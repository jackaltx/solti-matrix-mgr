# SOLTI Matrix Manager Collection (jackaltx.solti_matrix_mgr)

Ansible collection for managing Matrix Synapse homeservers and providing a **Reliable Data Plane** for structured system events and notifications.

## Overview

This collection is designed for technical operators and automation tools (like **ref.tools**) that require robust, self-healing communication with Matrix homeservers. It moves beyond simple API wrappers by implementing session management and automatic recovery.

### Key Features
- **Self-Healing Authentication**: Modules automatically detect expired tokens and re-authenticate using provided credentials.
- **Local Token Caching**: Reduces API load and prevents rate-limiting (`M_LIMIT_EXCEEDED`) by caching tokens in `/tmp`.
- **Structured Event Transport**: Pure transport layer for posting arbitrary JSON content (supporting Solti Event Schemas).
- **Declarative Admin**: Roles for converging homeserver state (users, rooms, config overlays).

---

## Installation

```bash
# From source
cd solti-matrix-mgr/
ansible-galaxy collection build
ansible-galaxy collection install jackaltx-solti_matrix_mgr-*.tar.gz
```

---

## Core Module: `matrix_event`

The `matrix_event` module is the primary interface for system notifications. It ensures your events arrive even if the bot's session has been invalidated.

### Self-Healing Pattern (Recommended)
Always provide `user_id` and `password` alongside the `access_token`. The module will use the token first (fast), fall back to the local cache, and only perform a full login if necessary.

```yaml
- name: Post structured verification event
  jackaltx.solti_matrix_mgr.matrix_event:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ matrix_bot_token }}"
    user_id: "@solti-logger:example.com"    # Required for self-healing
    password: "{{ bot_password }}"           # Required for self-healing
    room_id: "#solti-verify:example.com"
    content:
      msgtype: "com.solti.event"
      body: "Verification PASSED"
      solti:
        schema: "verify.pass.v1"
        source: "monitoring/prod"
        data:
          status: "OK"
          services: { loki: true, influx: true }
```

### Parameters

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `homeserver_url` | str | Yes | URL of the Matrix homeserver. |
| `access_token` | str | Yes | Bot or user access token. |
| `user_id` | str | No | MXID for re-authentication fallback. |
| `password` | str | No | Password for re-authentication fallback. |
| `room_id` | str | Yes | Room ID (`!xxx`) or alias (`#xxx`). |
| `content` | dict | Yes | The full JSON payload for the event. |

---

## Admin Modules

### `synapse_user`
Manage user accounts and bot identities.
```yaml
- name: Ensure bot user exists with no rate limits
  jackaltx.solti_matrix_mgr.synapse_user:
    homeserver_url: "{{ hs_url }}"
    access_token: "{{ admin_token }}"
    user_id: "@bot:example.com"
    password: "{{ bot_password }}"
    ratelimit_override:
      messages_per_second: 0
      burst_count: 0
    state: present
```

### `synapse_device_info` (Audit & Cleanup)
Audit and manage user devices/tokens. Crucial for managing bot sessions across distributed nodes.
```yaml
- name: Cleanup old ansible tokens (>30 days)
  jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "{{ hs_url }}"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
    user_agent_filter: "ansible-httpget"
    older_than_days: 30
    revoke_matched: true
```

---

## Architecture & Integration

### For ref.tools Operators
This collection acts as the **Data Plane**. Orchestrators (like `mylab`) should provide the credentials, while this collection ensures the delivery of the data.

1. **Inventory Driven**: Define users and rooms in your inventory.
2. **Ephemeral Admins**: Use the `matrix-playbook.sh` wrapper (in `mylab/bin`) to generate short-lived admin tokens for maintenance.
3. **Persistent Bots**: Use the self-healing `matrix_event` module for long-running service notifications.

### Proxmox & Docker Support
Optimized for layered configuration on Proxmox LXC (via `conf.d` overlays) and `matrix-docker-ansible-deploy` environments.

---

## Documentation
- **[Token Management Guide](docs/token-management.md)** - Ephemeral vs Persistent strategies.
- **[Event Schemas](docs/event-schemas.md)** - Defining structured payloads for automated processing.
- **[Self-Healing Design](GEMINI.md)** - Technical details on the caching and recovery logic.

## License
MIT
