# Gemini Agent Context for jackaltx.solti_matrix_mgr

This document provides context and guidelines for the Gemini CLI agent when working within the `jackaltx.solti_matrix_mgr` Ansible collection. Your primary role will be to assist with test coding and ensuring the quality of this collection.

## Architectural Principles

*   **Generic Matrix Client**: The `solti_matrix_mgr` collection is intended to be a generic client for the Matrix API (Admin API, Client-Server API). It should remain free of any Solti-specific or other domain-specific logic.
*   **Transport Layer Focus**: Modules like `matrix_event` are pure transport layers. They accept generic data and send it to Matrix without imposing structure or validation.
*   **Playbook-driven Logic**: Any domain-specific logic, such as constructing Solti-schema events or processing Matrix event content, should reside in Ansible playbooks or roles that *use* this collection, not within the collection's modules.

## Testing Strategy

When developing or modifying tests, adhere to the following principles:

1.  **Molecule for Integration Testing**: Use [Molecule](https://molecule.readthedocs.io/) for testing roles and modules. The collection already has a `molecule/` directory.
2.  **Idempotency**: All Ansible tasks and roles should be idempotent. Running a test multiple times should yield the same result without making unnecessary changes.
3.  **Check Mode Verification**: Ensure tests include verification of `check_mode` behavior where applicable.
4.  **Generic Test Data**: Test data used should be generic and not contain any sensitive information.
5.  **Focus on Module/Role Functionality**: Tests should primarily verify that the modules and roles correctly interact with the Matrix API or manage local resources as intended.
6.  **Event Content Testing (for `matrix_event`)**: When testing `matrix_event`, ensure that the module correctly sends the provided `content` dictionary without alteration. Verification should focus on the successful API call and the returned `event_id`, `room_id`, etc.
7.  **Schema Validation (External)**: Do *not* implement Solti-specific schema validation within this collection's tests. Validation of Solti schemas should be performed by separate tools (e.g., the `matrix-view-events.py` script) or in higher-level playbooks.

## Development Workflow

*   When making changes to modules or roles, ensure corresponding tests are updated or added.
*   Run Molecule tests frequently during development (`molecule test`).
*   Follow existing coding style and best practices within the collection (e.g., Ansible linting).

## Key Files for Gemini Agent

*   `plugins/modules/`: Contains the Ansible modules (e.g., `matrix_event.py`, `synapse_user.py`).
*   `plugins/module_utils/`: Contains Python utility code shared by modules.
*   `molecule/`: Contains Molecule scenarios for testing.
*   `README.md`: Public-facing documentation for the collection.

Your goal is to become proficient in extending the test coverage and developing new tests for this collection, always adhering to the generic nature of `solti_matrix_mgr`.
