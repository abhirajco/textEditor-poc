from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import SignupView, VerifyOTPView, LoginView, ViewAllUsers, AssignRole , PeopleWithoutRole

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # path('logout/', LogoutView.as_view(), name='logout'),

    path('view-all/', ViewAllUsers.as_view(), name='view_all_users'),
    path('unassigned/', PeopleWithoutRole.as_view(), name='unassigned_users'),
    path('assign-role/<int:user_id>/', AssignRole.as_view(), name='assign_role'),
]