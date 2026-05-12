# CLAUDE.md — solti-matrix-mgr Collection

Ansible collection for managing a Matrix Synapse homeserver and posting structured
events. Grew organically during early Matrix exploration — carries some dead code.
See [STATUS_20260512.md](STATUS_20260512.md) for the full live-vs-dead analysis.

## What This Collection Does

Two distinct jobs:

1. **Provisioning** — declaratively create/update users and rooms via `matrix_config`
2. **Event bus** — post structured JSON events to Matrix rooms via `matrix_event`

The orchestrator (`mylab`) drives both. This collection is a pure library — no site
credentials, no domain-specific logic.

## Live Modules (the ones that matter)

| Module | Purpose |
|---|---|
| `matrix_config` | Declarative user + room provisioning — the workhorse |
| `matrix_event` | Post structured events to rooms, with self-healing auth |
| `synapse_user` | Create/update/deactivate individual users |
| `synapse_info` | Query homeserver facts and statistics |
| `synapse_device_info` | Audit and revoke devices/tokens |

## Dead Code (do not build on these)

**Modules** — exist in `plugins/modules/` but have no active callers:
- `synapse_room` — superseded by `matrix_config` rooms block
- `synapse_room_info` — no callers
- `synapse_user_info` — no callers

**Roles** — all three are unused:
- `hookshot_webhook` — Matrix-Hookshot not deployed
- `synapse_config` — Synapse managed via container, not file overlays
- `synapse_user` (role) — predates `matrix_config`, replaced by it

See STATUS_20260512.md for cleanup options (archive vs delete).

## Key Architecture: `matrix_config`

The most-used module. Declarative and idempotent — define the desired state,
it converges to it. Never deletes resources (additive only).

```yaml
- jackaltx.solti_matrix_mgr.matrix_config:
    homeserver_url: "{{ matrix_homeserver_url }}"
    access_token:   "{{ matrix_admin_token }}"
    domain:         "{{ matrix_domain }}"
    users:
      - user_id:     "@botname"
        displayname: "Bot Display Name"
        password:    "{{ lookup('env', 'BOT_PASS') }}"
        ratelimit_override:
          messages_per_second: 0
          burst_count: 0
    rooms:
      - alias: "RoomAlias"
        name:  "Room Name"
        topic: "Room topic"
        encrypted: false
        retention:
          max_lifetime_days: 30
        members:
          - user_id: "@admin"
            power_level: 100
          - user_id: "@botname"
            power_level: 50
```

Token for the new user is returned in `result.tokens["@botname:domain"]` and
saved to `~/.secrets/LabMatrix` by the calling playbook.

## Key Architecture: `matrix_event` (Self-Healing Auth)

Provide both `access_token` and credentials (`user_id` + `password`). If the
token is expired, the module re-authenticates automatically, caches the new
token in `/tmp/ansible-matrix-token-<hash>` (0600), and retries. Never fails
due to stale tokens.

```yaml
- jackaltx.solti_matrix_mgr.matrix_event:
    homeserver_url: "{{ matrix_homeserver_url }}"
    access_token:   "{{ matrix_bot_token }}"
    user_id:        "@bot:{{ domain }}"
    password:       "{{ bot_password }}"
    room_id:        "#room:{{ domain }}"
    content:
      msgtype: "com.solti.event"
      body:    "Verification PASSED"
      solti:
        schema: "verify.pass.v1"
        source: "service/host"
```

## How Playbooks Are Run from mylab

Never call `ansible-playbook` directly for Matrix admin. Use the wrapper:

```bash
cd mylab
source ~/.secrets/LabProvision && source ~/.secrets/LabMatrix
./bin/matrix-playbook.sh playbooks/matrix/salty-matrix-config.yml
```

The wrapper generates an ephemeral admin token (1h TTL, cached), injects it as
`MATRIX_ADMIN_TOKEN`, and the playbook picks it up via `lookup('env', ...)`.

## Molecule Testing

Scenarios live in **`extensions/molecule/`** (not a top-level `molecule/` dir):

| Scenario | Status |
|---|---|
| `default` | Active |
| `apply-config` | Active — tests `matrix_config` |
| `e2e` | Active |
| `jack1` | Abandoned |
| `self-contained` | Abandoned |
| `user-mgmt` | Abandoned |

## Inventory / Config

- `inventory/group_vars/all.yml` — gitignored, site-specific values
- `inventory/group_vars/vault.yml.example` — template for secrets structure

## Claude's Role

- Adding new Matrix config playbooks in `mylab/playbooks/matrix/` — follow the
  pattern in `salty-matrix-config.yml` (layer on existing config, add user + room member)
- Extending `matrix_config` or `matrix_event` modules
- Debugging token issues — check `/tmp/ansible-matrix-token-*` on the host
- Do not touch the dead modules/roles unless explicitly cleaning them up
