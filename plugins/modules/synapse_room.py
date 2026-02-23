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
    - Supports convenience params (admins/moderators) for standardized
      room creation with proper power levels.
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
        choices: ['present', 'absent', 'info', 'members', 'join']
        default: info
    user_id:
        description: User ID to force-join into the room (used with state=join, requires admin token)
        type: str
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
    room_name:
        description: Display name for the room (used with state=present)
        type: str
    room_alias_name:
        description: >-
            Local part of the room alias, e.g. 'my-room' creates
            '#my-room:server.com' (used with state=present)
        type: str
    topic:
        description: Room topic (used with state=present)
        type: str
    invite:
        description: >-
            List of user IDs to invite after room creation.
            Users listed in admins/moderators are automatically invited.
        type: list
        elements: str
        default: []
    admins:
        description: >-
            List of user IDs to set as room admins (power level 100).
            These users are automatically added to the invite list.
            The creating user (access_token owner) is always admin.
        type: list
        elements: str
        default: []
    moderators:
        description: >-
            List of user IDs to set as room moderators (power level 50).
            These users are automatically added to the invite list.
        type: list
        elements: str
        default: []
    power_level_content_override:
        description: >-
            Raw power_level_content_override dict passed directly to the
            createRoom API. Takes precedence over admins/moderators params.
            Use this for non-standard power level configurations.
        type: dict
    preset:
        description: >-
            Room creation preset. private_chat sets invite-only with
            shared history. public_chat allows anyone to join.
        type: str
        choices: ['private_chat', 'public_chat', 'trusted_private_chat']
        default: private_chat
    guest_access:
        description: Whether guests can join the room
        type: str
        choices: ['can_join', 'forbidden']
        default: forbidden
    message:
        description: Message to send before deleting room
        type: str
    validate_certs:
        description: Validate SSL certificates
        type: bool
        default: true
author:
    - SOLTI Contributors
'''

EXAMPLES = r'''
- name: Create room with bot as admin and human moderator
  jackaltx.solti_matrix_mgr.synapse_room:
    homeserver_url: "https://matrix-web.jackaltx.com"
    access_token: "{{ bot_token }}"
    room_id: "#solti-deploys:jackaltx.com"
    room_name: "SOLTI Deployment Events"
    room_alias_name: "solti-deploys"
    topic: "Automated deployment notifications"
    state: present
    admins:
      - "@solti-logger:jackaltx.com"
    moderators:
      - "@jackal:jackaltx.com"
  register: room_result

- name: Create room with raw power level override
  jackaltx.solti_matrix_mgr.synapse_room:
    homeserver_url: "https://matrix-web.jackaltx.com"
    access_token: "{{ bot_token }}"
    room_id: "#custom-room:jackaltx.com"
    room_name: "Custom Power Levels"
    room_alias_name: "custom-room"
    state: present
    power_level_content_override:
      users:
        "@solti-logger:jackaltx.com": 100
        "@jackal:jackaltx.com": 75
      users_default: 0
      events_default: 10

- name: Get room information
  jackaltx.solti_matrix_mgr.synapse_room:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    room_id: "!abcdef:example.com"
    state: info
  register: room_info

- name: Delete and purge a room
  jackaltx.solti_matrix_mgr.synapse_room:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    room_id: "!spamroom:example.com"
    state: absent
    purge: true
    block: true
    message: "This room has been closed for policy violations."
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
    get_room_members,
    delete_room,
)


def resolve_room_alias(module, homeserver_url, access_token, alias):
    """Resolve a room alias to room ID using Client-Server API."""
    try:
        from urllib.parse import quote as url_quote
    except ImportError:
        from urllib import quote as url_quote

    # URL-encode the full alias (#room:server.com → %23room%3Aserver.com)
    alias_encoded = url_quote(alias, safe='')
    url = f"{homeserver_url}/_matrix/client/v3/directory/room/{alias_encoded}"

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    response, info = fetch_url(module, url, method="GET", headers=headers)

    if info.get('status') == 200 and response:
        try:
            body = json.loads(response.read())
            return body.get('room_id')
        except (ValueError, AttributeError):
            pass
    return None


def get_whoami(module, homeserver_url, access_token):
    """Get the authenticated user's ID via Client-Server API."""
    url = f"{homeserver_url}/_matrix/client/v3/account/whoami"
    headers = {"Authorization": f"Bearer {access_token}"}
    response, info = fetch_url(module, url, method="GET", headers=headers)
    if info.get('status') == 200 and response:
        try:
            body = json.loads(response.read())
            return body.get('user_id')
        except (ValueError, AttributeError):
            pass
    return None


def create_room(module, homeserver_url, access_token, data):
    """Create a room using the Client-Server API."""
    url = f"{homeserver_url}/_matrix/client/v3/createRoom"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response, info = fetch_url(
        module, url, method="POST",
        headers=headers, data=json.dumps(data),
    )

    status_code = info.get('status', -1)
    body = {}

    if response:
        try:
            body = json.loads(response.read())
        except (ValueError, AttributeError):
            pass

    if not body and 'body' in info:
        try:
            body = json.loads(info['body'])
        except (ValueError, TypeError):
            body = {'raw': info.get('body', '')}

    # Include status and any error message from fetch_url
    if not body and status_code < 0:
        body = {'error': info.get('msg', 'Unknown error'), 'url': url}

    return {'status_code': status_code, 'body': body, 'url': url}


def run_module():
    module_args = dict(
        homeserver_url=dict(type='str', required=True),
        access_token=dict(type='str', required=True, no_log=True),
        admin_user=dict(type='str', required=False),
        admin_password=dict(type='str', required=False, no_log=True),
        room_id=dict(type='str', required=True),
        state=dict(type='str', default='info', choices=['present', 'absent', 'info', 'members', 'join']),
        user_id=dict(type='str'),
        purge=dict(type='bool', default=True),
        block=dict(type='bool', default=False),
        room_name=dict(type='str'),
        room_alias_name=dict(type='str'),
        topic=dict(type='str'),
        invite=dict(type='list', elements='str', default=[]),
        admins=dict(type='list', elements='str', default=[]),
        moderators=dict(type='list', elements='str', default=[]),
        power_level_content_override=dict(type='dict'),
        preset=dict(type='str', default='private_chat',
                    choices=['private_chat', 'public_chat', 'trusted_private_chat']),
        guest_access=dict(type='str', default='forbidden',
                          choices=['can_join', 'forbidden']),
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
        user_id=module.params.get('admin_user'),
        password=module.params.get('admin_password'),
    )

    room_id = module.params['room_id']
    state = module.params['state']

    # Resolve alias if provided
    original_room_id = room_id
    alias_resolved = False
    if room_id.startswith('#'):
        resolved = resolve_room_alias(
            module,
            module.params['homeserver_url'],
            module.params['access_token'],
            room_id,
        )
        if resolved:
            room_id = resolved
            alias_resolved = True
        elif state not in ('present', 'absent', 'join'):
            module.fail_json(msg=f"Could not resolve room alias: {room_id}")

    # Get current room state
    # If alias resolved, the room definitely exists. Try Admin API for details,
    # but don't fail if the token lacks admin privileges.
    current_room = None
    if not room_id.startswith('#'):
        current_room = get_room_info(api, room_id)
        # If Admin API failed but alias resolved, room still exists
        if (current_room is None or (isinstance(current_room, dict) and 'error' in current_room)) and alias_resolved:
            current_room = {'room_id': room_id, 'resolved_from_alias': True}

    if state == 'info':
        if current_room and 'error' not in current_room:
            result['room'] = current_room
        elif current_room is None:
            module.fail_json(msg=f"Room not found: {room_id}")
        else:
            module.fail_json(msg=f"Failed to query room: {current_room}")

    elif state == 'members':
        members = get_room_members(api, room_id)
        if members and 'error' not in members:
            result['members'] = members
        elif members is None:
            module.fail_json(msg=f"Room not found: {room_id}")
        else:
            module.fail_json(msg=f"Failed to query room members: {members}")

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

    elif state == 'join':
        # Join room using the Client-Server API.
        # The access_token owner is the user who joins.
        # For invite-only rooms, the user must have a pending invite first
        # (use invite param in state=present, or invite separately).
        if module.check_mode:
            result['changed'] = True
        else:
            # Use api._request to hit Client-Server API with self-healing
            # We must use CLIENT_API_BASE instead of SYNAPSE_API_BASE
            endpoint = f"rooms/{room_id}/join"
            resp = api._request("POST", endpoint, data={}, api_version="client")

            if resp['status_code'] == 200:
                result['changed'] = True
                result['room'] = resp['body']
            else:
                module.fail_json(msg=f"Failed to join room: {resp['body']}")

    elif state == 'present':
        if current_room and 'error' not in current_room:
            # Room already exists
            result['room'] = current_room
        else:
            if module.check_mode:
                result['changed'] = True
            else:
                preset = module.params['preset']
                data = {
                    "visibility": "private" if preset != "public_chat" else "public",
                    "preset": preset,
                }
                if module.params['room_name']:
                    data['name'] = module.params['room_name']
                if module.params['room_alias_name']:
                    data['room_alias_name'] = module.params['room_alias_name']
                if module.params['topic']:
                    data['topic'] = module.params['topic']

                # Determine the creating user so we can exclude from invites
                creator = get_whoami(module, module.params['homeserver_url'],
                                    module.params['access_token'])

                # Build invite list: explicit + admins + moderators (deduplicated)
                # Exclude the creator — they're already in the room
                invite_set = set(module.params['invite'] or [])
                admins = module.params['admins'] or []
                moderators = module.params['moderators'] or []
                invite_set.update(admins)
                invite_set.update(moderators)
                if creator:
                    invite_set.discard(creator)
                if invite_set:
                    data['invite'] = list(invite_set)

                # Build power_level_content_override
                if module.params['power_level_content_override']:
                    # Raw override takes precedence
                    data['power_level_content_override'] = module.params['power_level_content_override']
                elif admins or moderators:
                    # Build from convenience params
                    users_power = {}
                    for user in admins:
                        users_power[user] = 100
                    for user in moderators:
                        users_power[user] = 50
                    data['power_level_content_override'] = {
                        "users": users_power,
                        "users_default": 0,
                    }

                # Guest access (initial_state event)
                guest_access = module.params['guest_access']
                if guest_access:
                    data.setdefault('initial_state', []).append({
                        "type": "m.room.guest_access",
                        "state_key": "",
                        "content": {"guest_access": guest_access},
                    })

                resp = create_room(
                    module,
                    module.params['homeserver_url'],
                    module.params['access_token'],
                    data,
                )

                if resp['status_code'] == 200:
                    result['changed'] = True
                    result['room'] = resp['body']
                    result['power_levels_applied'] = 'power_level_content_override' in data
                else:
                    module.fail_json(
                        msg=f"Failed to create room: HTTP {resp['status_code']}",
                        status_code=resp['status_code'],
                        response=resp['body'],
                        url=resp.get('url', ''),
                    )

    # Return updated token if re-authentication occurred
    result['access_token'] = api.access_token
    result['reauthenticated'] = api.reauthenticated

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
