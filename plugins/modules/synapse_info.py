#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for querying Matrix/Synapse server information.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: synapse_info
short_description: Query Matrix Synapse server information
version_added: "0.1.0"
description:
    - Gather facts about a Synapse homeserver.
    - Query users, rooms, registration tokens, federation status.
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
    gather:
        description: What information to gather
        type: list
        elements: str
        choices: ['version', 'users', 'rooms', 'registration_tokens', 'all']
        default: ['version']
    users_filter:
        description: Filter for user list (name search)
        type: str
    rooms_filter:
        description: Filter for room list (search term)
        type: str
    limit:
        description: Maximum results for list queries
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
- name: Get server version
  homelab.matrix.synapse_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    gather:
      - version
  register: server_info

- name: List all users
  homelab.matrix.synapse_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    gather:
      - users
    limit: 500
  register: user_list

- name: Find rooms matching pattern
  homelab.matrix.synapse_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    gather:
      - rooms
    rooms_filter: "project"
  register: project_rooms

- name: Gather all information
  homelab.matrix.synapse_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    gather:
      - all
  register: full_info
'''

RETURN = r'''
version:
    description: Server version information
    type: dict
    returned: when gather includes 'version' or 'all'
    sample:
        server_version: "1.99.0"
        python_version: "3.11.0"
users:
    description: List of users
    type: list
    returned: when gather includes 'users' or 'all'
rooms:
    description: List of rooms
    type: list
    returned: when gather includes 'rooms' or 'all'
registration_tokens:
    description: List of registration tokens
    type: list
    returned: when gather includes 'registration_tokens' or 'all'
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.homelab.matrix.plugins.module_utils.matrix_api import (
    MatrixAdminAPI,
    get_server_version,
    list_rooms,
    list_registration_tokens,
)


def list_users(api, limit=100, name_filter=None):
    """List users with optional filter."""
    endpoint = f"users?limit={limit}"
    if name_filter:
        endpoint += f"&name={name_filter}"
    return api.get(endpoint, api_version="v2")


def run_module():
    module_args = dict(
        homeserver_url=dict(type='str', required=True),
        access_token=dict(type='str', required=True, no_log=True),
        gather=dict(
            type='list',
            elements='str',
            default=['version'],
            choices=['version', 'users', 'rooms', 'registration_tokens', 'all']
        ),
        users_filter=dict(type='str'),
        rooms_filter=dict(type='str'),
        limit=dict(type='int', default=100),
        validate_certs=dict(type='bool', default=True),
    )

    result = dict(
        changed=False,
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

    gather = module.params['gather']
    if 'all' in gather:
        gather = ['version', 'users', 'rooms', 'registration_tokens']
    
    limit = module.params['limit']

    if 'version' in gather:
        resp = get_server_version(api)
        if resp['status_code'] == 200:
            result['version'] = resp['body']
        else:
            module.warn(f"Failed to get version: {resp['body']}")

    if 'users' in gather:
        resp = list_users(api, limit=limit, name_filter=module.params['users_filter'])
        if resp['status_code'] == 200:
            result['users'] = resp['body'].get('users', [])
            result['users_total'] = resp['body'].get('total', len(result['users']))
        else:
            module.warn(f"Failed to list users: {resp['body']}")

    if 'rooms' in gather:
        resp = list_rooms(api, limit=limit, search_term=module.params['rooms_filter'])
        if resp['status_code'] == 200:
            result['rooms'] = resp['body'].get('rooms', [])
            result['rooms_total'] = resp['body'].get('total_rooms', len(result['rooms']))
        else:
            module.warn(f"Failed to list rooms: {resp['body']}")

    if 'registration_tokens' in gather:
        resp = list_registration_tokens(api)
        if resp['status_code'] == 200:
            result['registration_tokens'] = resp['body'].get('registration_tokens', [])
        else:
            module.warn(f"Failed to list registration tokens: {resp['body']}")

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
