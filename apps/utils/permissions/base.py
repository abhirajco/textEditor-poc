from rest_framework import permissions
# from django.contrib.auth.models import Group  
from django.apps import apps


#i think we can directly use the below permission directly, used in accounts
class IsAdminUserRole(permissions.BasePermission):
    """
    Allows access only to users with the 'admin' role string.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'admin'
        )

# class HasRBACPermission(permissions.BasePermission):
#     """
#     The 'Gold Standard' check:
#     Looks at the user's Groups and checks the RBAC Matrix for specific area access.
#     """
#     def has_permission(self, request, view):
#         if not request.user or not request.user.is_authenticated:
#             return False
        
#         # if request.user.role=="admin":
#         #     return True
            
#         # These must be defined in View 
#         area = getattr(view, 'required_area', None)
#         role_type = getattr(view, 'required_role', None)
        
#         if not area or not role_type:
#             return False 

#         # Check if the user's groups have the required permission in the RBAC table
#         RBAC = apps.get_model('accounts', 'RBAC')
#         return RBAC.objects.filter(
#             application_group__in=request.user.groups.all(),
#             application_area=area,
#             application_role=role_type
#         ).exists()

#new rbac for multiple roles
class HasRBACPermission(permissions.BasePermission):
    """
    The 'Gold Standard' check:
    Now supports both 'required_role' (string) and 'required_roles' (list).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        area = getattr(view, 'required_area', None)
        
        # 1. Grab single role or multiple roles from the view
        single_role = getattr(view, 'required_role', None)
        multiple_roles = getattr(view, 'required_roles', [])

        # 2. Combine them into one list of acceptable roles
        # If single_role is 'read' and multiple_roles is ['write'], allowed becomes ['read', 'write']
        allowed_roles = list(multiple_roles)
        if single_role:
            allowed_roles.append(single_role)
        
        # Security check: if no roles are defined at all, deny access
        if not area or not allowed_roles:
            return False 

        # 3. Check the RBAC table
        # We use application_role__in to check if the user has ANY of the roles in our list
        RBAC = apps.get_model('accounts', 'RBAC')
        
        return RBAC.objects.filter(
            application_group__in=request.user.groups.all(),
            application_area=area,
            application_role__in=allowed_roles  # Key change here!
        ).exists()

# from rest_framework.permissions import BasePermission
# from django.apps import apps

# class RBACPermission(BasePermission):
#     role = None

#     def has_permission(self, request, view):
#         # 1. Authentication Check
#         if not request.user or not request.user.is_authenticated:
#             return False

#         # 2. Superuser Override 
#         if request.user.is_superuser:
#             return True

#         # 3. Get the area from the view (e.g., rbac_area = 'content')
#         area = getattr(view, "rbac_area", None)
        
#         # If the view doesn't define an area or the class doesn't define a role, deny
#         if not area or not self.role:
#             return False

#         # 4. Use apps.get_model to stay safe from Circular Imports!
#         try:
#             RBAC = apps.get_model('accounts', 'RBAC')
#             return RBAC.objects.filter(
#                 user=request.user, 
#                 area=area, 
#                 role=self.role
#             ).exists()
#         except (LookupError, ValueError):
#             # Fallback in case the model isn't loaded yet or name is wrong
#             return False

