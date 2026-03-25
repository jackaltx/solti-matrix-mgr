#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for declarative Matrix configuration management.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: matrix_config
short_description: Declarative Matrix configuration (users + rooms)
version_added: "0.2.0"
description:
    - Manage Matrix users and rooms declaratively
    - Query first, create/update only what's needed (idempotent)
    - Never deletes resources (additive only)
    - Verifies only resources in the provided config
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
    domain:
        description: Matrix domain (e.g., jackaltx.com)
        required: true
        type: str
    users:
        description: List of users to ensure exist
        type: list
        elements: dict
        default: []
        suboptions:
            user_id:
                description: User ID without domain (e.g., "@admin")
                required: true
                type: str
            displayname:
                description: Display name
                type: str
            password:
                description: Password (only used on creation)
                type: str
                no_log: true
            admin:
                description: Admin privileges
                type: bool
                default: false
            ratelimit_override:
                description: Rate limit override
                type: dict
    rooms:
        description: List of rooms to ensure exist
        type: list
        elements: dict
        default: []
        suboptions:
            alias:
                description: Room alias without # or domain
                required: true
                type: str
            name:
                description: Room name
                type: str
            topic:
                description: Room topic
                type: str
            encrypted:
                description: Enable encryption
                type: bool
                default: false
            members:
                description: Room members to invite
                type: list
                elements: dict
            retention:
                description: Message retention policy (auto-delete old messages)
                type: dict
                suboptions:
                    max_lifetime_days:
                        description: Delete messages after N days
                        type: int
                    min_lifetime_days:
                        description: Keep messages at least N days
                        type: int
    validate_certs:
        description: Validate SSL certificates
        type: bool
        default: true
author:
    - Claude & Jackal
'''

EXAMPLES = r'''
- name: Apply Matrix configuration
  jackaltx.solti_matrix_mgr.matrix_config:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    domain: "example.com"
    users:
      - user_id: "@admin"
        displayname: "Admin"
        password: "{{ admin_pass }}"
        admin: true
      - user_id: "@jackal"
        displayname: "Jackal"
        password: "{{ jackal_pass }}"
    rooms:
      - alias: "team"
        name: "Team Chat"
        encrypted: true
        members:
          - user_id: "@jackal"
            power_level: 100
  register: result

- debug:
    msg: "{{ result.summary }}"
'''

RETURN = r'''
changed:
    description: Whether any changes were made
    type: bool
    returned: always
users:
    description: User operation results
    type: list
    returned: always
    elements: dict
    sample:
        - user: "@admin:example.com"
          action: created
        - user: "@jackal:example.com"
          action: unchanged
rooms:
    description: Room operation results
    type: list
    returned: always
    elements: dict
    sample:
        - alias: "#team:example.com"
          action: created
          members_invited: ["@jackal"]
summary:
    description: Summary of changes
    type: dict
    returned: always
    sample:
        users_created: 1
        users_updated: 0
        users_unchanged: 1
        rooms_created: 1
        rooms_unchanged: 0
'''

import json
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url
try:
    from urllib.parse import quote
except ImportError:
    from urllib import quote


def query_user(module, homeserver_url, access_token, user_id):
    """Query if user exists and get properties"""
    url = f"{homeserver_url}/_synapse/admin/v2/users/{user_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    resp, info = fetch_url(module, url, headers=headers, method="GET")

    if info['status'] == 200:
        return json.loads(resp.read())
    elif info['status'] == 404:
        return None
    else:
        module.fail_json(msg=f"Failed to query user {user_id}: {info}")


def create_user(module, homeserver_url, access_token, user_id, user_config):
    """Create a new user"""
    url = f"{homeserver_url}/_synapse/admin/v2/users/{user_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    body = {
        "displayname": user_config.get('displayname', ''),
        "admin": user_config.get('admin', False),
    }

    if user_config.get('password'):
        body['password'] = user_config['password']

    if user_config.get('ratelimit_override'):
        body['user_type'] = None  # Required for ratelimit override

    resp, info = fetch_url(
        module, url, headers=headers, method="PUT",
        data=json.dumps(body)
    )

    if info['status'] not in [200, 201]:
        module.fail_json(msg=f"Failed to create user {user_id}: {info}")

    # Set rate limit override if specified
    if user_config.get('ratelimit_override'):
        set_ratelimit(module, homeserver_url, access_token, user_id, user_config['ratelimit_override'])

    return True


def update_user(module, homeserver_url, access_token, user_id, user_config, current):
    """Update existing user properties (NOT password)"""
    url = f"{homeserver_url}/_synapse/admin/v2/users/{user_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    body = {}
    changed_fields = []

    if user_config.get('displayname') and user_config['displayname'] != current.get('displayname'):
        body['displayname'] = user_config['displayname']
        changed_fields.append('displayname')

    if user_config.get('admin', False) != current.get('admin', False):
        body['admin'] = user_config['admin']
        changed_fields.append('admin')

    if body:
        resp, info = fetch_url(
            module, url, headers=headers, method="PUT",
            data=json.dumps(body)
        )
        if info['status'] not in [200, 201]:
            module.fail_json(msg=f"Failed to update user {user_id}: {info}")

    return changed_fields


def set_ratelimit(module, homeserver_url, access_token, user_id, ratelimit):
    """Set rate limit override for user"""
    url = f"{homeserver_url}/_synapse/admin/v1/users/{user_id}/override_ratelimit"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    body = {
        "messages_per_second": ratelimit.get('messages_per_second', 0),
        "burst_count": ratelimit.get('burst_count', 0)
    }

    resp, info = fetch_url(
        module, url, headers=headers, method="POST",
        data=json.dumps(body)
    )

    if info['status'] not in [200, 201]:
        module.fail_json(msg=f"Failed to set ratelimit for {user_id}: {info}")


def ensure_user(module, homeserver_url, access_token, domain, user_config):
    """Ensure user exists and matches config"""
    user_id_short = user_config['user_id']
    if not user_id_short.startswith('@'):
        user_id_short = f"@{user_id_short}"

    user_id = f"{user_id_short}:{domain}"

    # Query current state
    current = query_user(module, homeserver_url, access_token, user_id)

    if current is None:
        # User doesn't exist - create
        create_user(module, homeserver_url, access_token, user_id, user_config)
        return {'user': user_id, 'action': 'created', 'changed': True}

    # User exists - check for updates
    changed_fields = update_user(module, homeserver_url, access_token, user_id, user_config, current)

    if changed_fields:
        return {'user': user_id, 'action': 'updated', 'fields': changed_fields, 'changed': True}

    return {'user': user_id, 'action': 'unchanged', 'changed': False}


def query_room(module, homeserver_url, access_token, room_alias):
    """Query if room exists"""
    # URL encode the room alias
    encoded_alias = quote(room_alias, safe='')
    url = f"{homeserver_url}/_matrix/client/v3/directory/room/{encoded_alias}"
    headers = {"Authorization": f"Bearer {access_token}"}

    resp, info = fetch_url(module, url, headers=headers, method="GET")

    if info['status'] == 200:
        data = json.loads(resp.read())
        return data.get('room_id')
    elif info['status'] == 404:
        return None
    else:
        return None  # Graceful degradation


def create_room(module, homeserver_url, access_token, domain, room_config):
    """Create a new room"""
    url = f"{homeserver_url}/_matrix/client/v3/createRoom"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    alias_short = room_config['alias']
    if alias_short.startswith('#'):
        alias_short = alias_short[1:]

    body = {
        "room_alias_name": alias_short,
        "name": room_config.get('name', alias_short),
        "preset": "private_chat",
        "visibility": "private",
    }

    if room_config.get('topic'):
        body['topic'] = room_config['topic']

    if room_config.get('encrypted', False):
        body['initial_state'] = [{
            "type": "m.room.encryption",
            "state_key": "",
            "content": {"algorithm": "m.megolm.v1.aes-sha2"}
        }]

    resp, info = fetch_url(
        module, url, headers=headers, method="POST",
        data=json.dumps(body)
    )

    if info['status'] not in [200, 201]:
        return None

    data = json.loads(resp.read())
    return data.get('room_id')


def invite_to_room(module, homeserver_url, access_token, room_id, user_id):
    """Invite user to room. Returns status code."""
    url = f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/invite"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    body = {"user_id": user_id}

    resp, info = fetch_url(
        module, url, headers=headers, method="POST",
        data=json.dumps(body)
    )

    # Return status code so caller can differentiate
    # 200 = invited, 403 = already in room, 429 = rate limit
    return info['status']


def set_retention_policy(module, homeserver_url, access_token, room_id, retention):
    """Set m.room.retention state event for auto-expiry of messages"""
    if not retention:
        return False

    # Build retention content (convert days to milliseconds)
    content = {}

    if 'max_lifetime_days' in retention:
        content['max_lifetime'] = retention['max_lifetime_days'] * 86400000

    if 'min_lifetime_days' in retention:
        content['min_lifetime'] = retention['min_lifetime_days'] * 86400000

    if not content:
        return False

    # Set the retention state event
    url = f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/state/m.room.retention"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    resp, info = fetch_url(
        module, url, headers=headers, method="PUT",
        data=json.dumps(content)
    )

    if info['status'] not in [200, 201]:
        module.fail_json(msg=f"Failed to set retention for room {room_id}: {info}")

    return True


def get_room_members(module, homeserver_url, access_token, room_id):
    """Get list of room members (both joined and invited)"""
    members = []

    # Get joined members
    url = f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/joined_members"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp, info = fetch_url(module, url, headers=headers, method="GET")

    if info['status'] == 200:
        data = json.loads(resp.read())
        members.extend(list(data.get('joined', {}).keys()))

    # Also check for invited members via room state
    # Get m.room.member events to see invites
    url2 = f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/state"
    resp2, info2 = fetch_url(module, url2, headers=headers, method="GET")

    if info2['status'] == 200:
        data2 = json.loads(resp2.read())
        # Look for m.room.member events with membership=invite
        for event in data2:
            if event.get('type') == 'm.room.member':
                if event.get('content', {}).get('membership') == 'invite':
                    # state_key is the user_id for member events
                    invited_user = event.get('state_key')
                    if invited_user and invited_user not in members:
                        members.append(invited_user)

    return members


def ensure_room(module, homeserver_url, access_token, domain, room_config):
    """Ensure room exists and has correct members"""
    alias_short = room_config['alias']
    if not alias_short.startswith('#'):
        alias_short = f"#{alias_short}"

    room_alias = f"{alias_short}:{domain}"

    # Query current state
    room_id = query_room(module, homeserver_url, access_token, room_alias)

    if room_id is None:
        # Room doesn't exist - create
        room_id = create_room(module, homeserver_url, access_token, domain, room_config)

        if not room_id:
            return {'alias': room_alias, 'action': 'failed', 'changed': False}

        # Set retention policy if configured
        retention_set = False
        if 'retention' in room_config:
            retention_set = set_retention_policy(
                module, homeserver_url, access_token, room_id, room_config['retention']
            )

        # Invite members
        members_invited = []
        for member in room_config.get('members', []):
            user_id_short = member['user_id']
            if not user_id_short.startswith('@'):
                user_id_short = f"@{user_id_short}"
            user_id = f"{user_id_short}:{domain}"

            status = invite_to_room(module, homeserver_url, access_token, room_id, user_id)
            # 200=invited, 403=already in room, 429=rate limit - all acceptable
            if status in [200, 403, 429]:
                members_invited.append(user_id_short)

        result = {
            'alias': room_alias,
            'action': 'created',
            'members_invited': members_invited,
            'changed': True
        }
        if retention_set:
            result['retention_set'] = True

        return result

    # Room exists - check members
    current_members = get_room_members(module, homeserver_url, access_token, room_id)
    desired_members = []

    for member in room_config.get('members', []):
        user_id_short = member['user_id']
        if not user_id_short.startswith('@'):
            user_id_short = f"@{user_id_short}"
        desired_members.append(f"{user_id_short}:{domain}")

    missing_members = set(desired_members) - set(current_members)

    # Debug: track what we found
    debug_info = {
        'current_members': current_members,
        'desired_members': desired_members,
        'missing_members': list(missing_members)
    }

    if missing_members:
        members_added = []
        for user_id in missing_members:
            status = invite_to_room(module, homeserver_url, access_token, room_id, user_id)
            # Only count as added if actually invited (not already in room)
            if status == 200:
                members_added.append(user_id.split(':')[0])

        # If we added members, report the change
        if members_added:
            return {
                'alias': room_alias,
                'action': 'members_added',
                'members_added': members_added,
                'debug': debug_info,
                'changed': True
            }

    return {
        'alias': room_alias,
        'action': 'unchanged',
        'debug': debug_info if 'debug_info' in locals() else {},
        'changed': False
    }


def run_module():
    module_args = dict(
        homeserver_url=dict(type='str', required=True),
        access_token=dict(type='str', required=True, no_log=True),
        domain=dict(type='str', required=True),
        users=dict(type='list', elements='dict', default=[]),
        rooms=dict(type='list', elements='dict', default=[]),
        validate_certs=dict(type='bool', default=True),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    homeserver_url = module.params['homeserver_url']
    access_token = module.params['access_token']
    domain = module.params['domain']
    users_config = module.params['users']
    rooms_config = module.params['rooms']

    user_results = []
    room_results = []
    changed = False

    # Process users
    for user_config in users_config:
        result = ensure_user(module, homeserver_url, access_token, domain, user_config)
        user_results.append(result)
        if result['changed']:
            changed = True

    # Process rooms
    for room_config in rooms_config:
        result = ensure_room(module, homeserver_url, access_token, domain, room_config)
        room_results.append(result)
        if result['changed']:
            changed = True

    # Generate summary
    summary = {
        'users_created': len([r for r in user_results if r['action'] == 'created']),
        'users_updated': len([r for r in user_results if r['action'] == 'updated']),
        'users_unchanged': len([r for r in user_results if r['action'] == 'unchanged']),
        'rooms_created': len([r for r in room_results if r['action'] == 'created']),
        'rooms_members_added': len([r for r in room_results if r['action'] == 'members_added']),
        'rooms_unchanged': len([r for r in room_results if r['action'] == 'unchanged']),
    }

    module.exit_json(
        changed=changed,
        users=user_results,
        rooms=room_results,
        summary=summary
    )


def main():
    run_module()


if __name__ == '__main__':
    main()
