#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for querying Matrix/Synapse rooms via Admin API.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: synapse_room_info
short_description: Query Matrix Synapse rooms via Admin API
version_added: "0.1.0"
description:
    - List and filter rooms on a Synapse homeserver.
    - Uses the Synapse Admin API v1.
options:
    homeserver_url:
        description: URL of the Matrix homeserver
        required: true
        type: str
    access_token:
        description: Admin access token for authentication
        required: true
        type: str
        no_log: true
    room_id:
        description: Get specific room by ID
        type: str
    room_alias:
        description: Get specific room by alias (e.g., "my-room" or "#my-room:server.com")
        type: str
    search_term:
        description: Search rooms by name or topic
        type: str
    limit:
        description: Maximum number of rooms to return
        type: int
        default: 100
    validate_certs:
        description: Validate SSL certificates
        type: bool
        default: true
author:
    - Your Name (@yourhandle)
'''

EXAMPLES = r'''
- name: List all rooms
  jackaltx.solti_matrix_mgr.synapse_room_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"

- name: Get specific room by alias
  jackaltx.solti_matrix_mgr.synapse_room_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    room_alias: "test-room"

- name: Search rooms
  jackaltx.solti_matrix_mgr.synapse_room_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    search_term: "testing"
'''

RETURN = r'''
rooms:
    description: List of rooms matching the query
    type: list
    returned: success
    elements: dict
    sample:
        - room_id: "!abc123:example.com"
          name: "Test Room"
          canonical_alias: "#test-room:example.com"
          joined_members: 5
          joined_local_members: 3
          version: "6"
          creator: "@admin:example.com"
          encryption: null
          federatable: true
          public: false
total:
    description: Total number of rooms matching the query
    type: int
    returned: success
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.jackaltx.solti_matrix_mgr.plugins.module_utils.matrix_api import (
    MatrixAdminAPI,
)


def resolve_room_alias(api, room_alias, homeserver):
    """Resolve room alias to room ID."""
    # Normalize alias format
    if not room_alias.startswith('#'):
        room_alias = f"#{room_alias}:{homeserver}"
    elif ':' not in room_alias:
        room_alias = f"{room_alias}:{homeserver}"

    # URL encode the alias
    import urllib.parse
    encoded_alias = urllib.parse.quote(room_alias, safe='')

    resp = api.get(f"directory/room/{encoded_alias}", api_version="client")

    if resp['status_code'] == 200:
        return resp['body'].get('room_id')
    return None


def get_room_details(api, room_id):
    """Get detailed room information."""
    resp = api.get(f"rooms/{room_id}")

    if resp['status_code'] == 200:
        return resp['body']
    return None


def run_module():
    module_args = dict(
        homeserver_url=dict(type='str', required=True),
        access_token=dict(type='str', required=True, no_log=True),
        room_id=dict(type='str'),
        room_alias=dict(type='str'),
        search_term=dict(type='str'),
        limit=dict(type='int', default=100),
        validate_certs=dict(type='bool', default=True),
    )

    result = dict(
        changed=False,
        rooms=[],
        total=0,
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        mutually_exclusive=[
            ['room_id', 'room_alias'],
        ],
    )

    api = MatrixAdminAPI(
        module,
        module.params['homeserver_url'],
        module.params['access_token'],
        module.params['validate_certs'],
    )

    # Extract homeserver domain from URL
    homeserver = module.params['homeserver_url'].split('//')[-1].split(':')[0]

    # If specific room_id provided
    if module.params['room_id']:
        room = get_room_details(api, module.params['room_id'])
        if room:
            result['rooms'] = [room]
            result['total'] = 1
        else:
            module.fail_json(msg=f"Room not found: {module.params['room_id']}")

    # If room_alias provided, resolve it first
    elif module.params['room_alias']:
        room_id = resolve_room_alias(api, module.params['room_alias'], homeserver)
        if room_id:
            room = get_room_details(api, room_id)
            if room:
                result['rooms'] = [room]
                result['total'] = 1
            else:
                module.fail_json(msg=f"Room found but details unavailable: {room_id}")
        else:
            module.fail_json(msg=f"Room alias not found: {module.params['room_alias']}")

    # List all rooms
    else:
        params = {
            'limit': module.params['limit'],
        }

        if module.params['search_term']:
            params['search_term'] = module.params['search_term']

        # Build query string
        query_params = '&'.join([f"{k}={v}" for k, v in params.items()])
        endpoint = f"rooms?{query_params}"

        resp = api.get(endpoint)

        if resp['status_code'] != 200:
            module.fail_json(msg=f"Failed to list rooms: {resp['body']}")

        rooms = resp['body'].get('rooms', [])
        result['rooms'] = rooms
        result['total'] = resp['body'].get('total', len(rooms))

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
