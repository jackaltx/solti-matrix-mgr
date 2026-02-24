# Molecule Test Scenarios

This directory contains Molecule test scenarios for the `solti_matrix_mgr` collection.

## Scenarios Overview

| Scenario | Environment | Purpose | Usage |
| --- | --- | --- | --- |
| **default** | Local Matrix | Test `matrix_event` module against live Matrix server | `molecule test` |
| **jack1** | Local Matrix | Test `synapse_room` and `synapse_user` modules with self-healing auth | `molecule test -s jack1` |
| **user-mgmt** | Local Matrix | Test `synapse_user` with user_type, `synapse_user_info`, and `synapse_room_info` | `molecule test -s user-mgmt` |
| **e2e** | GitHub Actions | End-to-end integration test with Synapse in Docker | CI only |
| **self-contained** | Local (mocked) | Test configuration generation without live server | `molecule test -s self-contained` |

## Scenario Details

### default

**Location:** Local development
**Target:** Live Matrix homeserver (requires credentials)
**Tests:**
- `matrix_event` module functionality
- Event posting and verification
- Self-healing authentication

**Requirements:**
```bash
export MATRIX_HOMESERVER_URL="https://matrix-web.jackaltx.com"
export MATRIX_ROOM_ID="#solti-verify:jackaltx.com"
export MATRIX_SOLTI_LOGGER_TOKEN="syt_..."
export MATRIX_ADMIN_USER="@admin:jackaltx.com"
export MATRIX_ADMIN_TOKEN="syt_..."
export MATRIX_BOT_SOLTI_LOGGER_PASSWORD="password"
```

**Artifacts:** `~/.ansible/tmp/molecule.*/verify_output/matrix_event_result.json`

### jack1

**Location:** Local development
**Target:** Live Matrix homeserver (requires credentials)
**Tests:**
- `synapse_room` module (create, info, join states)
- `synapse_user` module (create user)
- Self-healing token management
- Room information retrieval

**Requirements:** Same as `default` scenario

**Artifacts:** `~/.ansible/tmp/molecule.*/verify_output/matrix_event_result.json`

### user-mgmt

**Location:** Local development
**Target:** Live Matrix homeserver (requires credentials)
**Tests:**

- `synapse_user` module with `user_type` support (bot users)
- `synapse_user_info` module (list/filter users by type)
- `synapse_room_info` module (query rooms by alias)
- Idempotent user creation
- User-to-user_type mapping (role: bot → user_type: "bot")

**Requirements:** Same as `default` scenario

**Test Flow:**

1. Create 2 bot users with `user_type: "bot"`
2. Create test room
3. Query bot users via `synapse_user_info`
4. Verify user_type is set correctly
5. Query room via `synapse_room_info`
6. Verify idempotency

**Artifacts:** None (verification via module queries)

### e2e

**Location:** GitHub Actions CI/CD
**Target:** Synapse in Docker (ephemeral)
**Tests:**
- Full integration test with Synapse homeserver
- User creation (`synapse_user`)
- Room creation (`synapse_room`)
- Event posting (`matrix_event`)
- Event verification via Admin API

**Workflow:** `.github/workflows/e2e.yml`

**Process:**
1. Create - Spin up Docker network and synapse container
2. Prepare - Configure Synapse, register admin user
3. Converge - Create bot, room, post event
4. Verify - Create verifier bot, join room, verify event
5. Destroy - Clean up containers

**Artifacts:** Event ID logged via debug output (check workflow logs)

### self-contained

**Location:** Local development
**Target:** None (mocked/dry-run)
**Tests:**
- Configuration file generation
- Template rendering
- No actual Matrix server required

**Use Case:** Test configuration logic without deploying to live server

**Artifacts:** Test config files in `~/.ansible/tmp/molecule.*/synapse_test/etc/`

## Running Tests

### Local Scenarios

```bash
# Default scenario (matrix_event)
molecule test

# Jack1 scenario (synapse_room/user)
molecule test -s jack1

# Self-contained (config generation)
molecule test -s self-contained

# Run without cleanup (for debugging)
molecule converge -s default
molecule verify -s default
# ... inspect results ...
molecule destroy -s default
```

### GitHub Actions

E2E test runs automatically on:
- Push to `main` or `test` branches
- Pull requests to `main`
- Manual trigger via workflow_dispatch

## Artifact Locations

All test artifacts are stored in ephemeral directories managed by Molecule:

- **Local tests:** `~/.ansible/tmp/molecule.<hash>.<scenario>/`
- **GitHub Actions:** `/home/runner/.cache/molecule/<collection>/<scenario>/`

Artifacts are **automatically cleaned up** after test completion (unless using `molecule converge` without destroy).

## Environment Variables

### Required for Local Tests

| Variable | Description | Example |
| --- | --- | --- |
| `MATRIX_HOMESERVER_URL` | Matrix homeserver URL | `https://matrix-web.jackaltx.com` |
| `MATRIX_ROOM_ID` | Test room ID or alias | `#solti-verify:jackaltx.com` |
| `MATRIX_SOLTI_LOGGER_TOKEN` | Bot access token | `syt_...` |
| `MATRIX_ADMIN_USER` | Admin user MXID | `@admin:jackaltx.com` |
| `MATRIX_ADMIN_TOKEN` | Admin access token | `syt_...` |
| `MATRIX_BOT_SOLTI_LOGGER_PASSWORD` | Bot password | `password` |

### Optional

| Variable | Description | Default |
| --- | --- | --- |
| `MOLECULE_PROJECT_DIRECTORY` | Project root | Auto-detected |
| `MOLECULE_EPHEMERAL_DIRECTORY` | Temp artifacts | `~/.ansible/tmp/molecule.*` |

## Notes

- **default** and **jack1** require live Matrix credentials
- **e2e** runs only in GitHub Actions with Docker
- **self-contained** can run without any external dependencies
- All scenarios use `molecule_ephemeral_directory` for artifacts (no repo pollution)
