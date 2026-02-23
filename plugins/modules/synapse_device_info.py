#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module for auditing Matrix/Synapse user devices (access tokens).
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: synapse_device_info
short_description: Query and manage Matrix user devices (access tokens)
version_added: "0.1.0"
description:
    - List devices (active access tokens) for a Matrix user.
    - Filter devices by user_agent, last_seen age, and display_name.
    - Optionally revoke matched devices for token hygiene.
    - Useful for auditing and cleaning up orphaned/old tokens.
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
    user_agent_filter:
        description: Filter devices by user_agent substring (e.g., "ansible-httpget")
        type: str
    older_than_days:
        description: Filter devices last seen more than N days ago (0 = include never-seen devices)
        type: int
    display_name_filter:
        description: Filter devices by display_name substring
        type: str
    revoke_matched:
        description: Revoke (delete) devices that match the filters
        type: bool
        default: false
    validate_certs:
        description: Validate SSL certificates
        type: bool
        default: true
author:
    - Your Name (@yourhandle)
'''

EXAMPLES = r'''
- name: List all devices for admin user
  jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
  register: admin_devices

- name: Find old ansible tokens
  jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
    user_agent_filter: "ansible-httpget"
    older_than_days: 7
  register: old_ansible_tokens

- name: Audit and report orphaned tokens
  jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
    older_than_days: 0  # Never used
  register: orphaned

- name: Clean up old ansible tokens
  jackaltx.solti_matrix_mgr.synapse_device_info:
    homeserver_url: "https://matrix.example.com"
    access_token: "{{ admin_token }}"
    user_id: "@admin:example.com"
    user_agent_filter: "ansible-httpget"
    older_than_days: 30
    revoke_matched: true
  register: cleanup
'''

RETURN = r'''
devices:
    description: All devices for the user
    type: list
    returned: always
    sample:
        - device_id: "ABCDEFGHIJ"
          display_name: "Firefox on Linux"
          last_seen_ts: 1771182567107
          last_seen_ip: "192.168.1.100"
          last_seen_user_agent: "Mozilla/5.0..."
          user_id: "@admin:example.com"
matched_devices:
    description: Devices that matched the filter criteria
    type: list
    returned: always
revoked_devices:
    description: Device IDs that were revoked (only when revoke_matched=true)
    type: list
    returned: when revoke_matched is true
total_devices:
    description: Total number of devices for the user
    type: int
    returned: always
matched_count:
    description: Number of devices matching filters
    type: int
    returned: always
changed:
    description: Whether any devices were revoked
    type: bool
    returned: always
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.jackaltx.solti_matrix_mgr.plugins.module_utils.matrix_api import MatrixAdminAPI
import time


def list_user_devices(api, user_id):
    """List all devices for a user."""
    result = api.get(f"users/{user_id}/devices", api_version="v2")
    if result['status_code'] == 200:
        return result['body'].get('devices', [])
    elif result['status_code'] == 404:
        return []
    return None


def delete_device(api, user_id, device_id):
    """Delete/revoke a specific device."""
    result = api.delete(f"users/{user_id}/devices/{device_id}", api_version="v2")
    return result['status_code'] == 200


def filter_devices(devices, user_agent_filter=None, older_than_days=None, display_name_filter=None):
    """Filter devices based on criteria."""
    matched = []
    current_time_ms = int(time.time() * 1000)

    for device in devices:
        # User agent filter
        if user_agent_filter:
            user_agent = device.get('last_seen_user_agent') or ''
            if user_agent_filter.lower() not in user_agent.lower():
                continue

        # Display name filter
        if display_name_filter:
            display_name = device.get('display_name') or ''
            if display_name_filter.lower() not in display_name.lower():
                continue

        # Age filter
        if older_than_days is not None:
            last_seen_ts = device.get('last_seen_ts')

            # Handle never-seen devices (last_seen_ts is None)
            if last_seen_ts is None:
                # Only match never-seen devices if older_than_days is exactly 0
                if older_than_days == 0:
                    matched.append(device)
                # Skip this device for all other cases
                continue

            # Calculate age for devices with last_seen_ts
            age_ms = current_time_ms - last_seen_ts
            age_days = age_ms / (1000 * 60 * 60 * 24)

            # Skip if device is newer than threshold
            if age_days < older_than_days:
                continue

            # Skip never-seen check (older_than_days=0) if we have a timestamp
            if older_than_days == 0:
                continue

        matched.append(device)

    return matched


def run_module():
    module_args = dict(
        homeserver_url=dict(type='str', required=True),
        access_token=dict(type='str', required=True, no_log=True),
        admin_user=dict(type='str', required=False),
        admin_password=dict(type='str', required=False, no_log=True),
        user_id=dict(type='str', required=True),
        user_agent_filter=dict(type='str'),
        older_than_days=dict(type='int'),
        display_name_filter=dict(type='str'),
        revoke_matched=dict(type='bool', default=False),
        validate_certs=dict(type='bool', default=True),
    )

    result = dict(
        changed=False,
        devices=[],
        matched_devices=[],
        total_devices=0,
        matched_count=0,
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

    user_id = module.params['user_id']

    # Get all devices
    devices = list_user_devices(api, user_id)

    if devices is None:
        module.fail_json(msg=f"Failed to query devices for user {user_id}")

    result['devices'] = devices
    result['total_devices'] = len(devices)

    # Apply filters
    matched = filter_devices(
        devices,
        user_agent_filter=module.params['user_agent_filter'],
        older_than_days=module.params['older_than_days'],
        display_name_filter=module.params['display_name_filter'],
    )

    result['matched_devices'] = matched
    result['matched_count'] = len(matched)

    # Revoke matched devices if requested
    if module.params['revoke_matched'] and matched:
        if module.check_mode:
            result['changed'] = True
            result['revoked_devices'] = [d['device_id'] for d in matched]
        else:
            revoked = []
            failed = []

            for device in matched:
                device_id = device['device_id']
                if delete_device(api, user_id, device_id):
                    revoked.append(device_id)
                else:
                    failed.append(device_id)

            result['revoked_devices'] = revoked
            result['changed'] = len(revoked) > 0

            if failed:
                module.warn(f"Failed to revoke devices: {', '.join(failed)}")

    # Return updated token if re-authentication occurred
    result['access_token'] = api.access_token
    result['reauthenticated'] = api.reauthenticated

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
