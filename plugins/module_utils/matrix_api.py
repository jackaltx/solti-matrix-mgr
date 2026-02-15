"""
Shared utilities for Matrix Admin API modules.
Supports Synapse Admin API with hooks for Conduit/Dendrite differences.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
from ansible.module_utils.urls import fetch_url
from ansible.module_utils.basic import AnsibleModule


class MatrixAdminAPI:
    """
    Wrapper for Matrix Admin API calls.
    
    Synapse:  /_synapse/admin/v1/...
    Conduit:  /_conduit/admin/...  (via admin room commands typically)
    Dendrite: /_dendrite/admin/... (different endpoints)
    """
    
    SYNAPSE_API_BASE = "/_synapse/admin"
    
    def __init__(self, module, homeserver_url, access_token, validate_certs=True):
        self.module = module
        self.homeserver_url = homeserver_url.rstrip('/')
        self.access_token = access_token
        self.validate_certs = validate_certs
    
    def _request(self, method, endpoint, data=None, api_version="v1"):
        """Make an authenticated request to the Admin API."""
        url = f"{self.homeserver_url}{self.SYNAPSE_API_BASE}/{api_version}/{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        
        body = json.dumps(data) if data else None
        
        response, info = fetch_url(
            self.module,
            url,
            method=method,
            headers=headers,
            data=body,
        )
        
        status_code = info.get('status', -1)
        
        if response:
            try:
                body = json.loads(response.read())
            except (ValueError, AttributeError):
                body = {}
        else:
            body = {}
            if 'body' in info:
                try:
                    body = json.loads(info['body'])
                except ValueError:
                    body = {'raw': info.get('body', '')}
        
        return {
            'status_code': status_code,
            'body': body,
            'url': url,
        }
    
    def get(self, endpoint, api_version="v1"):
        return self._request("GET", endpoint, api_version=api_version)
    
    def post(self, endpoint, data=None, api_version="v1"):
        return self._request("POST", endpoint, data=data, api_version=api_version)
    
    def put(self, endpoint, data=None, api_version="v1"):
        return self._request("PUT", endpoint, data=data, api_version=api_version)
    
    def delete(self, endpoint, data=None, api_version="v1"):
        return self._request("DELETE", endpoint, data=data, api_version=api_version)


# User management helpers
def get_user_info(api, user_id):
    """Get user details. Returns None if user doesn't exist."""
    result = api.get(f"users/{user_id}", api_version="v2")
    if result['status_code'] == 200:
        return result['body']
    elif result['status_code'] == 404:
        return None
    else:
        return {'error': result['body'], 'status': result['status_code']}


def create_or_update_user(api, user_id, password=None, displayname=None, admin=False, deactivated=False):
    """Create or update a user via PUT (upsert behavior)."""
    data = {
        "admin": admin,
        "deactivated": deactivated,
    }
    if password:
        data["password"] = password
    if displayname:
        data["displayname"] = displayname
    
    result = api.put(f"users/{user_id}", data=data, api_version="v2")
    return result


def deactivate_user(api, user_id, erase=False):
    """Deactivate a user account."""
    data = {"erase": erase}
    result = api.post(f"deactivate/{user_id}", data=data)
    return result


# Room management helpers
def get_room_info(api, room_id):
    """Get room details."""
    result = api.get(f"rooms/{room_id}")
    if result['status_code'] == 200:
        return result['body']
    elif result['status_code'] == 404:
        return None
    return {'error': result['body'], 'status': result['status_code']}


def list_rooms(api, limit=100, search_term=None):
    """List rooms with optional search."""
    endpoint = f"rooms?limit={limit}"
    if search_term:
        endpoint += f"&search_term={search_term}"
    return api.get(endpoint)


def get_room_members(api, room_id):
    """Get room members list."""
    result = api.get(f"rooms/{room_id}/members")
    if result['status_code'] == 200:
        return result['body']
    elif result['status_code'] == 404:
        return None
    return {'error': result['body'], 'status': result['status_code']}


def delete_room(api, room_id, purge=True, block=False):
    """Delete/purge a room."""
    data = {
        "purge": purge,
        "block": block,
    }
    # Room deletion is async in Synapse v2
    result = api.delete(f"rooms/{room_id}", data=data, api_version="v2")
    return result


# Rate limiting helpers
def set_ratelimit_override(api, user_id, messages_per_second=0, burst_count=0):
    """
    Set or remove rate limit override for a user.
    Set both to 0 to disable rate limiting entirely (useful for bots).
    """
    data = {
        "messages_per_second": messages_per_second,
        "burst_count": burst_count,
    }
    result = api.post(f"users/{user_id}/override_ratelimit", data=data)
    return result


def delete_ratelimit_override(api, user_id):
    """Remove rate limit override, restoring default limits."""
    result = api.delete(f"users/{user_id}/override_ratelimit")
    return result


# Server info
def get_server_version(api):
    """Get server version info."""
    return api.get("server_version")


# Registration token management (for controlled signups)
def create_registration_token(api, token=None, uses_allowed=None, expiry_time=None):
    """Create a registration token."""
    data = {}
    if token:
        data["token"] = token
    if uses_allowed is not None:
        data["uses_allowed"] = uses_allowed
    if expiry_time is not None:
        data["expiry_time"] = expiry_time
    
    return api.post("registration_tokens/new", data=data)


def list_registration_tokens(api, valid=None):
    """List registration tokens."""
    endpoint = "registration_tokens"
    if valid is not None:
        endpoint += f"?valid={'true' if valid else 'false'}"
    return api.get(endpoint)
