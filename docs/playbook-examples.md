# Playbook Examples

Common patterns and examples for using solti-matrix-mgr collection.

## Prerequisites

Source credentials before running any playbook:

```bash
source ~/.secrets/LabMatrix
```

## Room Management

### Create a room with custom settings

```yaml
- name: Create project room
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_access_token: "{{ lookup('env', 'MATRIX_ACCESS_TOKEN') }}"

  tasks:
    - name: Create room
      jackaltx.solti_matrix_mgr.synapse_room:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_access_token }}"
        room_id: "#project-alpha:example.com"
        room_name: "Project Alpha"
        room_alias_name: "project-alpha"
        topic: "Discussion for Project Alpha"
        state: present
        admins:
          - "@alice:example.com"
        moderators:
          - "@bob:example.com"
      register: room_result

    - debug:
        msg: "Room created: {{ room_result.room.room_id }}"
```

### Delete a room programmatically

```yaml
- name: Cleanup test rooms
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_admin_token: "{{ lookup('env', 'MATRIX_ADMIN_TOKEN') }}"
    rooms_to_delete:
      - "#test-room-1:example.com"
      - "#test-room-2:example.com"

  tasks:
    - name: Resolve room aliases
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/directory/room/{{ item | urlencode }}"
        method: GET
        headers:
          Authorization: "Bearer {{ matrix_admin_token }}"
        status_code: 200
      register: room_lookups
      loop: "{{ rooms_to_delete }}"
      ignore_errors: true

    - name: Delete rooms
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v2/rooms/{{ item.json.room_id }}"
        method: DELETE
        headers:
          Authorization: "Bearer {{ matrix_admin_token }}"
          Content-Type: "application/json"
        body_format: json
        body:
          purge: true
          block: false
        status_code: 200
      loop: "{{ room_lookups.results }}"
      when: item is succeeded
      register: deletions

    - debug:
        msg: "Deleted {{ deletions.results | selectattr('changed') | list | length }} rooms"
```

## User Management

### Create a bot user with no rate limits

```yaml
- name: Setup logger bot
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_admin_token: "{{ lookup('env', 'MATRIX_ADMIN_TOKEN') }}"

  tasks:
    - name: Create bot user
      jackaltx.solti_matrix_mgr.synapse_user:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_admin_token }}"
        user_id: "@solti-logger:example.com"
        password: "{{ bot_password }}"
        displayname: "SOLTI Logger Bot"
        ratelimit_override:
          messages_per_second: 0
          burst_count: 0
        state: present
      register: bot_user

    - debug:
        msg: "Bot created: {{ bot_user.user.name }}"
```

### Audit all users on the homeserver

```yaml
- name: Audit homeserver users
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_admin_token: "{{ lookup('env', 'MATRIX_ADMIN_TOKEN') }}"

  tasks:
    - name: Get server info
      jackaltx.solti_matrix_mgr.synapse_info:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_admin_token }}"
        gather:
          - users
          - rooms
          - version
        limit: 1000
      register: server_info

    - name: Display summary
      debug:
        msg:
          - "Server version: {{ server_info.version.server_version | default('N/A') }}"
          - "Total users: {{ server_info.users_total }}"
          - "Total rooms: {{ server_info.rooms_total }}"

    - name: Find admin users
      set_fact:
        admins: "{{ server_info.users | selectattr('admin', 'equalto', true) | list }}"

    - debug:
        msg: "Admin users: {{ admins | map(attribute='name') | list }}"
```

## Token Management

### Audit and cleanup old tokens weekly

```yaml
- name: Weekly token cleanup
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_admin_token: "{{ lookup('env', 'MATRIX_ADMIN_TOKEN') }}"
    token_max_age: 30  # days

  tasks:
    - name: Get all admin devices
      jackaltx.solti_matrix_mgr.synapse_device_info:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_admin_token }}"
        user_id: "@admin:example.com"
      register: all_devices

    - name: Find orphaned devices
      jackaltx.solti_matrix_mgr.synapse_device_info:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_admin_token }}"
        user_id: "@admin:example.com"
        older_than_days: 0  # Never used
      register: orphaned

    - name: Find old ansible tokens
      jackaltx.solti_matrix_mgr.synapse_device_info:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_admin_token }}"
        user_id: "@admin:example.com"
        user_agent_filter: "ansible-httpget"
        older_than_days: "{{ token_max_age }}"
      register: old_tokens

    - name: Generate report
      debug:
        msg:
          - "Total devices: {{ all_devices.total_devices }}"
          - "Orphaned: {{ orphaned.matched_count }}"
          - "Old ansible tokens: {{ old_tokens.matched_count }}"

    - name: Cleanup orphaned devices
      jackaltx.solti_matrix_mgr.synapse_device_info:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_admin_token }}"
        user_id: "@admin:example.com"
        older_than_days: 0
        revoke_matched: true
      when: orphaned.matched_count > 0

    - name: Cleanup old tokens
      jackaltx.solti_matrix_mgr.synapse_device_info:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_admin_token }}"
        user_id: "@admin:example.com"
        user_agent_filter: "ansible-httpget"
        older_than_days: "{{ token_max_age }}"
        revoke_matched: true
      when: old_tokens.matched_count > 0
```

### Single-use token pattern

```yaml
- name: List rooms with single-use token
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_admin_token: "{{ lookup('env', 'MATRIX_ADMIN_TOKEN') }}"

  tasks:
    - name: Query rooms
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v1/rooms"
        method: GET
        headers:
          Authorization: "Bearer {{ matrix_admin_token }}"
        status_code: 200
      register: rooms_response

    - debug:
        msg: "Total rooms: {{ rooms_response.json.total_rooms }}"

  post_tasks:
    - name: Revoke token after use
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_matrix/client/v3/logout"
        method: POST
        headers:
          Authorization: "Bearer {{ matrix_admin_token }}"
        status_code: 200
      when: cleanup_token | default(false) | bool
      ignore_errors: true
      no_log: true
```

Usage:
```bash
ansible-playbook playbook.yml -e "cleanup_token=true"
```

## Event Posting

### Post verification results to Matrix room

```yaml
- name: Post test results to Matrix
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_access_token: "{{ lookup('env', 'MATRIX_ACCESS_TOKEN') }}"
    matrix_room_id: "{{ lookup('env', 'MATRIX_ROOM_ID') }}"

  tasks:
    - name: Run tests
      command: pytest tests/
      register: test_result
      ignore_errors: true

    - name: Post results to Matrix
      jackaltx.solti_matrix_mgr.matrix_event:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_access_token }}"
        room_id: "{{ matrix_room_id }}"
        event_type: "m.room.message"
        content:
          msgtype: "m.text"
          body: |
            Test run completed
            Status: {{ 'PASSED' if test_result.rc == 0 else 'FAILED' }}
            Exit code: {{ test_result.rc }}
        state: present
```

### Structured event with custom fields

```yaml
- name: Post deployment notification
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_access_token: "{{ lookup('env', 'MATRIX_ACCESS_TOKEN') }}"
    matrix_room_id: "#deployments:example.com"

  tasks:
    - name: Post deployment event
      jackaltx.solti_matrix_mgr.matrix_event:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_access_token }}"
        room_id: "{{ matrix_room_id }}"
        event_type: "com.example.deployment"
        content:
          service: "api-server"
          version: "v1.2.3"
          environment: "production"
          deployed_by: "ansible"
          timestamp: "{{ ansible_date_time.iso8601 }}"
        state: present
```

## Advanced Patterns

### Conditional room creation

```yaml
- name: Ensure project rooms exist
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_access_token: "{{ lookup('env', 'MATRIX_ACCESS_TOKEN') }}"
    projects:
      - name: "alpha"
        display_name: "Project Alpha"
        admins: ["@alice:example.com"]
      - name: "beta"
        display_name: "Project Beta"
        admins: ["@bob:example.com"]

  tasks:
    - name: Create rooms for each project
      jackaltx.solti_matrix_mgr.synapse_room:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_access_token }}"
        room_id: "#project-{{ item.name }}:example.com"
        room_name: "{{ item.display_name }}"
        room_alias_name: "project-{{ item.name }}"
        state: present
        admins: "{{ item.admins }}"
      loop: "{{ projects }}"
      register: room_results

    - debug:
        msg: "Created/verified {{ projects | length }} project rooms"
```

### Multi-step room setup with verification

```yaml
- name: Setup and verify room
  hosts: localhost
  gather_facts: false

  vars:
    matrix_homeserver_url: "{{ lookup('env', 'MATRIX_HOMESERVER_URL') }}"
    matrix_access_token: "{{ lookup('env', 'MATRIX_ACCESS_TOKEN') }}"
    matrix_admin_token: "{{ lookup('env', 'MATRIX_ADMIN_TOKEN') }}"

  tasks:
    - name: Create room
      jackaltx.solti_matrix_mgr.synapse_room:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_access_token }}"
        room_id: "#verified-room:example.com"
        room_name: "Verified Room"
        room_alias_name: "verified-room"
        state: present
        admins: ["@admin:example.com"]
      register: room_creation

    - name: Verify room state
      ansible.builtin.uri:
        url: "{{ matrix_homeserver_url }}/_synapse/admin/v1/rooms/{{ room_creation.room.room_id }}/state"
        method: GET
        headers:
          Authorization: "Bearer {{ matrix_admin_token }}"
        status_code: 200
      register: room_state

    - name: Extract power levels
      set_fact:
        power_levels: "{{ room_state.json.state | selectattr('type', 'equalto', 'm.room.power_levels') | map(attribute='content') | first }}"

    - name: Verify admin has correct power level
      assert:
        that:
          - power_levels.users['@admin:example.com'] == 100
        fail_msg: "Admin power level incorrect!"
        success_msg: "Room verified successfully"

    - name: Post success message
      jackaltx.solti_matrix_mgr.matrix_event:
        homeserver_url: "{{ matrix_homeserver_url }}"
        access_token: "{{ matrix_access_token }}"
        room_id: "{{ room_creation.room.room_id }}"
        event_type: "m.room.message"
        content:
          msgtype: "m.notice"
          body: "Room setup and verification complete ✓"
        state: present
```

## See Also

- [Token Management Guide](token-management.md)
- [Playbook Quick Reference](../../mylab/playbooks/matrix/README.md)
- [Module Documentation](../plugins/modules/)
