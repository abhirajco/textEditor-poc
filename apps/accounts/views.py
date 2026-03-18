from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated

from .models import User, RBAC
from utils.permissions.base import HasRBACPermission
from utils.notifications.services import send_otp_via_email


# ==============================================================================
# AUTH VIEWS
# ==============================================================================

class SignupView(APIView):
    """
    Step 1: User provides email + full_name + password.
    OTP is emailed and pending data is held in Redis for 10 minutes.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email     = request.data.get('email', '').strip()
        full_name = request.data.get('full_name', '').strip()
        password  = request.data.get('password', '')

        if not all([email, full_name, password]):
            return Response({"error": "email, full_name and password are required."}, status=400)

        if User.objects.filter(email=email).exists():
            return Response({"error": "A user with this email already exists."}, status=400)

        hashed_pw    = make_password(password)
        pending_data = {"email": email, "full_name": full_name, "password": hashed_pw}

        try:
            send_otp_via_email(email, pending_data)
        except Exception as e:
            return Response({"error": f"Failed to send OTP email: {str(e)}"}, status=500)

        return Response({"message": "OTP sent! Please verify to complete registration."}, status=200)


class VerifyOTPView(APIView):
    """
    Step 2: User submits the OTP.
    Account is created with group='user' and role='none'.
    Admin must assign group + role later.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email        = request.data.get('email', '').strip()
        otp_provided = request.data.get('otp', '').strip()

        cache_key   = f"otp_auth_{email}"
        cached_data = cache.get(cache_key)

        if not cached_data:
            return Response({"error": "OTP expired or not found. Please sign up again."}, status=400)

        if str(cached_data["otp"]) != str(otp_provided):
            return Response({"error": "Invalid OTP."}, status=400)

        User.objects.create(
            email     = email,
            full_name = cached_data["full_name"],
            password  = cached_data["password"],
            group     = 'user',
            role      = 'none',
            is_active = True,
        )

        cache.delete(cache_key)
        return Response({"message": "Account created successfully. You can now login."}, status=201)


class LoginView(APIView):
    """Returns JWT access + refresh tokens on valid credentials."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email    = request.data.get('email', '').strip()
        password = request.data.get('password', '')

        user = User.objects.filter(email=email).first()

        if not user or not check_password(password, user.password):
            return Response({"error": "Invalid credentials."}, status=401)

        if not user.is_active:
            return Response({"error": "Account is inactive."}, status=403)

        refresh = RefreshToken.for_user(user)
        return Response({
            "refresh": str(refresh),
            "access":  str(refresh.access_token),
            "user": {
                "id":        user.id,
                "email":     user.email,
                "full_name": user.full_name,
                "group":     user.group,
                "role":      user.role,
            }
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"error": "No refresh token provided."}, status=400)
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Successfully logged out."})
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# ==============================================================================
# ADMIN — USER MANAGEMENT VIEWS
# ==============================================================================

class ViewAllUsers(APIView):
    """Returns every user in the system. Admin only."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "users"
    required_role = "admin"

    def get(self, request):
        users = User.objects.all().order_by('-date_joined')
        data  = [
            {
                "id":        u.id,
                "full_name": u.full_name,
                "email":     u.email,
                "group":     u.group,
                "role":      u.role,
                "is_active": u.is_active,
            }
            for u in users
        ]
        return Response(data)


class PeopleWithoutRole(APIView):
    """Returns users who registered but haven't been assigned a role yet."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "users"
    required_role = "admin"

    def get(self, request):
        users = User.objects.filter(role='none').order_by('-date_joined')
        data  = [{"id": u.id, "full_name": u.full_name, "email": u.email, "group": u.group} for u in users]
        return Response(data)


class AssignRole(APIView):
    """
    Admin assigns group + role to a user, syncs Django Group, and rebuilds the
    RBAC matrix. Handles roles for both Insight (content) and Kanban (board).
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "users"
    required_role = "admin"

    def post(self, request, user_id):
        new_group = request.data.get('group', '').lower().strip()
        new_role  = request.data.get('role',  'none').lower().strip()

        valid_groups = [c[0] for c in User.GROUP_CHOICES]
        valid_roles  = [c[0] for c in User.ROLE_CHOICES]

        if new_group not in valid_groups or new_role not in valid_roles:
            return Response({"error": f"Invalid group or role."}, status=400)

        try:
            with transaction.atomic():
                user       = User.objects.get(id=user_id)
                user.group = new_group
                user.role  = new_role

                if new_group == 'admin':
                    user.is_staff     = True
                    user.is_superuser = True

                user.save()

                # Sync Django Group
                django_group_name = new_group.capitalize()
                django_group, _   = Group.objects.get_or_create(name=django_group_name)
                user.groups.clear()
                user.groups.add(django_group)

                # Rebuild RBAC for this group
                self._setup_rbac(django_group, new_group, new_role)

            return Response({
                "message": f"Updated {user.email} → group={new_group}, role={new_role}. RBAC synced."
            })

        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)

    def _setup_rbac(self, django_group, group, role):
        """
        Wipe and rebuild RBAC rules.

        Admin        → admin action on ALL areas (content + board + users + reports + settings)
        Executive    → content: read + feedback + promote  |  board: read + write + update
        Internal     → depends on role:
            writer   → content: write + update  |  board: read + write + update
            reviewer → content: update + feedback + promote  |  board: read + write + update
        External/SME → content: update + feedback + promote  (no board access)
        """
        RBAC.objects.filter(application_group=django_group).delete()

        if group == 'admin':
            for area in ['content', 'board', 'users', 'reports', 'settings']:
                RBAC.objects.create(application_group=django_group, application_area=area, application_action='admin')

        elif group == 'executive':
            # Insight content access
            for action in ['read', 'feedback', 'promote']:
                RBAC.objects.create(application_group=django_group, application_area='content', application_action=action)
            # Kanban board access
            for action in ['read', 'write', 'update']:
                RBAC.objects.create(application_group=django_group, application_area='board', application_action=action)

        elif group == 'internal':
            if role == 'writer':
                # Insight
                for action in ['write', 'update']:
                    RBAC.objects.create(application_group=django_group, application_area='content', application_action=action)
                # Kanban
                for action in ['read', 'write', 'update']:
                    RBAC.objects.create(application_group=django_group, application_area='board', application_action=action)

            elif role == 'reviewer':
                # Insight
                for action in ['update', 'feedback', 'promote']:
                    RBAC.objects.create(application_group=django_group, application_area='content', application_action=action)
                # Kanban
                for action in ['read', 'write', 'update']:
                    RBAC.objects.create(application_group=django_group, application_area='board', application_action=action)

        elif group == 'external' and role == 'sme':
            # SMEs only get Insight content access — no board access
            for action in ['update', 'feedback', 'promote']:
                RBAC.objects.create(application_group=django_group, application_area='content', application_action=action)


class DeleteUser(APIView):
    """Permanently deletes a user. Admin only."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "users"
    required_role = "admin"

    def delete(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)

            if user == request.user:
                return Response({"error": "You cannot delete your own admin account."}, status=400)

            email = user.email
            user.delete()
            return Response({"message": f"User '{email}' has been permanently deleted."})

        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)


class AdminUserRBACListView(APIView):
    """Returns every user with their full RBAC permissions. Admin only."""
    permission_classes = [HasRBACPermission]
    required_area = "users"
    required_role = "admin"

    def get(self, request):
        try:
            user_list = []
            for user in User.objects.all():
                actions = RBAC.objects.filter(
                    application_group__name__iexact=user.group
                ).values('application_area', 'application_action')

                user_list.append({
                    'id':          user.id,
                    'full_name':   user.full_name,
                    'email':       user.email,
                    'group':       user.group,
                    'role':        user.role,
                    'permissions': list(actions),
                })

            return Response({"count": len(user_list), "users": user_list})

        except Exception as e:
            return Response({"error": str(e)})


# ==============================================================================
# @MENTION USER SEARCH
# ==============================================================================

class UserSearchView(APIView):
    """
    GET /api/accounts/users/search/?q=jo
    GET /api/accounts/users/search/?q=john+doe

    Returns users where EACH word in the query matches the START of a word
    in their full_name. Case insensitive. Excludes the requesting user.
    Used by the @mention dropdown in both the article comment box and task discussion.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('q', '').strip()

        if not query:
            return Response([])

        filters = Q()
        for word in query.split():
            filters &= Q(full_name__iregex=rf'(?<!\w){word}')

        users = (
            User.objects
            .filter(filters)
            .exclude(id=request.user.id)
            .values('id', 'full_name', 'email')[:10]
        )

        return Response(list(users))
