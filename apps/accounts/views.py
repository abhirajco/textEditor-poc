from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, RBAC
from utils.permissions.base import *

class SignupView(APIView):
    """Step 1: Store data temporarily and send OTP."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        full_name = request.data.get('full_name')
        password = request.data.get('password')

        if not all([email, full_name, password]):
            return Response({"error": "All fields are required"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({"error": "User with this email already exists"}, status=status.HTTP_400_BAD_REQUEST)

        hashed_pw = make_password(password)
        pending_user_data = {
            "email": email,
            "password": hashed_pw,
            "full_name": full_name,
        }

        try:
            # Assuming this function handles Redis storage and SMTP
            from utils.notifications.services import send_otp_via_email 
            send_otp_via_email(email, pending_user_data)
        except Exception as e:
            return Response({"error": f"Failed to send mail, error: {str(e)}"}, status=500)
        
        return Response({"message": "OTP sent! Please verify to complete registration."}, status=status.HTTP_200_OK)

class VerifyOTPView(APIView):
    """Step 2: Verify OTP from Redis and create the User."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        otp_provided = request.data.get('otp')

        cache_key = f"otp_auth_{email}"
        cached_data = cache.get(cache_key)

        if not cached_data:
            return Response({"error": "OTP expired or not found"}, status=status.HTTP_400_BAD_REQUEST)

        if str(cached_data["otp"]) != str(otp_provided):
            return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        # Create user with default group='user' and role='none'
        user = User.objects.create(
            email=email,
            full_name=cached_data["full_name"],
            password=cached_data["password"], 
            group='user', 
            role='none',
            is_active=True
        )

        cache.delete(cache_key)
        return Response({"message": "Account created successfully. You can now login."}, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = User.objects.filter(email=email).first()

        if not user:
            return Response({"no user with the given password found , pls signup"})
        
        ##print(user.password)

        if not check_password(password, user.password):
            return Response({"wrong passwrod"})
        
        
        if user and check_password(password, user.password):
            refresh = RefreshToken.for_user(user)
            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "email": user.email, 
                    "group": user.group, 
                    "role": user.role,
                    "full_name": user.full_name
                }
            })
        else:
            return Response({"error": "Invalid credentials"}, status=401)

class AssignRole(APIView):
    """Admin assigns Group and Role, then syncs RBAC."""
    permission_classes = [permissions.IsAuthenticated,  HasRBACPermission]

    required_area = "users"
    required_role = "admin"

    def post(self, request, user_id):
        new_group = request.data.get('group', '').lower()
        new_role = request.data.get('role', 'none').lower()
        
        valid_groups = [c[0] for c in User.GROUP_CHOICES]
        valid_roles = [c[0] for c in User.ROLE_CHOICES]

        if new_group not in valid_groups or new_role not in valid_roles:
            return Response({"error": "Invalid group or role"}, status=400)

        try:
            with transaction.atomic():
                user = User.objects.get(id=user_id)
                user.group = new_group
                user.role = new_role
                
                # Special flags for Admin group
                if new_group == 'admin':
                    user.is_staff = True
                    user.is_superuser = True
                
                user.save()

                # Sync Django Group
                django_group_name = new_group.capitalize()
                django_group, _ = Group.objects.get_or_create(name=django_group_name)
                user.groups.clear()
                user.groups.add(django_group)

                # Setup RBAC Matrix rules for this Django Group
                self.setup_rbac_for_logic(django_group, new_group, new_role)

            return Response({"message": f"Updated {user.email} to {new_group}({new_role}) and synced RBAC."})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

    def setup_rbac_for_logic(self, django_group, group, role):
        """Maps your business workflow to the RBAC Matrix table."""
        # Clear old rules for this group to prevent duplicates
        RBAC.objects.filter(application_group=django_group).delete()

        if group == 'admin':
            for area in ["content", "users", "reports", "settings"]:
                RBAC.objects.create(application_group=django_group, application_area=area, application_action="admin")
        
        elif group == 'executive':
            RBAC.objects.create(application_group=django_group, application_area="content", application_action="read")
            RBAC.objects.create(application_group=django_group, application_area="content", application_action="feedback")
            RBAC.objects.create(application_group=django_group, application_area="content", application_action="promote")

        elif group == 'internal':
            if role == 'writer':
                RBAC.objects.create(application_group=django_group, application_area="content", application_action="write")
                RBAC.objects.create(application_group=django_group, application_area="content", application_action="update")
            elif role == 'reviewer':
                RBAC.objects.create(application_group=django_group, application_area="content", application_action="update")
                RBAC.objects.create(application_group=django_group, application_area="content", application_action="feedback")
                RBAC.objects.create(application_group=django_group, application_area="content", application_action="promote")

        elif group == 'external' and role == 'sme':
            RBAC.objects.create(application_group=django_group, application_area="content", application_action="update")
            RBAC.objects.create(application_group=django_group, application_area="content", application_action="feedback")

class ViewAllUsers(APIView):
    """
    Returns every user in the system.
    Only accessible by Admins.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]

    required_area = "users"
    required_role = "admin"

    def get(self, request):
        users = User.objects.all().order_by('-date_joined')
        data = [
            {
                "id": u.id, 
                "full_name": u.full_name, 
                "email": u.email, 
                "group": u.group, 
                "role": u.role,
                "is_active": u.is_active
            } for u in users
        ]
        return Response(data, status=status.HTTP_200_OK)

class DeleteUser(APIView):
    """View to allow Admin to permanently delete a user."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]

    required_area = "users"
    required_role = "admin"

    def delete(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)

            print(user.full_name)
            
            # Prevent admin from deleting themselves accidentally
            if user == request.user:
                return Response({"error": "You cannot delete your own admin account."}, status=400)
            
            email = user.email
            user.delete()
            return Response({"message": f"User {email} has been permanently deleted."}, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({"error": str(e)})

class PeopleWithoutRole(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]

    required_area = "users"
    required_role = "admin"

    def get(self, request):
        # Users who are still in the default 'user' group
        users = User.objects.filter(group='user')
        data = [{"id": u.id, "full_name": u.full_name, "email": u.email, "group": u.group} for u in users]
        return Response(data, status=status.HTTP_200_OK)
    
class AdminUserRBACListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "users"  # Changed to 'users' area
    required_roles = ["admin"]

    def get(self, request):
        try:
            user_list = []
            users = User.objects.all()

            for user in users:
            # We use __iexact to bridge the gap between 'internal' and 'Internal'
                actions = RBAC.objects.filter(
                    application_group__name__iexact=user.group 
                ).values('application_area', 'application_action')

                user_list.append({
                    'id': user.id,
                    'full_name': user.full_name,
                    'email': user.email,
                    'group': user.group,
                    'role': user.role,
                    'permissions': list(actions)
                })
    
            return Response({"count": len(user_list), "users": user_list})

        except Exception as e:
            return Response({"error": str(e)})