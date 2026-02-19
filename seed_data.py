import os
import sys
import django

# 1. Setup paths to match your settings.py logic
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPS_DIR = os.path.join(BASE_DIR, 'apps')

# This is the magic line that matches your settings.py
if APPS_DIR not in sys.path:
    sys.path.insert(0, APPS_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

# 2. Import 'User' directly (NOT apps.accounts)
from apps.accounts.models import User
from django.contrib.auth.models import Group

def seed():
    print("--- Starting Data Injection ---")
    roles = ['admin', 'writer', 'approver', 'associate', 'user']
    
    for role_name in roles:
        email = f"{role_name}@insight.com"
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'full_name': f"Test {role_name.capitalize()}",
                'role': role_name,
                'is_active': True,
                'is_staff': True if role_name == 'admin' else False,
                'is_superuser': True if role_name == 'admin' else False,
            }
        )
        user.set_password('InSight2026!')
        user.save()

        group, _ = Group.objects.get_or_create(name=role_name.capitalize())
        user.groups.add(group)
        print(f"{'Created' if created else 'Updated'} {email}")

if __name__ == "__main__":
    seed()