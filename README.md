# SOLTI Matrix Manager Collection (jackaltx.solti_matrix_mgr)

Ansible collection for managing Matrix homeservers (Synapse primarily) via the Admin API and configuration overlays, as well as providing a generic event posting mechanism to Matrix rooms.

## Overview

This collection provides:

- **Custom Modules** for the Synapse Admin API:
  - `synapse_user` - Create/update/deactivate users
  - `synapse_room` - Query/delete rooms
  - `synapse_info` - Gather server facts (users, rooms, version)
  - `matrix_event` - Post arbitrary content to Matrix rooms (pure transport layer)

- **Roles** for declarative configuration:
  - `synapse_user` - Manage user accounts
  - `synapse_config` - Deploy homeserver.yaml overlays and appservices
  - `hookshot_webhook` - Configure matrix-hookshot webhooks

## Requirements

- Ansible 2.14+
- Python 3.9+
- A running Synapse homeserver with Admin API access
- Admin access token (user must be server admin)

## Installation

```bash
# From Galaxy (when published)
ansible-galaxy collection install jackaltx.solti_matrix_mgr

# From source
cd solti-matrix-mgr/
ansible-galaxy collection build
ansible-galaxy collection install jackaltx-solti_matrix_mgr-*.tar.gz
```

## Quick Start

### 1. Set up inventory

```bash
cp inventory/hosts.example inventory/hosts
cp inventory/group_vars/vault.yml.example inventory/group_vars/vault.yml
ansible-vault encrypt inventory/group_vars/vault.yml
```

Edit `inventory/hosts` with your Matrix server(s).

### 2. Configure variables

Edit `inventory/group_vars/all.yml`:

```yaml
matrix_domain: "example.com"
synapse_homeserver_url: "https://matrix.{{ matrix_domain }}"
synapse_admin_token: "{{ vault_synapse_admin_token }}"

synapse_users:
  - user_id: "@alice:{{ matrix_domain }}"
    displayname: "Alice"
    password: "{{ vault_alice_password }}"
    state: present
```

### 3. Run the playbook

```bash
# Full run
ansible-playbook -i inventory/hosts playbooks/site.yml

# Just users
ansible-playbook -i inventory/hosts playbooks/site.yml --tags users

# Check mode (dry run)
ansible-playbook -i inventory/hosts playbooks/site.yml --check
```

## Module Reference

### matrix_event

The `matrix_event` module acts as a generic transport layer for posting arbitrary JSON content to Matrix rooms. It does not enforce any specific schema or structure on the content, allowing full flexibility for custom event types, including those with embedded Solti-specific data.

**Parameters:**

- `homeserver_url` (str, required): URL of the Matrix homeserver.
- `access_token` (str, required): Bot or user access token for authentication.
- `room_id` (str, required): Room ID (`!xxx:server.com`) or alias (`#xxx:server.com`).
- `content` (dict, required): The full `content` dictionary for the Matrix event. This must include `msgtype` and `body`.
- `transaction_id` (str, optional): Optional explicit transaction ID for idempotency.
- `validate_certs` (bool, default: `true`): Validate SSL certificates.

**Example Usage:**

```yaml
- name: Post a Solti verification failure event
  set_fact:
    failure_content:
      msgtype: "m.text"
      body: "❌ Verification FAILED for service 'loki'"
      solti:
        schema: "verify.fail.v1"
        source: "molecule/test-env"
        data:
          service: "loki"
          reason: "Health check failed"

- name: Send verification failure event to Matrix
  jackaltx.solti_matrix_mgr.matrix_event:
    homeserver_url: "{{ matrix_homeserver_url }}"
    access_token: "{{ matrix_access_token }}"
    room_id: "#solti-verify:example.com"
    content: "{{ failure_content }}"

- name: Post a simple text message
  jackaltx.solti_matrix_mgr.matrix_event:
    homeserver_url: "{{ matrix_homeserver_url }}"
    access_token: "{{ matrix_access_token }}"
    room_id: "#general:example.com"
    content:
      msgtype: "m.text"
      body: "Hello from Ansible!"
```

### synapse_user

```yaml
- name: Create a user
  jackaltx.solti_matrix_mgr.synapse_user:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@alice:example.com"
    password: "{{ user_password }}"
    displayname: "Alice Smith"
    admin: false
    state: present

- name: Create a bot with no rate limits
  jackaltx.solti_matrix_mgr.synapse_user:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@bot:example.com"
    password: "{{ bot_password }}"
    ratelimit_override:
      messages_per_second: 0
      burst_count: 0
    state: present
```

### synapse_room

```yaml
- name: Get room info
  jackaltx.solti_matrix_mgr.synapse_room:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    room_id: "!abc123:example.com"
    state: info
  register: room

- name: Delete and block a room
  jackaltx.solti_matrix_mgr.synapse_room:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    room_id: "!spam:example.com"
    state: absent
    purge: true
    block: true
```

### synapse_info

```yaml
- name: Gather server facts
  jackaltx.solti_matrix_mgr.synapse_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    gather:
      - version
      - users
      - rooms
    limit: 100
  register: server_info
```

## Role Reference

### synapse_user role

Variables:
```yaml
synapse_homeserver_url: "https://matrix.example.com"
synapse_admin_token: "{{ vault_token }}"
synapse_users:
  - user_id: "@user:example.com"
    password: "secret"
    displayname: "Display Name"
    admin: false
    state: present
    ratelimit_disabled: false  # Set true for bots
```

### synapse_config role

Variables:
```yaml
synapse_config_dir: "/etc/synapse"
synapse_config_overlays:
  federation:
    allow_public_rooms_over_federation: false
  registration:
    enable_registration: false

synapse_appservices:
  - name: hookshot
    registration_file: "files/hookshot.yaml"
```

### hookshot_webhook role

Variables:
```yaml
hookshot_config_dir: "/matrix/hookshot"
hookshot_webhooks:
  - name: "ci-notifications"
    room_id: "!room:example.com"
    enabled: true
```

## Architecture Notes

### For Proxmox Helper-Script LXC installs

The Helper-Script installs Synapse as a systemd service with configs in `/etc/synapse/`. This collection layers on top via:

1. SSH access for config file management
2. Admin API for user/room operations

```
┌─────────────────────────────────────┐
│ LXC Container                       │
├─────────────────────────────────────┤
│ /etc/synapse/                       │
│   ├── homeserver.yaml               │
│   ├── conf.d/                       │  ← Ansible overlays
│   │   ├── federation.yaml           │
│   │   └── registration.yaml         │
│   └── appservices/                  │  ← Bridge registrations
│       └── hookshot.yaml             │
├─────────────────────────────────────┤
│ Synapse (systemd)                   │
│   └── Admin API :8008               │  ← Module API calls
└─────────────────────────────────────┘
```

### For spantaleev/matrix-docker-ansible-deploy

This collection can work alongside the spantaleev playbook for additional automation. Adjust paths:

```yaml
synapse_config_dir: "/matrix/synapse/config"
hookshot_config_dir: "/matrix/hookshot"
hookshot_is_containerized: true
```

## Webhook Integration

### Inbound webhooks (external → Matrix)

1. Deploy hookshot with `matrix_hookshot_enabled: true`
2. Use this collection to document expected webhooks
3. Create endpoints via `!hookshot webhook <name>` in target rooms
4. Send HTTP POST to the generated URL:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"text": "Build passed!", "username": "CI Bot"}' \
  "https://matrix.example.com/hookshot/webhook/<id>"
```

### Outbound webhooks (Matrix → external)

Configure in hookshot for room events to trigger external URLs.

## Testing

```bash
# Syntax check
ansible-playbook --syntax-check playbooks/site.yml

# Check mode
ansible-playbook -i inventory/hosts playbooks/site.yml --check --diff

# Verbose output
ansible-playbook -i inventory/hosts playbooks/site.yml -vvv
```

## Related Projects

- [spantaleev/matrix-docker-ansible-deploy](https://github.com/spantaleev/matrix-docker-ansible-deploy) - Full Matrix stack deployment
- [matrix-org/matrix-hookshot](https://github.com/matrix-org/matrix-hookshot) - Webhook bridge
- [maubot/maubot](https://github.com/maubot/maubot) - Bot plugin framework
- [synadm](https://github.com/JOJ0/synadm) - CLI for Synapse Admin API

## License

MIT
