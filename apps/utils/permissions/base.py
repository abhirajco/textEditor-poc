from rest_framework import permissions
from django.apps import apps


class HasRBACPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        # 1. THE FAST-PASS: If they are a system Admin, just let them in.
        # This removes the need for IsAdminUserRole in your views.
        if request.user.group == 'admin':
            return True

        # 2. THE MATRIX CHECK: For everyone else (Executive, Internal, External)
        area = getattr(view, 'required_area', None)
        single_role = getattr(view, 'required_role', None)
        multiple_roles = getattr(view, 'required_roles', [])

        allowed_roles = list(multiple_roles)
        if single_role:
            allowed_roles.append(single_role)
        
        if not area or not allowed_roles:
            return False 

        RBAC = apps.get_model('accounts', 'RBAC')
        
        return RBAC.objects.filter(
            application_group__in=request.user.groups.all(),
            application_area=area,
            application_action__in=allowed_roles
        ).exists()