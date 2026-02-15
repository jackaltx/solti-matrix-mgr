#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for managing Matrix/Synapse users via Admin API.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: synapse_user
short_description: Manage Matrix Synapse users via Admin API
version_added: "0.1.0"
description:
    - Create, update, or deactivate users on a Synapse homeserver.
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
        description: Full Matrix user ID (@user:server.com)
        required: true
        type: str
    state:
        description: Desired state of the user
        type: str
        choices: ['present', 'absent']
        default: present
    password:
        description: User password (only for creation or password reset)
        type: str
        no_log: true
    displayname:
        description: User display name
        type: str
    admin:
        description: Whether user has admin privileges
        type: bool
        default: false
    deactivated:
        description: Whether to deactivate the account
        type: bool
        default: false
    erase:
        description: When state=absent, also erase user data
        type: bool
        default: false
    ratelimit_override:
        description: Rate limit override (set to 0/0 to disable for bots)
        type: dict
        suboptions:
            messages_per_second:
                type: int
                default: 0
            burst_count:
                type: int
                default: 0
    validate_certs:
        description: Validate SSL certificates
        type: bool
        default: true
author:
    - Your Name (@yourhandle)
'''

EXAMPLES = r'''
- name: Create a regular user
  jackaltx.solti_matrix_mgr.synapse_user:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@alice:example.com"
    password: "{{ user_password }}"
    displayname: "Alice Smith"
    state: present

- name: Create an admin user
  jackaltx.solti_matrix_mgr.synapse_user:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
    password: "{{ admin_password }}"
    admin: true
    state: present

- name: Create a bot with no rate limits
  jackaltx.solti_matrix_mgr.synapse_user:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@hookshot:example.com"
    password: "{{ bot_password }}"
    displayname: "Hookshot Bot"
    ratelimit_override:
      messages_per_second: 0
      burst_count: 0
    state: present

- name: Deactivate a user
  jackaltx.solti_matrix_mgr.synapse_user:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@baduser:example.com"
    state: absent
    erase: true
'''

RETURN = r'''
user:
    description: User information from the server
    type: dict
    returned: success
    sample:
        name: "@alice:example.com"
        displayname: "Alice Smith"
        admin: false
        deactivated: false
changed:
    description: Whether any changes were made
    type: bool
    returned: always
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.jackaltx.solti_matrix_mgr.plugins.module_utils.matrix_api import (
    MatrixAdminAPI,
    get_user_info,
    create_or_update_user,
    deactivate_user,
    set_ratelimit_override,
)


def run_module():
    module_args = dict(
        homeserver_url=dict(type='str', required=True),
        access_token=dict(type='str', required=True, no_log=True),
        user_id=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        password=dict(type='str', no_log=True),
        displayname=dict(type='str'),
        admin=dict(type='bool', default=False),
        deactivated=dict(type='bool', default=False),
        erase=dict(type='bool', default=False),
        ratelimit_override=dict(type='dict'),
        validate_certs=dict(type='bool', default=True),
    )

    result = dict(
        changed=False,
        user={},
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

    user_id = module.params['user_id']
    state = module.params['state']

    # Get current user state
    current_user = get_user_info(api, user_id)
    
    if isinstance(current_user, dict) and 'error' in current_user:
        module.fail_json(msg=f"Failed to query user: {current_user}")

    if state == 'absent':
        if current_user and not current_user.get('deactivated', False):
            if module.check_mode:
                result['changed'] = True
            else:
                resp = deactivate_user(api, user_id, erase=module.params['erase'])
                if resp['status_code'] == 200:
                    result['changed'] = True
                else:
                    module.fail_json(msg=f"Failed to deactivate user: {resp['body']}")
    
    elif state == 'present':
        needs_update = False
        
        if current_user is None:
            needs_update = True
        else:
            # Check if any attributes differ
            if module.params['displayname'] and current_user.get('displayname') != module.params['displayname']:
                needs_update = True
            if current_user.get('admin', False) != module.params['admin']:
                needs_update = True
            if current_user.get('deactivated', False) != module.params['deactivated']:
                needs_update = True
        
        if needs_update:
            if module.check_mode:
                result['changed'] = True
            else:
                resp = create_or_update_user(
                    api,
                    user_id,
                    password=module.params['password'],
                    displayname=module.params['displayname'],
                    admin=module.params['admin'],
                    deactivated=module.params['deactivated'],
                )
                if resp['status_code'] in [200, 201]:
                    result['changed'] = True
                    result['user'] = resp['body']
                else:
                    module.fail_json(msg=f"Failed to create/update user: {resp['body']}")
        
        # Handle rate limit override
        if module.params['ratelimit_override'] is not None:
            rl = module.params['ratelimit_override']
            if not module.check_mode:
                resp = set_ratelimit_override(
                    api,
                    user_id,
                    messages_per_second=rl.get('messages_per_second', 0),
                    burst_count=rl.get('burst_count', 0),
                )
                if resp['status_code'] != 200:
                    module.warn(f"Failed to set rate limit override: {resp['body']}")

    # Fetch final state
    if not module.check_mode:
        final_user = get_user_info(api, user_id)
        if final_user and not isinstance(final_user, dict) or 'error' not in final_user:
            result['user'] = final_user

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
