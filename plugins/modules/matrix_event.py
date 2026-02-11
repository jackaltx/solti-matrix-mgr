#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for posting structured events to Matrix rooms.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: matrix_event
short_description: Post events to Matrix rooms (transport layer)
version_added: "0.1.0"
description:
    - Posts events to Matrix rooms using the Client-Server API
    - Acts as transport layer - wraps your data in Matrix event structure
    - Supports both room IDs (!xxx:server.com) and room aliases (#xxx:server.com)
    - Auto-generates human-readable bodies from event_data.schema (if present)
    - Always uses m.room.message for visibility in standard Matrix clients
options:
    homeserver_url:
        description: URL of the Matrix homeserver
        required: true
        type: str
    access_token:
        description: Bot or user access token for authentication
        required: true
        type: str
        no_log: true
    room_id:
        description: Room ID (!xxx:server.com) or alias (#xxx:server.com)
        required: true
        type: str
    event_data:
        description: Your event data dict (will be wrapped in Matrix structure)
        required: true
        type: dict
    state:
        description: Whether to post the event
        type: str
        choices: ['present', 'absent']
        default: present
    transaction_id:
        description: Optional explicit transaction ID for idempotency
        type: str
        required: false
    validate_certs:
        description: Validate SSL certificates
        type: bool
        default: true
notes:
    - Module extracts event_data.schema to generate human-readable body
    - Module wraps event_data in Matrix structure (msgtype/body/solti)
    - No validation - you control the structure completely
    - See docs/event-schemas.md for recommended structures (not enforced)
author:
    - SOLTI Contributors
'''

EXAMPLES = r'''
# Build your event data dict
- name: Build verification failure event
  set_fact:
    verify_event:
      schema: "verify.fail.v1"
      timestamp: "{{ ansible_date_time.iso8601 }}"
      source: "molecule/{{ ansible_distribution | lower }}/podman"
      distribution: "{{ ansible_distribution }}_{{ ansible_distribution_version }}"
      hostname: "{{ ansible_hostname }}"
      summary:
        total_services: 5
        failed_services: 2
        passed_services: 5
      services:
        loki: false
        influxdb: false
        telegraf: true
      failed_service_names:
        - loki
        - influxdb

# Post it - module wraps it in Matrix structure
- name: Post verification event
  jackaltx.solti_matrix_mgr.matrix_event:
    homeserver_url: "https://matrix-web.jackaltx.com"
    access_token: "{{ bot_token }}"
    room_id: "#solti-verify:jackaltx.com"
    event_data: "{{ verify_event }}"

# Module auto-generates body from event_data.schema:
#   Result: msgtype=m.text, body="❌ Verification FAILED: 2/5 services on rocky9_9.0"

# Any structure works - schema is optional
- name: Custom event structure
  jackaltx.solti_matrix_mgr.matrix_event:
    homeserver_url: "https://matrix-web.jackaltx.com"
    access_token: "{{ bot_token }}"
    room_id: "#solti-ops:jackaltx.com"
    event_data:
      message: "Deployment started"
      host: "fleur.lavnet.net"
      operator: "{{ ansible_user_id }}"

# No schema? Generic body
#   Result: msgtype=m.text, body="SOLTI Event"
'''

RETURN = r'''
event_id:
    description: Matrix event ID of the posted event
    returned: success
    type: str
    sample: "$abc123def456:jackaltx.com"
room_id:
    description: Room ID where event was posted
    returned: success
    type: str
    sample: "!NGwlzxqbkdXnRGKvEF:jackaltx.com"
transaction_id:
    description: Transaction ID used for the request
    returned: success
    type: str
    sample: "ansible-1707574800-abc12345"
event_type:
    description: Event type that was posted
    returned: success
    type: str
    sample: "com.solti.verify.fail"
'''

from ansible.module_utils.basic import AnsibleModule

# Import from collection's module_utils
try:
    from ansible_collections.jackaltx.solti_matrix_mgr.plugins.module_utils.matrix_client import (
        MatrixClientAPI,
        resolve_room_identifier
    )
    from ansible_collections.jackaltx.solti_matrix_mgr.plugins.module_utils.solti_event import (
        _generate_body
    )
except ImportError:
    # Fallback for local development
    from ansible.module_utils.matrix_client import MatrixClientAPI, resolve_room_identifier
    from ansible.module_utils.solti_event import _generate_body


def main():
    """Main module execution."""
    module = AnsibleModule(
        argument_spec=dict(
            homeserver_url=dict(type='str', required=True),
            access_token=dict(type='str', required=True, no_log=True),
            room_id=dict(type='str', required=True),
            event_data=dict(type='dict', required=True),
            state=dict(type='str', default='present', choices=['present', 'absent']),
            transaction_id=dict(type='str', required=False),
            validate_certs=dict(type='bool', default=True),
        ),
        supports_check_mode=True,
    )

    # Extract parameters
    homeserver_url = module.params['homeserver_url']
    access_token = module.params['access_token']
    room_id = module.params['room_id']
    event_data = module.params['event_data']
    state = module.params['state']
    transaction_id = module.params.get('transaction_id')
    validate_certs = module.params['validate_certs']

    # Skip if state is absent
    if state == 'absent':
        module.exit_json(changed=False, skipped=True, msg="State is absent, skipping event post")

    # Skip in check mode
    if module.check_mode:
        module.exit_json(changed=True, skipped=True, msg="Check mode, would post event")

    # Extract schema from event_data for body generation (if present)
    schema = event_data.get('schema', 'unknown')

    # Generate human-readable body
    body = _generate_body(schema, event_data)

    # Wrap event_data in Matrix structure
    event_content = {
        "msgtype": "m.text",
        "body": body,
        "solti": event_data
    }

    # Initialize API client
    try:
        api = MatrixClientAPI(module, homeserver_url, access_token, validate_certs)
    except Exception as e:
        module.fail_json(msg=f"Failed to initialize Matrix API client: {str(e)}")

    # Resolve room alias to ID if needed
    resolved_room_id = resolve_room_identifier(api, room_id)
    if not resolved_room_id:
        module.fail_json(
            msg=f"Failed to resolve room identifier: {room_id}",
            room_id=room_id
        )

    # Post event to Matrix (always use m.room.message for visibility)
    event_type = "m.room.message"

    try:
        result = api.send_event(
            room_id=resolved_room_id,
            event_type=event_type,
            content=event_content,
            transaction_id=transaction_id
        )

        if result['status_code'] == 200:
            module.exit_json(
                changed=True,
                event_id=result['body'].get('event_id'),
                room_id=resolved_room_id,
                transaction_id=transaction_id or api._generate_transaction_id(resolved_room_id, event_type),
                event_type=event_type,
                schema=schema,
                msg="Event posted successfully"
            )
        else:
            module.fail_json(
                msg=f"Failed to post event: HTTP {result['status_code']}",
                status_code=result['status_code'],
                body=result['body'],
                url=result['url']
            )

    except Exception as e:
        module.fail_json(msg=f"Exception posting event: {str(e)}")


if __name__ == '__main__':
    main()
