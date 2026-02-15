# Matrix Token Management

Guide to managing Matrix admin access tokens in the solti-matrix-mgr collection.

## Overview

Matrix uses access tokens for authentication. This collection provides tools for:
- Generating admin tokens
- Auditing active tokens (devices)
- Cleaning up old/orphaned tokens
- Single-use token workflows

## Architecture

### Token Types

**Bot tokens** (`MATRIX_ACCESS_TOKEN`)
- Used for posting events, sending messages
- Long-lived, manually managed
- Stored in `~/.secrets/LabMatrix`

**Admin tokens** (`MATRIX_ADMIN_TOKEN`)
- Used for Synapse Admin API operations
- Can be short-lived or cached
- Generated via `get-admin-token.sh`

### Single Source of Truth

All credentials live in `~/.secrets/LabMatrix`:

```bash
# Bot user (@solti-logger) - for posting events
export MATRIX_ACCESS_TOKEN="syt_c29sdGktbG9nZ2Vy_..."
export MATRIX_HOMESERVER_URL="https://matrix-web.jackaltx.com"
export MATRIX_ROOM_ID="#solti-verify:jackaltx.com"

# Admin user - for Synapse Admin API
export MATRIX_ADMIN_USER="@admin:jackaltx.com"
export MATRIX_ADMIN_PASSWORD="..."
export MATRIX_ADMIN_TOKEN="syt_YWRtaW4_..."
```

## Token Lifecycle

### 1. Generate Admin Token

```bash
cd mylab
./bin/get-admin-token.sh
```

**What it does:**
1. Sources credentials from `~/.secrets/LabMatrix`
2. Logs in to Matrix homeserver with username/password
3. Receives new access token from server
4. Updates `MATRIX_ADMIN_TOKEN` in LabMatrix file

**Important:** Each login creates a NEW token. Old tokens remain valid (not revoked).

### 2. Token Auditing

Use the `synapse_device_info` module to list active tokens:

```yaml
- name: List all admin devices
  jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "{{ matrix_homeserver_url }}"
    access_token: "{{ matrix_admin_token }}"
    user_id: "@admin:jackaltx.com"
  register: devices
```

**Playbook:**
```bash
ansible-playbook playbooks/matrix/audit-tokens.yml
```

### 3. Token Cleanup

**Manual cleanup:**
```bash
ansible-playbook playbooks/matrix/audit-tokens.yml \
  -e "cleanup_old=true" \
  -e "max_age_days=30"
```

**Single-use pattern:**
```bash
ansible-playbook playbooks/matrix/list-rooms.yml \
  -e "cleanup_token=true"
```

**Scheduled cleanup (cron):**
```cron
# Weekly token cleanup
0 2 * * 0 cd /path/to/mylab && source ~/.secrets/LabMatrix && ansible-playbook playbooks/matrix/audit-tokens.yml -e "cleanup_old=true max_age_days=30"
```

## Module Reference: synapse_device_info

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `homeserver_url` | str | yes | - | Matrix homeserver URL |
| `access_token` | str | yes | - | Admin access token |
| `user_id` | str | yes | - | Full Matrix user ID |
| `user_agent_filter` | str | no | - | Filter by user_agent substring |
| `older_than_days` | int | no | - | Filter devices older than N days |
| `display_name_filter` | str | no | - | Filter by display_name substring |
| `revoke_matched` | bool | no | false | Revoke devices that match filters |
| `validate_certs` | bool | no | true | Validate SSL certificates |

### Return Values

| Key | Type | Description |
|-----|------|-------------|
| `devices` | list | All devices for the user |
| `matched_devices` | list | Devices matching filter criteria |
| `total_devices` | int | Total device count |
| `matched_count` | int | Count of matched devices |
| `revoked_devices` | list | Device IDs that were revoked (if `revoke_matched=true`) |
| `changed` | bool | Whether any devices were revoked |

### Examples

**List all devices:**
```yaml
- jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
  register: all_devices
```

**Find orphaned tokens (never used):**
```yaml
- jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
    older_than_days: 0  # Never-seen devices only
  register: orphaned
```

**Cleanup old ansible tokens:**
```yaml
- jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
    user_agent_filter: "ansible-httpget"
    older_than_days: 30
    revoke_matched: true
  register: cleanup
```

## Best Practices

### Development/Testing
- Use cached tokens (`~/.secrets/LabMatrix`)
- Manual cleanup via `audit-tokens.yml` when needed
- Fast iteration, minimal overhead

### Production/Automation
- Use single-use tokens (`-e "cleanup_token=true"`)
- Auto-revoke after each playbook run
- Prevents token accumulation

### Scheduled Jobs
- Periodic token audits (weekly/monthly)
- Cleanup tokens older than threshold (30-90 days)
- Monitor for unusual device counts

## Security Considerations

1. **Token storage:** `~/.secrets/LabMatrix` contains plaintext tokens
   - Protect with file permissions (`chmod 600`)
   - Never commit to git
   - Use secret management tools in production

2. **Token rotation:** Manually generated tokens don't expire by default
   - Implement regular cleanup schedules
   - Use single-use pattern for sensitive operations

3. **Audit logging:** Track token usage
   - Monitor device counts via `synapse_device_info`
   - Alert on unexpected device growth
   - Investigate orphaned/never-used tokens

4. **Access control:** Admin tokens have full Synapse access
   - Limit who can access `~/.secrets/LabMatrix`
   - Use separate tokens for different automation tasks
   - Revoke tokens immediately if compromised

## Troubleshooting

### "Invalid access token" errors

**Symptom:** `{"errcode":"M_UNKNOWN_TOKEN","error":"Invalid access token passed."}`

**Cause:** Token expired or revoked

**Solution:**
```bash
./bin/get-admin-token.sh
source ~/.secrets/LabMatrix
```

### Too many active devices

**Symptom:** 20+ devices for admin user

**Cause:** Tokens accumulating without cleanup

**Solution:**
```bash
ansible-playbook playbooks/matrix/audit-tokens.yml -e "cleanup_old=true max_age_days=7"
```

### Token revoked unexpectedly

**Symptom:** Token works, then stops working between playbook runs

**Cause:** `cleanup_token=true` was used, or password was changed

**Solution:**
- Check if single-use cleanup is enabled
- Verify admin password hasn't changed
- Regenerate token via `get-admin-token.sh`

## See Also

- [Playbook Examples](playbook-examples.md)
- [Module: synapse_device_info](../plugins/modules/synapse_device_info.py)
- [Script: get-admin-token.sh](../../mylab/bin/get-admin-token.sh)
- [Synapse Admin API Documentation](https://matrix-org.github.io/synapse/latest/usage/administration/admin_api/)
