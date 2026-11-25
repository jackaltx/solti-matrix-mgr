#!/usr/bin/env bash
#
# matrix-manage.sh — Generate and run Matrix provisioning playbooks
#
# Prereq: source ~/.secrets/LabProvision (sets VAULT_ADDR + VAULT_TOKEN)
#         source ~/.secrets/LabMatrix    (sets MATRIX_* vars)
#
# Usage:
#   ./matrix-manage.sh [-i INVENTORY] [-e KEY=VAL] [-v] <command> [target] [--cleanup]
#
# Commands:
#   provision list              Diff inventory rooms/bots against homeserver (read-only)
#   provision bootstrap         Create/update human users from Vault
#   provision <room-name>       Idempotent: create room + its bot users + members
#   provision all               Provision all rooms in matrix_rooms inventory order
#   provision remove <name>     Remove a room (--cleanup also removes sole_room bots with no remaining rooms)
#   provision recreate <name>   Remove then re-provision a room
#   list rooms                  Raw list of all rooms on the homeserver
#   list users <alias|room-id>  List members of a room with power levels
#   audit tokens                Audit admin user devices/access tokens
#   audit orphans               Scan for orphaned users and rooms
#
# Examples:
#   ./matrix-manage.sh -i inventory/hosts provision list
#   ./matrix-manage.sh -i inventory/hosts provision card-capture
#   ./matrix-manage.sh -i inventory/hosts provision remove card-capture --cleanup
#   ./matrix-manage.sh -i inventory/hosts provision recreate second-brain
#   ./matrix-manage.sh -i inventory/hosts provision bootstrap
#   ./matrix-manage.sh -i inventory/hosts audit orphans

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source Vault credentials (topology and secrets come from inventory + Vault)
if [[ -f "${HOME}/.secrets/LabProvision" ]]; then
    source "${HOME}/.secrets/LabProvision"
else
    echo "ERROR: ~/.secrets/LabProvision not found — VAULT_ADDR and VAULT_TOKEN required" >&2
    exit 1
fi

TEMP_DIR="${SCRIPT_DIR}/tmp"
INVENTORY="${SOLTI_INVENTORY:-$(dirname "${BASH_SOURCE[0]}")/inventory/hosts}"
EXTRA_ARGS=()

# Use venv ansible-playbook if present (ensures hvac and other deps are available).
# Search: collection-local venv → parent workspace venv → PATH
for _venv_candidate in \
    "${SCRIPT_DIR}/solti-venv/bin/ansible-playbook" \
    "${SCRIPT_DIR}/../solti-venv/bin/ansible-playbook"
do
    if [[ -f "$_venv_candidate" ]] && "$_venv_candidate" --version &>/dev/null; then
        ANSIBLE_PLAYBOOK="$_venv_candidate"
        break
    fi
done
unset _venv_candidate
if [[ -z "${ANSIBLE_PLAYBOOK:-}" ]]; then
    if command -v ansible-playbook &>/dev/null; then
        ANSIBLE_PLAYBOOK="ansible-playbook"
    else
        echo "ERROR: ansible-playbook not found — activate solti-venv or install ansible" >&2
        exit 1
    fi
fi

mkdir -p "${TEMP_DIR}"
chmod 700 "${TEMP_DIR}"

TEMP_PLAYBOOK=""
cleanup() {
    if [[ $? -eq 0 && -n "${TEMP_PLAYBOOK}" && -f "${TEMP_PLAYBOOK}" ]]; then
        rm -f "${TEMP_PLAYBOOK}"
    fi
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [-i INVENTORY] [-e KEY=VAL] [-v] <command> [target] [flags]

Commands:
  provision list              Diff inventory rooms/bots against homeserver (read-only)
  provision bootstrap         Create/update human users from Vault
  provision <room-name>       Provision a specific room (creates room + bot users + members)
  provision all               Provision all rooms defined in matrix_rooms
  provision remove <name>     Remove a room from the homeserver
                              --cleanup  also deactivate sole_room bots with no remaining rooms
  provision recreate <name>   Remove then re-provision a room

  list rooms                  Raw list of all rooms on the homeserver
  list users <target>         List members of a room
                              alias:   SecondBrain          (local part, no # or domain)
                              room-id: !abc123:jackaltx.com

  audit tokens                Audit admin access tokens/devices
  audit orphans               Scan for orphaned users and rooms

Options:
  -i INVENTORY    Inventory directory (or set SOLTI_INVENTORY env var)
  -e KEY=VALUE    Extra vars passed to ansible-playbook (repeatable)
  -v              Verbose ansible output

Prereq: source ~/.secrets/LabProvision && source ~/.secrets/LabMatrix
EOF
    exit 1
}

# ---------------------------------------------------------------------------
# Parse options
while getopts ":i:e:v" opt; do
    case $opt in
        i) INVENTORY="$OPTARG" ;;
        e) EXTRA_ARGS+=("-e" "$OPTARG") ;;
        v) EXTRA_ARGS+=("-v") ;;
        *) usage ;;
    esac
done
shift $((OPTIND - 1))

COMMAND="${1:-}"
TARGET="${2:-}"
ARG3="${3:-}"
CLEANUP=false
[[ "$ARG3" == "--cleanup" ]] && CLEANUP=true

[[ -z "$COMMAND" ]] && usage

# ---------------------------------------------------------------------------
# Validate inventory
if [[ -z "$INVENTORY" ]]; then
    echo "ERROR: Inventory required. Use -i INVENTORY or set SOLTI_INVENTORY." >&2
    exit 1
fi
if [[ ! -e "$INVENTORY" ]]; then
    echo "ERROR: Inventory not found: $INVENTORY" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Shared blocks embedded in generated playbooks

VAULT_LOGIN_VARS=$(cat <<'YAML'
  vars:
    _vault_addr:  "{{ lookup('env', 'VAULT_ADDR') }}"
    _vault_token: "{{ lookup('env', 'VAULT_TOKEN') }}"
    # Pull room/bot/human definitions from the homeserver's host_vars.
    # matrix_homeserver is defined in group_vars (e.g. matrix_mgr.yml).
    matrix_rooms:  "{{ hostvars[matrix_homeserver]['matrix_rooms']  | default([]) }}"
    matrix_bots:   "{{ hostvars[matrix_homeserver]['matrix_bots']   | default([]) }}"
    matrix_humans: "{{ hostvars[matrix_homeserver]['matrix_humans'] | default([]) }}"
YAML
)

PRE_TASKS=$(cat <<'YAML'
  pre_tasks:
    - name: Verify Vault env vars set
      ansible.builtin.assert:
        that:
          - lookup('env', 'VAULT_TOKEN') != ''
          - lookup('env', 'VAULT_ADDR') != ''
        fail_msg: "VAULT_TOKEN or VAULT_ADDR not set — run: source ~/.secrets/LabProvision"

    - name: Login to Matrix as admin (ephemeral token)
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/login"
        method: POST
        body_format: json
        body:
          type: "m.login.password"
          user: "{{ matrix_admin_user }}"
          password: "{{ matrix_admin_password }}"
        status_code: 200
      register: _login
      no_log: true

    - ansible.builtin.set_fact:
        _admin_token: "{{ _login.json.access_token }}"
      no_log: true
YAML
)

POST_TASKS=$(cat <<'YAML'
  post_tasks:
    - name: Logout (revoke ephemeral token)
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/logout"
        method: POST
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      no_log: true
      ignore_errors: true
YAML
)

# ---------------------------------------------------------------------------
generate_provision_list_playbook() {
    cat > "$TEMP_PLAYBOOK" <<YAML
---
# Generated by matrix-manage.sh: provision list
- name: Diff inventory rooms/bots against homeserver
  hosts: localhost
  connection: local
  gather_facts: false

${VAULT_LOGIN_VARS}

${PRE_TASKS}

  tasks:
    - name: Query all rooms from homeserver
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v1/rooms?limit=1000"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _hs_rooms
      no_log: true

    - name: Build homeserver alias index
      ansible.builtin.set_fact:
        _hs_aliases: "{{ _hs_rooms.json.rooms | map(attribute='canonical_alias') | select('string') | list }}"

    - name: Query all users from homeserver
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v2/users?from=0&limit=1000&guests=false"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _hs_users
      no_log: true

    - name: Build homeserver user index
      ansible.builtin.set_fact:
        _hs_user_ids: "{{ _hs_users.json.users
          | rejectattr('deactivated', 'defined')
          | map(attribute='name') | list
          + _hs_users.json.users
          | selectattr('deactivated', 'defined')
          | rejectattr('deactivated', 'equalto', true)
          | map(attribute='name') | list }}"

    - name: Build status lines
      ansible.builtin.set_fact:
        _status_lines: >-
          {%- set sep = '══════════════════════════════════════════' -%}
          {%- set lines = [sep, 'Provision Status — ' + matrix_domain, sep] -%}
          {%- for room in matrix_rooms -%}
            {%- set room_alias = '#' + room.alias + ':' + matrix_domain -%}
            {%- set room_ok = room_alias in _hs_aliases -%}
            {%- set _ = lines.append(('✓' if room_ok else '✗') + '  ' + room.name + '  (' + room_alias + ')') -%}
            {%- for m in room.members -%}
              {%- set uid = m.user_id + ':' + matrix_domain -%}
              {%- set u_ok = uid in _hs_user_ids -%}
              {%- set _ = lines.append('     ' + ('✓' if u_ok else '✗') + '  ' + m.user_id + '  [' + m.type[0]|upper + ']  pl=' + (m.power_level|string)) -%}
            {%- endfor -%}
          {%- endfor -%}
          {%- set _ = lines.append(sep) -%}
          {{ lines }}

    - name: Status table
      ansible.builtin.debug:
        msg: "{{ _status_lines }}"

${POST_TASKS}
YAML
}

# ---------------------------------------------------------------------------
generate_provision_bootstrap_playbook() {
    cat > "$TEMP_PLAYBOOK" <<YAML
---
# Generated by matrix-manage.sh: provision bootstrap
# Creates/updates human users from Vault. Safe to re-run.
- name: Bootstrap Matrix human users
  hosts: localhost
  connection: local
  gather_facts: false

${VAULT_LOGIN_VARS}

${PRE_TASKS}

  tasks:
    - name: Resolve human user passwords from Vault
      ansible.builtin.set_fact:
        _human_users: "{{ _human_users | default([]) + [{
          'user_id':     item.user_id,
          'displayname': item.displayname,
          'password':    lookup('community.hashi_vault.hashi_vault',
                           'kv/data/' + item.vault_path,
                           auth_method='token',
                           token=_vault_token,
                           url=_vault_addr)[item.vault_key | default('password')]
          }] }}"
      loop: "{{ matrix_humans }}"
      loop_control:
        label: "{{ item.user_id }}"
      no_log: true

    - name: Provision human users
      jackaltx.solti_matrix_mgr.matrix_config:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token:   "{{ _admin_token }}"
        domain:         "{{ matrix_domain }}"
        users:          "{{ _human_users }}"
        rooms:          []
      register: _result
      no_log: "{{ matrix_no_log | default(true) }}"

    - name: Results
      ansible.builtin.debug:
        msg: "Changed: {{ _result.changed }} | {{ _result.summary | default('') }}"

${POST_TASKS}
YAML
}

# ---------------------------------------------------------------------------
generate_provision_room_playbook() {
    local room_name="$1"

    if [[ "$room_name" == "all" ]]; then
        local room_filter="matrix_rooms"
        local play_title="Provision all rooms"
    else
        local room_filter="matrix_rooms | selectattr('name', 'equalto', '${room_name}') | list"
        local play_title="Provision room: ${room_name}"
    fi

    cat > "$TEMP_PLAYBOOK" <<YAML
---
# Generated by matrix-manage.sh: provision ${room_name}
- name: "${play_title}"
  hosts: localhost
  connection: local
  gather_facts: false

${VAULT_LOGIN_VARS}

${PRE_TASKS}

  tasks:
    - name: Process each room
      include_tasks: "${SCRIPT_DIR}/playbooks/tasks/provision_room.yml"
      loop: "{{ ${room_filter} }}"
      loop_control:
        loop_var: _room
        label: "{{ _room.name }}"

${POST_TASKS}
YAML
}

# ---------------------------------------------------------------------------
generate_provision_remove_playbook() {
    local room_name="$1"
    local do_cleanup="$2"

    cat > "$TEMP_PLAYBOOK" <<YAML
---
# Generated by matrix-manage.sh: provision remove ${room_name}
- name: "Remove room: ${room_name}"
  hosts: localhost
  connection: local
  gather_facts: false

${VAULT_LOGIN_VARS}

${PRE_TASKS}

  tasks:
    - name: Get room definition from inventory
      ansible.builtin.set_fact:
        _room: "{{ matrix_rooms | selectattr('name', 'equalto', '${room_name}') | first }}"

    - name: Resolve room alias to ID
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/directory/room/%23{{ _room.alias }}%3A{{ matrix_domain }}"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: [200, 404]
      register: _alias_lookup
      no_log: true

    - name: Abort if room does not exist
      ansible.builtin.fail:
        msg: "Room #{{ _room.alias }}:{{ matrix_domain }} not found on homeserver — nothing to remove"
      when: _alias_lookup.status == 404

    - name: Set room ID
      ansible.builtin.set_fact:
        _room_id: "{{ _alias_lookup.json.room_id }}"

    - name: Delete room via Synapse Admin API
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v1/rooms/{{ _room_id }}/delete"
        method: POST
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        body_format: json
        body:
          block: false
          purge: true
          message: "Room removed by matrix-manage.sh"
        status_code: 200
      register: _delete_result
      no_log: true

    - name: Room removed
      ansible.builtin.debug:
        msg: "Removed #{{ _room.alias }}:{{ matrix_domain }} ({{ _room_id }})"

$(if [[ "$do_cleanup" == "true" ]]; then
cat <<'CLEANUP_YAML'
    # --cleanup: deactivate sole_room bots that have no remaining memberships
    - name: Identify sole_room bots in this room
      ansible.builtin.set_fact:
        _sole_bots: >-
          {{
            _room.members
            | selectattr('type', 'equalto', 'bot')
            | map(attribute='user_id')
            | map('regex_replace', '$', ':' + matrix_domain)
            | select('in',
                matrix_bots
                | selectattr('sole_room', 'equalto', true)
                | map(attribute='user_id')
                | map('regex_replace', '$', ':' + matrix_domain)
                | list)
            | list
          }}

    - name: Query remaining room memberships for each sole_room bot
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v1/users/{{ item }}/joined_rooms"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _bot_memberships
      loop: "{{ _sole_bots }}"
      no_log: true

    - name: Deactivate bots with zero remaining rooms
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v1/deactivate/{{ item.item }}"
        method: POST
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        body_format: json
        body:
          erase: false
        status_code: 200
      loop: "{{ _bot_memberships.results }}"
      loop_control:
        label: "{{ item.item }}"
      when: item.json.total == 0
      register: _deactivated

    - name: Cleanup summary
      ansible.builtin.debug:
        msg: "Deactivated: {{ _deactivated.results | selectattr('changed', 'equalto', true) | map(attribute='item.item') | list }}"
CLEANUP_YAML
fi)

${POST_TASKS}
YAML
}

# ---------------------------------------------------------------------------
generate_list_rooms_playbook() {
    cat > "$TEMP_PLAYBOOK" <<YAML
---
# Generated by matrix-manage.sh: list rooms
- name: List Matrix Rooms
  hosts: localhost
  connection: local
  gather_facts: false

${PRE_TASKS}

  tasks:
    - name: Query Synapse Admin API for rooms
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v1/rooms?limit={{ room_limit | default(100) }}"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _rooms
      no_log: true

    - ansible.builtin.debug:
        var: rooms_result
      vars:
        rooms_result: "{{ _rooms.json.rooms | map('combine', {}) | map('dict2items') | map('selectattr', 'key', 'in', _fields) | map('items2dict') | list }}"
        _fields: [room_id, name, canonical_alias, creator, joined_members, join_rules]

    - ansible.builtin.debug:
        msg: "Total rooms: {{ _rooms.json.total_rooms }}"

${POST_TASKS}
YAML
}

# ---------------------------------------------------------------------------
generate_list_users_playbook() {
    local target="$1"

    if [[ "$target" == !* ]]; then
        local room_id="$target"
        cat > "$TEMP_PLAYBOOK" <<YAML
---
# Generated by matrix-manage.sh: list users ${room_id}
- name: "List members of ${room_id}"
  hosts: localhost
  connection: local
  gather_facts: false

${PRE_TASKS}

  tasks:
    - name: Get room power levels
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/rooms/${room_id}/state/m.room.power_levels"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _levels
      no_log: true

    - name: Get joined members
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/rooms/${room_id}/joined_members"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _members
      no_log: true

    - ansible.builtin.debug:
        msg: "{{ item.key }} — level {{ _levels.json.users.get(item.key, _levels.json.users_default | default(0)) }}"
      loop: "{{ _members.json.joined | dict2items }}"
      loop_control:
        label: "{{ item.key }}"

${POST_TASKS}
YAML

    else
        local room_alias="$target"
        cat > "$TEMP_PLAYBOOK" <<YAML
---
# Generated by matrix-manage.sh: list users ${room_alias}
- name: "List members of #${room_alias}"
  hosts: localhost
  connection: local
  gather_facts: false

${PRE_TASKS}

  tasks:
    - name: Resolve room alias to ID
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/directory/room/%23${room_alias}%3A{{ matrix_domain }}"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _alias
      no_log: true

    - name: Get room power levels
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/rooms/{{ _alias.json.room_id }}/state/m.room.power_levels"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _levels
      no_log: true

    - name: Get joined members
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/rooms/{{ _alias.json.room_id }}/joined_members"
        method: GET
        headers:
          Authorization: "Bearer {{ _admin_token }}"
        status_code: 200
      register: _members
      no_log: true

    - ansible.builtin.debug:
        msg: "{{ item.key }} — level {{ _levels.json.users.get(item.key, _levels.json.users_default | default(0)) }}"
      loop: "{{ _members.json.joined | dict2items }}"
      loop_control:
        label: "{{ item.key }}"

${POST_TASKS}
YAML
    fi
}

# ---------------------------------------------------------------------------
run_playbook() {
    local playbook="$1"
    local run_args=(-i "${INVENTORY}" "${playbook}")
    [[ ${#EXTRA_ARGS[@]} -gt 0 ]] && run_args+=("${EXTRA_ARGS[@]}")
    echo "Running: ${ANSIBLE_PLAYBOOK} ${run_args[*]}"
    echo ""
    "${ANSIBLE_PLAYBOOK}" "${run_args[@]}"
}

# ---------------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEMP_PLAYBOOK="${TEMP_DIR}/matrix-${COMMAND}-${TARGET:-}-${TIMESTAMP}.yml"

case "$COMMAND" in
    provision)
        case "$TARGET" in
            list)
                generate_provision_list_playbook
                ;;
            bootstrap)
                generate_provision_bootstrap_playbook
                ;;
            remove)
                [[ -z "$ARG3" || "$ARG3" == "--cleanup" ]] || true
                ROOM="${ARG3:-}"
                # re-parse: provision remove <name> [--cleanup]
                ROOM_NAME="${3:-}"
                CLEANUP_FLAG="${4:-}"
                [[ -z "$ROOM_NAME" || "$ROOM_NAME" == "--cleanup" ]] && {
                    echo "ERROR: provision remove requires a room name"
                    echo "       Usage: provision remove <room-name> [--cleanup]"
                    exit 1
                }
                DO_CLEANUP=false
                [[ "${CLEANUP_FLAG:-}" == "--cleanup" ]] && DO_CLEANUP=true
                generate_provision_remove_playbook "$ROOM_NAME" "$DO_CLEANUP"
                ;;
            recreate)
                ROOM_NAME="${3:-}"
                [[ -z "$ROOM_NAME" ]] && { echo "ERROR: provision recreate requires a room name"; exit 1; }
                # Remove first, then provision
                REMOVE_PLAYBOOK="${TEMP_DIR}/matrix-remove-${ROOM_NAME}-${TIMESTAMP}.yml"
                PROVISION_PLAYBOOK="${TEMP_DIR}/matrix-provision-${ROOM_NAME}-${TIMESTAMP}.yml"
                TEMP_PLAYBOOK="$REMOVE_PLAYBOOK"
                generate_provision_remove_playbook "$ROOM_NAME" "false"
                TEMP_PLAYBOOK="$PROVISION_PLAYBOOK"
                generate_provision_room_playbook "$ROOM_NAME"
                echo "=== Step 1: Remove ==="
                run_playbook "$REMOVE_PLAYBOOK"
                echo ""
                echo "=== Step 2: Provision ==="
                run_playbook "$PROVISION_PLAYBOOK"
                rm -f "$REMOVE_PLAYBOOK" "$PROVISION_PLAYBOOK"
                exit 0
                ;;
            "")
                echo "ERROR: provision requires a subcommand or room name"
                echo "       Try: provision list | bootstrap | <room-name> | all | remove <name> | recreate <name>"
                exit 1
                ;;
            *)
                generate_provision_room_playbook "$TARGET"
                ;;
        esac
        ;;
    list)
        case "$TARGET" in
            rooms) generate_list_rooms_playbook ;;
            users)
                [[ -z "${3:-}" ]] && { echo "ERROR: list users requires a room alias or room-id"; exit 1; }
                generate_list_users_playbook "${3}"
                ;;
            *) echo "ERROR: list target must be 'rooms' or 'users <alias>'"; exit 1 ;;
        esac
        ;;
    audit)
        case "$TARGET" in
            tokens)  TEMP_PLAYBOOK="${SCRIPT_DIR}/playbooks/admin/audit-tokens.yml"; trap - EXIT ;;
            orphans) TEMP_PLAYBOOK="${SCRIPT_DIR}/playbooks/admin/scan-orphans.yml"; trap - EXIT ;;
            *) echo "ERROR: audit target must be 'tokens' or 'orphans'"; exit 1 ;;
        esac
        ;;
    *) echo "ERROR: Unknown command: $COMMAND"; usage ;;
esac

run_playbook "$TEMP_PLAYBOOK"
