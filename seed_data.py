"""
seed_data.py  —  Merged Platform

Run from the project root:
    python seed_data.py

Creates ready-to-use users for BOTH the Insight (content) and Kanban (board) workflows.
All passwords are:  Pass123!
Admin password is:  Pass123!

Users created:
─────────────────────────────────────────────────────────────────────────────
 Email                    Group       Role             Accesses
─────────────────────────────────────────────────────────────────────────────
 admin@platform.com       admin       admin            Everything
 exec@platform.com        executive   exec_approver    Content approval + Board
 writer@platform.com      internal    writer           Content write + Board
 reviewer@platform.com    internal    reviewer         Content review + Board
 sme@platform.com         external    sme              Content review only
─────────────────────────────────────────────────────────────────────────────
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounts.models import User, RBAC
from django.contrib.auth.models import Group


# ==============================================================================
# USER DEFINITIONS
# ==============================================================================

USERS = [
    {
        "email":     "admin@platform.com",
        "name":      "System Admin",
        "group":     "admin",
        "role":      "admin",
        "is_staff":  True,
        "is_super":  True,
    },
    {
        "email":    "exec@platform.com",
        "name":     "Executive Boss",
        "group":    "executive",
        "role":     "exec_approver",
        "is_staff": False,
        "is_super": False,
    },
    {
        "email":    "writer@platform.com",
        "name":     "Alice Writer",
        "group":    "internal",
        "role":     "writer",
        "is_staff": False,
        "is_super": False,
    },
    {
        "email":    "reviewer@platform.com",
        "name":     "Bob Reviewer",
        "group":    "internal",
        "role":     "reviewer",
        "is_staff": False,
        "is_super": False,
    },
    {
        "email":    "sme@platform.com",
        "name":     "Charlie Expert",
        "group":    "external",
        "role":     "sme",
        "is_staff": False,
        "is_super": False,
    },
]

PASSWORD = "Pass123!"


# ==============================================================================
# RBAC RULES  (must mirror AssignRole._setup_rbac in accounts/views.py)
# ==============================================================================

def seed_rbac(django_group, group, role):
    """Wipe and rebuild RBAC rules for this Django Group."""
    RBAC.objects.filter(application_group=django_group).delete()

    if group == 'admin':
        for area in ['content', 'board', 'users', 'reports', 'settings']:
            RBAC.objects.get_or_create(
                application_group=django_group,
                application_area=area,
                application_action='admin',
            )

    elif group == 'executive':
        for action in ['read', 'feedback', 'promote']:
            RBAC.objects.get_or_create(
                application_group=django_group, application_area='content', application_action=action)
        for action in ['read', 'write', 'update']:
            RBAC.objects.get_or_create(
                application_group=django_group, application_area='board', application_action=action)

    elif group == 'internal':
        if role == 'writer':
            for action in ['write', 'update']:
                RBAC.objects.get_or_create(
                    application_group=django_group, application_area='content', application_action=action)
            for action in ['read', 'write', 'update']:
                RBAC.objects.get_or_create(
                    application_group=django_group, application_area='board', application_action=action)

        elif role == 'reviewer':
            for action in ['update', 'feedback', 'promote']:
                RBAC.objects.get_or_create(
                    application_group=django_group, application_area='content', application_action=action)
            for action in ['read', 'write', 'update']:
                RBAC.objects.get_or_create(
                    application_group=django_group, application_area='board', application_action=action)

    elif group == 'external' and role == 'sme':
        for action in ['update', 'feedback', 'promote']:
            RBAC.objects.get_or_create(
                application_group=django_group, application_area='content', application_action=action)
        # SMEs do NOT get board access


# ==============================================================================
# SEED
# ==============================================================================

def seed():
    print("\n🌱 Starting seed...\n")

    for data in USERS:
        user, created = User.objects.get_or_create(
            email=data['email'],
            defaults={
                'full_name':    data['name'],
                'group':        data['group'],
                'role':         data['role'],
                'is_staff':     data['is_staff'],
                'is_superuser': data['is_super'],
                'is_active':    True,
            }
        )

        if created:
            user.set_password(PASSWORD)
            user.save()

            django_group, _ = Group.objects.get_or_create(name=data['group'].capitalize())
            user.groups.add(django_group)
            seed_rbac(django_group, data['group'], data['role'])

            print(f"  ✅ Created  {data['email']}  ({data['group']} / {data['role']})")
        else:
            print(f"  ℹ️  Exists   {data['email']}  (skipped)")

    print("\n✅ Seed complete!\n")
    print("─" * 55)
    print(f"  All passwords: {PASSWORD}")
    print("─" * 55)
    print("  admin@platform.com    → admin (full access)")
    print("  exec@platform.com     → exec_approver (content + board)")
    print("  writer@platform.com   → writer (content + board)")
    print("  reviewer@platform.com → reviewer (content + board)")
    print("  sme@platform.com      → sme (content only)")
    print("─" * 55)


if __name__ == "__main__":
    seed()
