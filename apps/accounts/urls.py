from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    SignupView, VerifyOTPView, LoginView, LogoutView,
    ViewAllUsers, PeopleWithoutRole, AssignRole,
    DeleteUser, AdminUserRBACListView, UserSearchView,
)


urlpatterns = [
    # ── Auth Flow ──────────────────────────────────────────────────────────
    path('signup/', SignupView.as_view(),  name='signup'),
    path('verify-otp/',VerifyOTPView.as_view(), name='verify_otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ── Admin — User Management ────────────────────────────────────────────
    path('users/all/', ViewAllUsers.as_view(),        name='all_users'),
    path('users/pending/', PeopleWithoutRole.as_view(),   name='pending_users'),
    path('users/assign/<uuid:user_id>/', AssignRole.as_view(),          name='assign_role'),
    path('users/delete/<uuid:user_id>/', DeleteUser.as_view(),          name='delete_user'),
    path('users/rbac-audit/', AdminUserRBACListView.as_view(), name='rbac_audit'),

    # ── @Mention Search ────────────────────────────────────────────────────
    # Used by both article comment box and task discussion mention dropdown
    # GET /api/accounts/users/search/?q=rob  →  [{id, full_name, email}, ...]
    path('users/search/', UserSearchView.as_view(), name='user_search'),
]
