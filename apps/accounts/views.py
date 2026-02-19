from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from datetime import timedelta
import random
from .models import User, RBAC
#from .permissions import IsAdminUserRole # Your custom admin check
from django.contrib.auth.models import Group
from utils.permissions.base import IsAdminUserRole
from .models import User, EmailOTP
from utils.notifications.services import send_otp_via_email
from django.core.cache import cache
from django.db import transaction

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

        
        # Hash the password before saving it temporarily for security
        hashed_pw = make_password(password)

        pending_user_data = {
                "email": email,
                "password": hashed_pw,
                "full_name": full_name,
            }

        #send_otp_via_email(email , pending_user_data)


        # if send_otp_via_email(email, pending_user_data):
        #     return Response({"message": "OTP sent. Please verify to complete registration."}, status=status.HTTP_200_OK)
        # return Response({"error": "Failed to send email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            send_otp_via_email(email, pending_user_data)
        except Exception as e:
            return Response({"error": f"failed to send mail , error: {str(e)}"} , status=500)
        
        return Response({
                "message": "OTP sent! Please verify to complete registration."
            }, status=status.HTTP_200_OK)


#using db
# class VerifyOTPView(APIView):
#     """Step 2: Verify OTP and finally create the User."""
#     permission_classes = [permissions.AllowAny]

#     def post(self, request):
#         email = request.data.get('email')
#         otp = request.data.get('otp')

#         expiry_limit = timezone.now() - timedelta(minutes=10)
#         otp_record = EmailOTP.objects.filter(
#             email=email, otp=otp, created_at__gte=expiry_limit
#         ).first()

#         if not otp_record:
#             return Response({"error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

#         # Create the actual User
#         user = User.objects.create(
#             email=email,
#             full_name=otp_record.full_name,
#             password=otp_record.password, # Already hashed
#             role='user', # Default role
#             is_active=True
#         )

#         # Clean up: Delete OTP record after successful verification
#         otp_record.delete()

#         return Response({"message": "Account created successfully. You can now login."}, status=status.HTTP_201_CREATED)
class VerifyOTPView(APIView):
    """Step 2: Verify OTP from Redis and create the User."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        otp_provided = request.data.get('otp')

        # 1. Fetch data from Redis
        cache_key = f"otp_auth_{email}"
        cached_data = cache.get(cache_key)

        # 2. Check if OTP exists and matches
        if not cached_data:
            return Response({"error": "OTP expired or not found"}, status=status.HTTP_400_BAD_REQUEST)

        if str(cached_data["otp"]) != str(otp_provided):
            return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Create the actual User
        # Note: Use create_user if you need Django to handle password hashing
        # If the password was already hashed in Step 1, use create()
        user = User.objects.create(
            email=email,
            full_name=cached_data["full_name"],
            password=cached_data["password"], 
            role='user', 
            is_active=True
        )

        # 4. Clean up: Remove from Redis immediately after success
        cache.delete(cache_key)

        return Response(
            {"message": "Account created successfully. You can now login."}, 
            status=status.HTTP_201_CREATED
        )

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = User.objects.filter(email=email).first()

        if user and check_password(password, user.password):
            refresh = RefreshToken.for_user(user)
            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {"email": user.email, "role": user.role}
            })
        return Response({"error": "Invalid credentials"}, status=401)

class ViewAllUsers(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def get(self, request):
        users = User.objects.all()
        data = [{"id": u.id, "name": u.full_name, "email": u.email, "role": u.role} for u in users]
        return Response(data)

class AssignRole(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def post(self, request, user_id):
        new_role = request.data.get('role').lower()
        valid_roles = [c[0] for c in User.ROLE_CHOICES]

        if new_role not in valid_roles:
            return Response({"error": "Invalid role"}, status=400)

        try:
            with transaction.atomic():
                user = User.objects.get(id=user_id)
                user.role = new_role
                if new_role == 'admin':
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()

            # 1. Sync Group
                group_name = new_role.capitalize()
                group, _ = Group.objects.get_or_create(name=group_name)
                user.groups.clear()
                user.groups.add(group) # Link User to Group

            # 2. Assign RBAC Permissions automatically based on role
                self.setup_rbac_for_role(group, new_role)

            return Response({"message": f"Updated {user.email} to {new_role} and synced RBAC rules."})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

    def setup_rbac_for_role(self, group, role):
        """Helper to populate the RBAC table based on the assigned group."""
    
        if role == 'writer':
        # Writers: Create and Read
            RBAC.objects.get_or_create(application_group=group, application_area="content", application_role="write")
            RBAC.objects.get_or_create(application_group=group, application_area="content", application_role="read")
        
        elif role == 'approver':
        # Approvers: Read and Vote (Feedback), but NO Write/Update
            RBAC.objects.get_or_create(application_group=group, application_area="content", application_role="read")
            RBAC.objects.get_or_create(application_group=group, application_area="content", application_role="feedback")
        
        elif role == 'associate':
        # Associates: Read ONLY
            RBAC.objects.get_or_create(application_group=group, application_area="content", application_role="read")
        
        elif role == 'admin':
        # Admins: Full access to everything
            for area in ["content", "users", "reports"]:
                RBAC.objects.get_or_create(application_group=group, application_area=area, application_role="admin")


        #updating this check for any errors if occur - 17/2 (update the db ,run the seeding again)
        #again updating it 18/2
        # elif role == 'admin':
        # # Admins: Full access to everything
        #     for role in ["write", "read","feedback", "delete" , "admin"]:
        #         RBAC.objects.get_or_create(application_group=group, application_area="content", application_role=role)

class PeopleWithoutRole(APIView):
    """
    Returns users who are still just 'user' and haven't been 
    assigned to a professional role yet.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def get(self, request):
        # We filter for the default 'user' role
        users = User.objects.filter(role='user')
        data = [
            {
                "id": u.id, 
                "full_name": u.full_name, 
                "email": u.email,
                "role": u.role
            } for u in users
        ]
        return Response(data, status=status.HTTP_200_OK)