from django.urls import path
from .views import *
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # Auth Flow
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('login/', LoginView.as_view(), name='login'),

    # Admin Management
    path('users/all/', ViewAllUsers.as_view(), name='view_all_users'),
    path('users/pending/', PeopleWithoutRole.as_view(), name='pending_users'),
    path('users/assign/<int:user_id>/', AssignRole.as_view(), name='assign_role'),
    path('users/delete/<int:user_id>/', DeleteUser.as_view(), name='delete_user'),
    path('user-rbac-audit/', AdminUserRBACListView.as_view(), name='admin-rbac-audit'),

    #for refresh token 
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]