#!/bin/bash
#
# Create symlink for local development of solti-matrix-mgr collection
# This allows testing playbooks/roles without building and installing the collection
#
# NOTE: Remove the symbolic link before running molecule tests
#

# Create the ansible collections directory structure if it doesn't exist
mkdir -p ~/.ansible/collections/ansible_collections/jackaltx

# Create the symlink
ln -sfn $(pwd) ~/.ansible/collections/ansible_collections/jackaltx/solti_matrix_mgr

echo "✓ Created symlink:"
echo "  $(pwd) → ~/.ansible/collections/ansible_collections/jackaltx/solti_matrix_mgr"
echo ""
echo "You can now use: jackaltx.solti_matrix_mgr.* in playbooks"
echo ""
echo "To remove: rm ~/.ansible/collections/ansible_collections/jackaltx/solti_matrix_mgr"
