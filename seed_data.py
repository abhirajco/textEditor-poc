import os
import django

# 1. Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

# 2. Import from the app names directly (relying on your sys.path in settings)
from accounts.models import User, RBAC
from django.contrib.auth.models import Group

def seed_data():
    print("🚀 Starting Seeding...")

    # Define User Scenarios
    users_to_create = [
        {"email": "admin@insight.com", "name": "System Admin", "group": "admin", "role": "admin"},
        {"email": "exec@insight.com", "name": "Executive Boss", "group": "executive", "role": "exec_approver"},
        {"email": "writer@insight.com", "name": "Alice Writer", "group": "internal", "role": "writer"},
        {"email": "reviewer@insight.com", "name": "Bob Reviewer", "group": "internal", "role": "reviewer"},
        {"email": "sme@insight.com", "name": "Charlie Expert", "group": "external", "role": "sme"},
    ]

    for data in users_to_create:
        user, created = User.objects.get_or_create(
            email=data['email'],
            defaults={
                'full_name': data['name'],
                'group': data['group'],
                'role': data['role'],
                'is_staff': True if data['group'] == 'admin' else False,
                'is_superuser': True if data['group'] == 'admin' else False,
                'is_active': True
            }
        )
        if created:
            user.set_password("Pass123!")
            user.save()
            
            # Sync Django Group
            django_group, _ = Group.objects.get_or_create(name=data['group'].capitalize())
            user.groups.add(django_group)
            
            # Seed RBAC for this specific group/role
            seed_rbac_rules(django_group, data['group'], data['role'])
            
            print(f"✅ Created {data['email']} ({data['group']}/{data['role']})")
        else:
            print(f"🟡 {data['email']} already exists.")

def seed_rbac_rules(django_group, group, role):
    """Matches the logic in your AssignRole view to ensure the matrix is populated."""
    if group == 'admin':
        for area in ["content", "users", "reports", "settings"]:
            RBAC.objects.get_or_create(application_group=django_group, application_area=area, application_action="admin")
    
    elif group == 'executive':
        RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="read")
        RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="feedback")
        RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="promote")

    elif group == 'internal':
        if role == 'writer':
            RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="write")
            RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="update")
        elif role == 'reviewer':
            RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="update")
            RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="feedback")
            RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="promote")

    elif group == 'external' and role == 'sme':
        RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="update")
        RBAC.objects.get_or_create(application_group=django_group, application_area="content", application_action="feedback")

if __name__ == "__main__":
    seed_data()
    print("✨ Seeding Complete!")