# SOLTI Matrix Event Schemas

This document defines the standard event schemas used in the SOLTI system for posting structured events to Matrix rooms.

## Architecture Overview

SOLTI events use a layered approach separating transport (Matrix) from payload (SOLTI):

```yaml
# Matrix Transport Layer
event_type: m.room.message
room_id: #solti-verify:jackaltx.com

# Event Content (Matrix stores this)
content:
  # Human-readable (rendered by Matrix clients)
  msgtype: m.text
  body: "❌ Verification FAILED: loki on monitor11"

  # Machine-readable (processed by SOLTI tools)
  solti:
    schema: "verify.fail.v1"
    timestamp: "2026-02-11T10:30:00Z"
    source: "molecule/rocky9/podman"
    data:
      # Schema-specific fields
```

### Key Concepts

- **event_type**: Always `m.room.message` for visibility in standard Matrix clients
- **room_id**: Categorizes events (#solti-verify, #solti-deploys, etc.)
- **msgtype/body**: Human-readable summary (rendered by Element, etc.)
- **solti.schema**: Defines the structure of `solti.data` and enables dispatcher routing
- **solti.timestamp**: ISO 8601 timestamp (UTC)
- **solti.source**: Context about where the event originated (collection/distribution/scenario)
- **solti.data**: Schema-specific structured data

## Schema Versioning

All schemas use semantic versioning in the format `{category}.{name}.v{N}`:

- `verify.pass.v1` - Verification success schema, version 1
- `verify.fail.v1` - Verification failure schema, version 1

**Version Guidelines:**
- Increment version when adding required fields or changing field meanings
- Backward-compatible additions (new optional fields) can stay at same version
- Decoders should handle unknown fields gracefully

## Standard Schemas

### verify.pass.v1

**Purpose**: Posted when verification tests pass successfully

**Body Format**: `✅ Verification PASSED: {passed}/{total} services on {distribution}`

**Example Body**: `✅ Verification PASSED: 5/5 services on rocky9_9.0`

**Required Fields in `data`**:

| Field | Type | Description |
|-------|------|-------------|
| `distribution` | string | OS distribution name (e.g., `rocky9_9.0`, `debian12_12.1`) |
| `hostname` | string | Hostname where tests ran |
| `summary` | object | Test summary statistics |
| `summary.total_services` | integer | Total number of services tested |
| `summary.failed_services` | integer | Number of failed services (should be 0) |
| `summary.passed_services` | integer | Number of passed services |
| `services` | object | Service-level results (service_name → boolean) |
| `failed_service_names` | array | List of failed service names (empty for pass) |

**Optional Fields in `data`**:

| Field | Type | Description |
|-------|------|-------------|
| `context` | object | Additional context (collection, scenario, platform) |
| `context.collection` | string | Ansible collection name |
| `context.scenario` | string | Molecule scenario name |
| `context.platform` | string | Molecule platform name |

**Example**:

```yaml
solti:
  schema: "verify.pass.v1"
  timestamp: "2026-02-11T15:30:45Z"
  source: "molecule/rocky9/podman"
  data:
    distribution: "rocky9_9.0"
    hostname: "localhost"
    summary:
      total_services: 5
      failed_services: 0
      passed_services: 5
    services:
      alloy: true
      influxdb: true
      loki: true
      telegraf: true
      alert_notifier: true
    failed_service_names: []
    context:
      collection: "solti-monitoring"
      scenario: "podman"
      platform: "uut-ct0"
```

---

### verify.fail.v1

**Purpose**: Posted when verification tests fail

**Body Format**: `❌ Verification FAILED: {failed}/{total} services on {distribution}`

**Example Body**: `❌ Verification FAILED: 2/5 services on debian12_12.1`

**Required Fields in `data`**:

Same as `verify.pass.v1` (uses identical structure, different status)

**Example**:

```yaml
solti:
  schema: "verify.fail.v1"
  timestamp: "2026-02-11T15:32:10Z"
  source: "molecule/debian12/podman"
  data:
    distribution: "debian12_12.1"
    hostname: "localhost"
    summary:
      total_services: 5
      failed_services: 2
      passed_services: 3
    services:
      alloy: true
      influxdb: false
      loki: false
      telegraf: true
      alert_notifier: true
    failed_service_names:
      - influxdb
      - loki
    context:
      collection: "solti-monitoring"
      scenario: "podman"
      platform: "uut-ct1"
```

---

## Future Schemas (Planned)

### deploy.start.v1

**Purpose**: Posted when a service deployment begins

**Body Format**: `🚀 Deployment STARTED: {service} on {host}`

**Required Fields in `data`**:

| Field | Type | Description |
|-------|------|-------------|
| `service` | string | Service name (e.g., `loki`, `influxdb`) |
| `host` | string | Target hostname |
| `playbook` | string | Playbook name |
| `operator` | string | User initiating deployment |

**Example**:

```yaml
solti:
  schema: "deploy.start.v1"
  timestamp: "2026-02-11T16:00:00Z"
  source: "mylab/fleur"
  data:
    service: "alloy"
    host: "fleur.lavnet.net"
    playbook: "fleur-alloy.yml"
    operator: "lavender"
```

---

### deploy.complete.v1

**Purpose**: Posted when a service deployment completes

**Body Format**: `✅ Deployment COMPLETED: {service} on {host} (duration: {duration})`

**Required Fields in `data`**:

| Field | Type | Description |
|-------|------|-------------|
| `service` | string | Service name |
| `host` | string | Target hostname |
| `playbook` | string | Playbook name |
| `operator` | string | User who initiated deployment |
| `duration` | float | Deployment duration in seconds |
| `status` | string | `success` or `failed` |

**Optional Fields in `data`**:

| Field | Type | Description |
|-------|------|-------------|
| `error` | string | Error message if status=failed |

**Example**:

```yaml
solti:
  schema: "deploy.complete.v1"
  timestamp: "2026-02-11T16:02:30Z"
  source: "mylab/fleur"
  data:
    service: "alloy"
    host: "fleur.lavnet.net"
    playbook: "fleur-alloy.yml"
    operator: "lavender"
    duration: 150.3
    status: "success"
```

---

## Room Categories

Events should be posted to appropriate Matrix rooms based on category:

| Room | Purpose | Schemas |
|------|---------|---------|
| `#solti-verify:jackaltx.com` | Verification test results | `verify.pass.v1`, `verify.fail.v1` |
| `#solti-deploys:jackaltx.com` | Deployment events (future) | `deploy.start.v1`, `deploy.complete.v1` |
| `#solti-ops:jackaltx.com` | Operations discussion (future) | Human chat only |

---

## Adding New Schemas

To add a new event schema:

1. **Define the schema** in this document:
   - Choose appropriate category and name
   - Define required and optional fields
   - Specify body format template
   - Provide complete example

2. **Implement body generation** in `solti_event.py`:
   - Add case to `_generate_body()` function
   - Test body formatting with various data combinations

3. **Update decoder** in `matrix-view-events.py`:
   - Add case to `format_event()` dispatcher
   - Implement formatting function for rich display

4. **Test**:
   - Add test case to `test-matrix-event.yml`
   - Verify rendering in Element
   - Verify decoder output

5. **Document**:
   - Update this file
   - Update README.md with usage examples

---

## Schema Guidelines

When designing new schemas:

- **Keep `data` flat when possible**: Avoid deep nesting
- **Use consistent naming**: snake_case for field names
- **Include context**: Add `context` object for debugging info
- **Make bodies informative**: Include key data points in human-readable summary
- **Version explicitly**: Always include `.v1` suffix
- **Document thoroughly**: Required fields, types, examples

---

## Decoder Dispatch

The decoder (`matrix-view-events.py`) dispatches on `content.solti.schema`:

```python
def format_event(event):
    content = event.get('content', {})
    solti = content.get('solti', {})

    if not solti:
        return None  # Not a SOLTI event

    schema = solti.get('schema')
    data = solti.get('data', {})

    if schema == 'verify.fail.v1' or schema == 'verify.pass.v1':
        return format_verify_result(schema, data, solti)
    elif schema == 'deploy.start.v1':
        return format_deploy_start(data, solti)
    # ... dispatch on schema
```

Decoders should:
- Display schema metadata (schema, timestamp, source)
- Format `data` fields in human-readable layout
- Handle unknown fields gracefully (log but don't crash)
- Show the original `body` for comparison

---

## Version History

- **2026-02-11**: Initial version with `verify.pass.v1` and `verify.fail.v1`
