# CLAUDE.md — solti-matrix-mgr Collection

Ansible collection for managing a Matrix Synapse homeserver and posting structured
events. Grew organically during early Matrix exploration — carries some dead code.
See [STATUS_20260512.md](STATUS_20260512.md) for the full live-vs-dead analysis.

## What This Collection Does

> **Surfacing to unified docs:** Update `solti-docs.yml` at the collection root
> to declare which files and CLAUDE.md sections should appear on solti.jackaltx.com.
> Local `docs/` detail stays local — only declare what matters to the suite-wide audience.
> See [solti-docs/HARVEST.md](https://github.com/jackaltx/solti-docs/blob/main/HARVEST.md).

Two distinct jobs:

1. **Provisioning** — declaratively create/update users and rooms via `matrix_config`
2. **Event bus** — post structured JSON events to Matrix rooms via `matrix_event`

The orchestrator (`mylab`) drives both. This collection is a pure library — no site
credentials, no domain-specific logic.

## Docs

- [`docs/event-schemas.md`](docs/event-schemas.md) — Structured event schema definitions (verify.pass.v1, verify.fail.v1, planned deploy.*)
- [`docs/token-management.md`](docs/token-management.md) — Admin token lifecycle, auditing, single-use workflow
- [`docs/playbook-examples.md`](docs/playbook-examples.md) — Working playbook patterns
- [`docs/README.md`](docs/README.md) — Docs index

### Event Schema System

SOLTI events use a layered schema: Matrix transport carries a human-readable `body` for Element
rendering plus a machine-readable `solti:` block with `schema`, `timestamp`, `source`, and `data`.

```yaml
content:
  msgtype: m.text
  body: "✅ Verification PASSED: 5/5 services on rocky9_9.0"
  solti:
    schema: "verify.pass.v1"
    timestamp: "2026-02-11T15:30:45Z"
    source: "molecule/rocky9/podman"
    data:
      distribution: "rocky9_9.0"
      services: { alloy: true, loki: true, ... }
```

Live schemas: `verify.pass.v1`, `verify.fail.v1`. Planned: `deploy.start.v1`, `deploy.complete.v1`.

Room routing: `#solti-verify` for verification, `#solti-deploys` for deployments (planned).

Decoder: `matrix-view-events.py` dispatches on `content.solti.schema` for rich CLI display.

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

## Architectural Vision — Matrix as Federated Control Plane

Matrix rooms are more than chat channels — they are **scoped, federated control planes
for infrastructure services**, with bots as the translation layer between human intent
and API calls (ISPConfig, Vault, Docker, etc.).

**Why this works:**

- Power levels + invite-only rooms = access control without any external auth system
- A bot only accepts commands from users with sufficient power level in that room
- The room IS the security context — no external database needed
- Room state is federated: works across homeservers, portable to any Matrix client
- Matrix is an event-sourced audit log by nature — every action is recorded

**The Q/P/R triad:** every operation in this collection follows Query → Process → Report.
`list-rooms.yml` is the reference implementation. `matrix_config` follows the same pattern
at the module level (query current state, diff against desired, report changes).

## Operation Taxonomy

The mylab matrix playbooks fall into four categories — these map to future `matrix-manage.sh` verbs:

| Verb | Playbooks | Description |
|------|-----------|-------------|
| `provision` | `*-matrix-config.yml` | Idempotent create/update: user + room + members + power levels |
| `remove` | `remove-*`, `delete-room`, `clear-room` | Tear down resources |
| `list` | `list-rooms`, `list-rooms-by-user`, `list-users-by-room` | Query + display |
| `audit` | `audit-tokens`, `scan-orphans`, `cleanup-orphans` | Inspect + optional remediate |

## Layered Provisioning Pattern

Human-readable from the existing mylab playbooks:

```text
base          → @admin, @jackal, @solti-logger    (humans + ops rooms)
second-brain  → @conner, @brain2  + #SecondBrain  (bot gets its own room)
salty         → @salty added to #SecondBrain      (bot joins existing room — no new room)
card-capture  → @card-capture    + #CardCapture   (bot gets its own room)
```

Key distinction: a bot either **owns a room** (creates it, is creator) or **joins a room**
(added as member to a room owned by another bot/user). Both are idempotent via `matrix_config`.

## Inventory Schema Direction (matrix-manage.sh)

The 9 hand-written mylab playbooks are 90% identical boilerplate — only the `vars` block
differs. The generator reads this schema from inventory and constructs the `matrix_config`
call at runtime. Credentials come from Vault, not env vars.

```yaml
# inventory/hosts/group_vars/matrix_bots.yml  (private repo)
matrix_homeserver: "matrix-web"
matrix_domain: "jackaltx.com"
matrix_homeserver_url: "https://matrix-web.jackaltx.com"

matrix_bots:
  - name: "card-capture"
    user_id: "@card-capture"
    displayname: "Card Capture Bot"
    vault_path: "infrastructure/matrix-web/synapse/bots/card-capture"
    ratelimit_override: {messages_per_second: 0, burst_count: 0}
    room:
      alias: "CardCapture"
      name: "Card Capture"
      topic: "Drop a business card photo — bot extracts contact to Second Brain"
      retention: {max_lifetime_days: 7}
      members:
        - {user_id: "@jackal",       power_level: 100}
        - {user_id: "@card-capture", power_level: 50}

  - name: "salty"
    user_id: "@salty"
    displayname: "Salty"
    vault_path: "infrastructure/matrix-web/synapse/bots/salty"
    ratelimit_override: {messages_per_second: 0, burst_count: 0}
    room:
      alias: "SecondBrain"   # existing room — bot joins, does not create
      join_only: true
      members:
        - {user_id: "@jackal", power_level: 100}
        - {user_id: "@salty",  power_level: 50}
```

`join_only: true` signals intent: this bot does not own the room. The generator skips
room creation and only ensures membership and power levels.

Token output: written to Vault at `kv/runtime/matrix-web/bots/<name>/token` instead of
`~/.secrets/LabMatrix`. This is the migration path from the current env-var pattern.

## Architecture Direction — Runtime Provisioning for Agent Delegation

The intended future role is as the **provisioning backend for the delegator/sub-agent
pattern** in `solti-matrix-bots`. When salty-bot needs to spin up a per-room card-capture
instance, it provisions the room at runtime — not from an Ansible playbook.

**The gap:** `matrix_config` is an Ansible module. The Matrix Admin API calls inside it
are plain `requests`. Extract the core logic into a `solti_matrix` Python package
(vendored into the bot venv) so bots can call `provision_room(alias, members)` directly.

This is a **future sprint** item. Ansible-only usage is correct for now.

## Claude's Role

- New bot provisioning: add entry to `matrix_bots` in private inventory, run generator
- Do not add new per-bot playbooks to `mylab/playbooks/matrix/` — migrate to generator instead
- Extending `matrix_config` or `matrix_event` modules: read this file first
- Debugging token issues: check `/tmp/ansible-matrix-token-*` on the controller
- Do not touch dead modules/roles (synapse_room, hookshot_webhook, synapse_config) unless explicitly cleaning up
