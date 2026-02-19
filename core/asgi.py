"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
import sys
from pathlib import Path
from django.core.asgi import get_asgi_application

# 1. Define the base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. Add the 'apps' directory to sys.path so 'accounts' can be imported directly
APPS_DIR = os.path.join(BASE_DIR, 'apps')
if APPS_DIR not in sys.path:
    sys.path.insert(0, APPS_DIR)

# 3. Set the settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# 4. Initialize the ASGI application
application = get_asgi_application()
