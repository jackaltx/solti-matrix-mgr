# Matrix Manager Collection - Gemini Agent Context

This collection provides robust Ansible modules for managing Matrix Synapse homeservers and posting structured system events.

## Architectural Principles

*   **Generic Matrix Client**: Acts as a pure transport/management layer, free of domain-specific business logic.
*   **Self-Healing Authentication**: The `matrix_event` module and underlying `MatrixClientAPI` feature "Login-on-Failure." They automatically detect expired tokens and re-authenticate using provided credentials without failing the playbook.
*   **Local Token Caching**: To prevent rate-limiting (`M_LIMIT_EXCEEDED`) and reduce API load, tokens are cached in `/tmp/ansible-matrix-token-<user_hash>` with restrictive permissions (0600).

## Token Lifecycle Strategies

### Orchestrated Workflow (mylab)
The preferred way to run admin tasks is via the orchestrator's wrapper:
```bash
# mylab/bin/matrix-playbook.sh
./bin/matrix-playbook.sh playbooks/matrix/list-rooms.yml
```
This generates an ephemeral admin token for the session and auto-revokes it on completion.

### Event Notification Workflow (Self-Healing)
For automated notifications (e.g., in CI/CD or monitoring), the module manages its own token:
```yaml
- name: Post deployment event
  jackaltx.solti_matrix_mgr.matrix_event:
    homeserver_url: "{{ matrix_url }}"
    access_token: "{{ matrix_token }}"  # Current/cached token
    user_id: "@bot:server.com"           # Fallback for re-auth
    password: "{{ bot_password }}"        # Fallback for re-auth
    room_id: "#ops:server.com"
    content: "{{ event_data }}"
```
If `access_token` is invalid, the module logs in as `@bot`, gets a fresh token, caches it locally for future tasks, and retries the post.

## Key Development Files

*   `plugins/modules/matrix_event.py`: Entry point for system notifications.
*   `plugins/module_utils/matrix_client.py`: Core API logic including the self-healing and caching mechanisms.
*   `mylab/playbooks/test-matrix-event.yml`: Comprehensive acid test for verifying authentication resiliency.

## Testing & Validation

1.  **Unit/Integration**: Use Molecule scenarios in the `molecule/` directory.
2.  **Authentication Resiliency**: Run `test-matrix-event.yml` with a deliberately invalid `MATRIX_ACCESS_TOKEN` to verify the self-healing and caching logic.
3.  **Audit**: Use `mylab/playbooks/matrix/audit-tokens.yml` to monitor and clean up orphaned tokens for the admin user.
