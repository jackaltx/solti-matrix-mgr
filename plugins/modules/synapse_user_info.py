#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for querying Matrix/Synapse users via Admin API.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: synapse_user_info
short_description: Query Matrix Synapse users via Admin API
version_added: "0.1.0"
description:
    - List and filter users on a Synapse homeserver.
    - Uses the Synapse Admin API v2.
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
    user_id:
        description: Filter to specific user ID (returns single user)
        type: str
    user_type:
        description: Filter by user type (bot, support, or normal)
        type: str
        choices: ['bot', 'support', 'normal']
    admin:
        description: Filter admin users (true) or non-admin (false)
        type: bool
    deactivated:
        description: Include deactivated users
        type: bool
        default: false
    limit:
        description: Maximum number of users to return
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
- name: List all bot users
  jackaltx.solti_matrix_mgr.synapse_user_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_type: bot

- name: List all admin users
  jackaltx.solti_matrix_mgr.synapse_user_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    admin: true

- name: Get specific user info
  jackaltx.solti_matrix_mgr.synapse_user_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@alice:example.com"

- name: List all normal users (exclude bots and support)
  jackaltx.solti_matrix_mgr.synapse_user_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_type: normal
'''

RETURN = r'''
users:
    description: List of users matching the query
    type: list
    returned: success
    elements: dict
    sample:
        - name: "@alice:example.com"
          displayname: "Alice Smith"
          admin: false
          user_type: null
          deactivated: false
          creation_ts: 1560432668000
        - name: "@bot:example.com"
          displayname: "Bot User"
          admin: false
          user_type: "bot"
          deactivated: false
          creation_ts: 1560432670000
total:
    description: Total number of users matching the query
    type: int
    returned: success
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.jackaltx.solti_matrix_mgr.plugins.module_utils.matrix_api import (
    MatrixAdminAPI,
    get_user_info,
)


def run_module():
    module_args = dict(
        homeserver_url=dict(type='str', required=True),
        access_token=dict(type='str', required=True, no_log=True),
        user_id=dict(type='str'),
        user_type=dict(type='str', choices=['bot', 'support', 'normal']),
        admin=dict(type='bool'),
        deactivated=dict(type='bool', default=False),
        limit=dict(type='int', default=100),
        validate_certs=dict(type='bool', default=True),
    )

    result = dict(
        changed=False,
        users=[],
        total=0,
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

    # If specific user_id provided, get single user
    if module.params['user_id']:
        user = get_user_info(api, module.params['user_id'])
        if user and not isinstance(user, dict) or 'error' not in user:
            result['users'] = [user]
            result['total'] = 1
        elif isinstance(user, dict) and 'error' in user:
            module.fail_json(msg=f"Failed to get user info: {user['error']}")
        else:
            result['users'] = []
            result['total'] = 0
    else:
        # List users with filters
        params = {
            'limit': module.params['limit'],
            'deactivated': 'true' if module.params['deactivated'] else 'false',
        }

        # Add admin filter if specified
        if module.params['admin'] is not None:
            params['admins'] = 'true' if module.params['admin'] else 'false'

        # Build query string
        query_params = '&'.join([f"{k}={v}" for k, v in params.items()])
        endpoint = f"users?{query_params}"

        resp = api.get(endpoint, api_version="v2")

        if resp['status_code'] != 200:
            module.fail_json(msg=f"Failed to list users: {resp['body']}")

        users = resp['body'].get('users', [])

        # Apply user_type filter (API doesn't support filtering normal users directly)
        if module.params['user_type']:
            if module.params['user_type'] == 'normal':
                # Normal users have user_type == null
                users = [u for u in users if u.get('user_type') is None]
            else:
                users = [u for u in users if u.get('user_type') == module.params['user_type']]

        result['users'] = users
        result['total'] = len(users)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
