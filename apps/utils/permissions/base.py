from rest_framework import permissions
from django.apps import apps


class HasRBACPermission(permissions.BasePermission):
    """
    Checks the RBAC matrix to determine if the requesting user's Django Group
    has permission to perform the required action on the required area.

    Views declare one of:
        required_area = 'content'          (single area)
        required_role = 'admin'            (single allowed action)
        required_roles = ['read', 'write'] (multiple allowed actions)
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admin fast-pass — admins can do everything
        # if request.user.group == 'admin':
        #     return True

        area = getattr(view, 'required_area',  None)
        single_role = getattr(view, 'required_role',  None)
        multi_roles = getattr(view, 'required_roles', [])

        allowed_actions = list(multi_roles)
        if single_role:
            allowed_actions.append(single_role)

        if not area or not allowed_actions:
            return False

        RBAC = apps.get_model('accounts', 'RBAC')

        return RBAC.objects.filter(
            application_group__in=request.user.groups.all(),
            application_area=area,
            application_action__in=allowed_actions,
        ).exists()
