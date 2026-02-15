# SOLTI Matrix Manager Documentation

Comprehensive documentation for the `jackaltx.solti_matrix_mgr` Ansible collection.

## Getting Started

- **[Collection README](../README.md)** - Overview, installation, and quick start
- **[Playbook Quick Reference](../../../mylab/playbooks/matrix/README.md)** - Ready-to-use playbook commands (mylab installation)

## Guides

### [Token Management](token-management.md)
Complete guide to managing Matrix access tokens:
- Token types and lifecycle
- Generating and refreshing admin tokens
- Auditing active tokens/devices
- Cleanup strategies (cached, single-use, scheduled)
- Security best practices
- Troubleshooting

**Key topics:**
- `synapse_device_info` module reference
- Single source of truth: `~/.secrets/LabMatrix`
- Token audit and cleanup playbooks
- Production vs development patterns

### [Playbook Examples](playbook-examples.md)
Common patterns and complete playbook examples:
- Room management (create, delete, verify)
- User management (bots, rate limits)
- Token auditing and cleanup
- Event posting (verification results, deployments)
- Multi-step workflows
- Conditional logic

**Key topics:**
- Room creation with power levels
- Programmatic room deletion
- Weekly token cleanup automation
- Single-use token pattern
- Structured event posting

## Module Reference

### Admin API Modules

- **[synapse_user](../plugins/modules/synapse_user.py)** - Create/update/deactivate users
- **[synapse_room](../plugins/modules/synapse_room.py)** - Query/delete rooms
- **[synapse_info](../plugins/modules/synapse_info.py)** - Gather server facts
- **[synapse_device_info](../plugins/modules/synapse_device_info.py)** - Audit and manage devices (tokens)

### Messaging Modules

- **[matrix_event](../plugins/modules/matrix_event.py)** - Post arbitrary content to Matrix rooms

## Role Reference

### Configuration Roles

- **synapse_user** - Declarative user account management
- **synapse_config** - Deploy homeserver.yaml overlays and appservices
- **hookshot_webhook** - Configure matrix-hookshot webhooks

## Architecture

### Token Management Architecture

```
┌─────────────────────────────────────────┐
│ ~/.secrets/LabMatrix                    │  ← Single source of truth
├─────────────────────────────────────────┤
│ MATRIX_ADMIN_USER                       │
│ MATRIX_ADMIN_PASSWORD                   │
│ MATRIX_ADMIN_TOKEN (cached)             │  ← Auto-updated by get-admin-token.sh
└─────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ get-admin-token.sh                      │  ← Token generator
├─────────────────────────────────────────┤
│ 1. Read credentials from LabMatrix      │
│ 2. Login to Matrix homeserver           │
│ 3. Receive new access token             │
│ 4. Update MATRIX_ADMIN_TOKEN in file    │
└─────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Ansible Playbooks                       │
├─────────────────────────────────────────┤
│ source ~/.secrets/LabMatrix             │
│ ansible-playbook playbooks/matrix/...   │
│   - list-rooms.yml                      │
│   - create-room.yml                     │
│   - delete-room.yml                     │
│   - audit-tokens.yml                    │
└─────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Matrix Synapse Server                   │
├─────────────────────────────────────────┤
│ Admin API (/_synapse/admin/...)         │
│ Client API (/_matrix/client/...)        │
└─────────────────────────────────────────┘
```

### Deployment Patterns

#### Pattern 1: Proxmox Helper-Script LXC
```
LXC Container
├── /etc/synapse/
│   ├── homeserver.yaml
│   ├── conf.d/              ← Ansible overlays
│   └── appservices/         ← Bridge registrations
└── Synapse (systemd)
    └── Admin API :8008      ← Module API calls
```

#### Pattern 2: spantaleev/matrix-docker-ansible-deploy
```
Docker Compose Stack
├── /matrix/synapse/config/  ← Ansible overlays
├── /matrix/hookshot/        ← Webhook configs
└── Containers
    ├── synapse
    ├── postgres
    └── hookshot
```

## Event Schemas

(Future documentation for structured event posting)

- Verification results
- Deployment notifications
- Custom domain events

See `event-schemas.md` when available.

## Contributing

### Adding New Modules

1. Create module in `plugins/modules/`
2. Add module_utils helpers if needed
3. Write examples in `playbook-examples.md`
4. Update this index

### Adding New Playbooks

1. Create playbook in `mylab/playbooks/matrix/`
2. Add YAML header documentation
3. Update `mylab/playbooks/matrix/README.md`
4. Add example to `playbook-examples.md`

### Adding New Documentation

1. Create markdown file in `docs/`
2. Update this index (`docs/README.md`)
3. Link from collection README

## External Resources

- [Matrix Specification](https://spec.matrix.org/) - Official Matrix protocol spec
- [Synapse Admin API](https://matrix-org.github.io/synapse/latest/usage/administration/admin_api/) - Synapse Admin API reference
- [synadm](https://github.com/JOJ0/synadm) - CLI tool for Synapse Admin API
- [matrix-hookshot](https://github.com/matrix-org/matrix-hookshot) - Webhook bridge documentation

## Support

- **Issues:** File issues in the project repository
- **Questions:** Check playbook examples and token management guide first
- **Custom schemas:** See event-schemas.md for extension patterns
