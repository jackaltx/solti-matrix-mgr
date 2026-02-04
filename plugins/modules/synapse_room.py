#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for managing Matrix/Synapse rooms via Admin API.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: synapse_room
short_description: Manage Matrix Synapse rooms via Admin API
version_added: "0.1.0"
description:
    - Query, block, or delete rooms on a Synapse homeserver.
    - Room creation uses the Client-Server API (not Admin API).
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
        description: Room ID (!room:server.com) or alias (#room:server.com)
        required: true
        type: str
    state:
        description: Desired state of the room
        type: str
        choices: ['present', 'absent', 'info']
        default: info
    purge:
        description: When state=absent, purge all room history
        type: bool
        default: true
    block:
        description: When state=absent, block future joins
        type: bool
        default: false
    new_room_user_id:
        description: When deleting, create replacement room owned by this user
        type: str
    message:
        description: Message to send before deleting room
        type: str
    validate_certs:
        description: Validate SSL certificates
        type: bool
        default: true
author:
    - Your Name (@yourhandle)
'''

EXAMPLES = r'''
- name: Get room information
  homelab.matrix.synapse_room:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    room_id: "!abcdef:example.com"
    state: info
  register: room_info

- name: Delete and purge a room
  homelab.matrix.synapse_room:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    room_id: "!spamroom:example.com"
    state: absent
    purge: true
    block: true
    message: "This room has been closed for policy violations."

- name: Delete room and create replacement
  homelab.matrix.synapse_room:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    room_id: "!oldroom:example.com"
    state: absent
    new_room_user_id: "@admin:example.com"
'''

RETURN = r'''
room:
    description: Room information from the server
    type: dict
    returned: success
    sample:
        room_id: "!abcdef:example.com"
        name: "Test Room"
        canonical_alias: "#test:example.com"
        joined_members: 5
delete_id:
    description: Deletion task ID (for async tracking)
    type: str
    returned: when state=absent
'''

import json
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url
from ansible_collections.jackaltx.solti_matrix_mgr.plugins.module_utils.matrix_api import (
    MatrixAdminAPI,
    get_room_info,
    delete_room,
)


def resolve_room_alias(module, homeserver_url, alias, validate_certs):
    """Resolve a room alias to room ID using Client-Server API."""
    # Remove leading # and encode
    alias_encoded = alias.replace('#', '%23').replace(':', '%3A')
    url = f"{homeserver_url}/_matrix/client/v3/directory/room/{alias_encoded}"
    
    response, info = fetch_url(module, url, method="GET", validate_certs=validate_certs)
    
    if info['status'] == 200:
        body = json.loads(response.read())
        return body.get('room_id')
    return None


def run_module():
    module_args = dict(
        homeserver_url=dict(type='str', required=True),
        access_token=dict(type='str', required=True, no_log=True),
        room_id=dict(type='str', required=True),
        state=dict(type='str', default='info', choices=['present', 'absent', 'info']),
        purge=dict(type='bool', default=True),
        block=dict(type='bool', default=False),
        new_room_user_id=dict(type='str'),
        message=dict(type='str'),
        validate_certs=dict(type='bool', default=True),
    )

    result = dict(
        changed=False,
        room={},
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    api = MatrixAdminAPI(
        module,
        module.params['homeserver_url'],
        module.params['access_token'],
        module.params['validate_certs'],
    )

    room_id = module.params['room_id']
    state = module.params['state']

    # Resolve alias if provided
    if room_id.startswith('#'):
        resolved = resolve_room_alias(
            module,
            module.params['homeserver_url'],
            room_id,
            module.params['validate_certs']
        )
        if resolved:
            room_id = resolved
        else:
            module.fail_json(msg=f"Could not resolve room alias: {room_id}")

    # Get current room state
    current_room = get_room_info(api, room_id)
    
    if state == 'info':
        if current_room and 'error' not in current_room:
            result['room'] = current_room
        elif current_room is None:
            module.fail_json(msg=f"Room not found: {room_id}")
        else:
            module.fail_json(msg=f"Failed to query room: {current_room}")
    
    elif state == 'absent':
        if current_room and 'error' not in current_room:
            if module.check_mode:
                result['changed'] = True
            else:
                # Build deletion request
                data = {
                    "purge": module.params['purge'],
                    "block": module.params['block'],
                }
                if module.params['new_room_user_id']:
                    data['new_room_user_id'] = module.params['new_room_user_id']
                if module.params['message']:
                    data['message'] = module.params['message']
                
                # Use v2 API for async deletion
                resp = api.delete(f"rooms/{room_id}", data=data, api_version="v2")
                
                if resp['status_code'] == 200:
                    result['changed'] = True
                    result['delete_id'] = resp['body'].get('delete_id')
                else:
                    module.fail_json(msg=f"Failed to delete room: {resp['body']}")
        else:
            # Room doesn't exist, nothing to do
            pass
    
    elif state == 'present':
        # Room creation would need Client-Server API, not Admin API
        # This is a placeholder - full implementation would use createRoom
        module.fail_json(msg="Room creation via this module is not yet implemented. Use matrix_room or the SDK.")

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
