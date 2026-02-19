# from rest_framework import permissions
# from django.contrib.auth.models import Group  
# from .models import RBAC


# #i think we can directly use the below permission directly
# class IsAdminUserRole(permissions.BasePermission):
#     """
#     Allows access only to users with the 'admin' role string.
#     """
#     def has_permission(self, request, view):
#         return bool(
#             request.user and 
#             request.user.is_authenticated and 
#             request.user.role == 'admin'
#         )

# class HasRBACPermission(permissions.BasePermission):
#     """
#     The 'Gold Standard' check:
#     Looks at the user's Groups and checks the RBAC Matrix for specific area access.
#     """
#     def has_permission(self, request, view):
#         if not request.user or not request.user.is_authenticated:
#             return False
            
#         # These must be defined in View 
#         area = getattr(view, 'required_area', None)
#         role_type = getattr(view, 'required_role', None)
        
#         if not area or not role_type:
#             return False 

#         # Check if the user's groups have the required permission in the RBAC table
#         return RBAC.objects.filter(
#             application_group__in=request.user.groups.all(),
#             application_area=area,
#             application_role=role_type
#         ).exists()



# # from rest_framework import permissions
# # from django.contrib.auth.models import Group  # <--- THIS IS THE MISSING LINK
# # from .models import RBAC

# # class IsAdminUserRole(permissions.BasePermission):
# #     """
# #     Allows access only to users with the 'admin' role.
# #     """
# #     def has_permission(self, request, view):
# #         return bool(
# #             request.user and 
# #             request.user.is_authenticated and 
# #             request.user.role == 'admin'
# #         )

# # class IsWriterRole(permissions.BasePermission):
# #     """
# #     Allows access only to users with the 'writer' role.
# #     """
# #     def has_permission(self, request, view):
# #         return bool(
# #             request.user and 
# #             request.user.is_authenticated and 
# #             request.user.role == 'writer'
# #         )

# # class IsApproverRole(permissions.BasePermission):
# #     """
# #     Allows access only to users with the 'approver' role.
# #     """
# #     def has_permission(self, request, view):
# #         return bool(
# #             request.user and 
# #             request.user.is_authenticated and 
# #             request.user.role == 'approver'
# #         )