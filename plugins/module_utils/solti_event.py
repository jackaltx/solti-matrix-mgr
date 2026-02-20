"""
SOLTI Event Structure Helpers

Provides utilities for building Matrix events with SOLTI-specific structure:
- Layer 1 (Transport): msgtype == "com.solti.event" (machine-only)
- Layer 2 (Envelope):  solti.{schema, timestamp, source, data}
- Layer 3 (Content):   schema-specific data payload

The bot (matrix-bot-nio.py) constructs human-readable summaries from the
structured data — senders do not generate human-readable bodies.

See solti-matrix-mgr/docs/event-schemas.md for schema definitions.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import time
from datetime import datetime


def create_solti_event(schema, data, source=None):
    """
    Build event content with SOLTI structure.

    Creates a Matrix event content dict with both human-readable (msgtype/body)
    and machine-readable (solti) components.

    Args:
        schema (str): Schema identifier (e.g., "verify.fail.v1")
        data (dict): Schema-specific payload data
        source (str, optional): Source context (e.g., "molecule/rocky9/podman")

    Returns:
        dict: Event content ready for matrix_event module

    Example:
        >>> content = create_solti_event(
        ...     schema="verify.fail.v1",
        ...     data={
        ...         "distribution": "rocky9_9.0",
        ...         "summary": {"failed_services": 2, "total_services": 5},
        ...         ...
        ...     },
        ...     source="molecule/rocky9/podman"
        ... )
        >>> # content now has msgtype, body, and solti fields
    """
    return {
        "msgtype": "com.solti.event",
        "body": f"SOLTI event: {schema}",
        "solti": {
            "schema": schema,
            "timestamp": _iso_timestamp(),
            "source": source or "unknown",
            "data": data
        }
    }


def _generate_body(schema, data):
    """
    Generate human-readable body from schema and data.

    Args:
        schema (str): Schema identifier
        data (dict): Schema-specific data

    Returns:
        str: Human-readable message for Matrix clients

    Note:
        Falls back to generic format if schema unknown.
    """
    if schema == "verify.fail.v1":
        return _body_verify_fail(data)
    elif schema == "verify.pass.v1":
        return _body_verify_pass(data)
    elif schema == "deploy.start.v1":
        return _body_deploy_start(data)
    elif schema == "deploy.complete.v1":
        return _body_deploy_complete(data)
    else:
        # Generic fallback for unknown schemas
        return f"📋 SOLTI Event: {schema}"


def _body_verify_fail(data):
    """
    Generate body for verify.fail.v1 schema.

    Format: "❌ Verification FAILED: {failed}/{total} services on {distribution}"
    """
    summary = data.get('summary', {})
    failed = summary.get('failed_services', 0)
    total = summary.get('total_services', 0)
    distribution = data.get('distribution', 'unknown')

    return f"❌ Verification FAILED: {failed}/{total} services on {distribution}"


def _body_verify_pass(data):
    """
    Generate body for verify.pass.v1 schema.

    Format: "✅ Verification PASSED: {passed}/{total} services on {distribution}"
    """
    summary = data.get('summary', {})
    passed = summary.get('passed_services', 0)
    total = summary.get('total_services', 0)
    distribution = data.get('distribution', 'unknown')

    return f"✅ Verification PASSED: {passed}/{total} services on {distribution}"


def _body_deploy_start(data):
    """
    Generate body for deploy.start.v1 schema.

    Format: "🚀 Deployment STARTED: {service} on {host}"
    """
    service = data.get('service', 'unknown')
    host = data.get('host', 'unknown')

    return f"🚀 Deployment STARTED: {service} on {host}"


def _body_deploy_complete(data):
    """
    Generate body for deploy.complete.v1 schema.

    Format: "✅ Deployment COMPLETED: {service} on {host} (duration: {duration}s)"
            or "❌ Deployment FAILED: {service} on {host}"
    """
    service = data.get('service', 'unknown')
    host = data.get('host', 'unknown')
    status = data.get('status', 'unknown')
    duration = data.get('duration', 0)

    if status == 'success':
        return f"✅ Deployment COMPLETED: {service} on {host} (duration: {duration:.1f}s)"
    elif status == 'failed':
        return f"❌ Deployment FAILED: {service} on {host}"
    else:
        return f"📋 Deployment {status.upper()}: {service} on {host}"


def _iso_timestamp():
    """
    Generate ISO 8601 timestamp in UTC.

    Returns:
        str: Timestamp in format "2026-02-11T15:30:45Z"
    """
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_schema_data(schema, data):
    """
    Validate that data contains required fields for schema.

    Args:
        schema (str): Schema identifier
        data (dict): Data to validate

    Returns:
        tuple: (bool, list) - (is_valid, list_of_missing_fields)

    Example:
        >>> valid, missing = validate_schema_data("verify.fail.v1", data)
        >>> if not valid:
        ...     print(f"Missing fields: {missing}")
    """
    required_fields = _get_required_fields(schema)
    missing_fields = []

    for field_path in required_fields:
        if not _has_nested_field(data, field_path):
            missing_fields.append(field_path)

    return (len(missing_fields) == 0, missing_fields)


def _get_required_fields(schema):
    """
    Get list of required field paths for a schema.

    Args:
        schema (str): Schema identifier

    Returns:
        list: List of required field paths (supports dot notation for nested)
    """
    if schema in ["verify.fail.v1", "verify.pass.v1"]:
        return [
            "distribution",
            "hostname",
            "summary",
            "summary.total_services",
            "summary.failed_services",
            "summary.passed_services",
            "services",
            "failed_service_names"
        ]
    elif schema == "deploy.start.v1":
        return [
            "service",
            "host",
            "playbook",
            "operator"
        ]
    elif schema == "deploy.complete.v1":
        return [
            "service",
            "host",
            "playbook",
            "operator",
            "duration",
            "status"
        ]
    else:
        # Unknown schema - no validation
        return []


def _has_nested_field(data, field_path):
    """
    Check if nested field exists in data.

    Args:
        data (dict): Data dictionary
        field_path (str): Field path with dots (e.g., "summary.total_services")

    Returns:
        bool: True if field exists, False otherwise
    """
    parts = field_path.split('.')
    current = data

    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]

    return True
