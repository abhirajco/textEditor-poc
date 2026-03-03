
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group

# --- User Manager ---
# apps/accounts/models.py

class UserManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            full_name=full_name,
            **extra_fields
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
            
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('group', 'admin')
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, full_name, password, **extra_fields)

    # Django uses this method to find users during login/createsuperuser
    def get_by_natural_key(self, email):
        return self.get(email=email)
    

# --- Custom User Model ---
# apps/accounts/models.py

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, max_length=255)
    full_name = models.CharField(max_length=255)
    
    GROUP_CHOICES = [
        ('admin', 'Admin'),
        ('executive', 'Executive'),
        ('internal', 'Internal Member'),
        ('external', 'External Member'),
        ('user', 'User'),
    ]
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('exec_approver', 'Executive Approver'),
        ('writer', 'Writer'),
        ('reviewer', 'Reviewer'),
        ('sme', 'SME'),
        ('none', 'None'),
    ]

    group = models.CharField(max_length=20, choices=GROUP_CHOICES, default='user')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='none')
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False) # For Django Admin access
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return f"{self.email} | {self.group} ({self.role})"
    
    class Meta:
        app_label = 'accounts'

# --- RBAC Matrix ---
class RBAC(models.Model):
    APPLICATION_CHOICES = [("in-sight", "In-Sight")]
    AREA_CHOICES = [
        ("content", "Content Management"),
        ("users", "User Management"),
        ("reports", "Reports & Analytics"),
        ("settings", "System Settings"),
    ]
    # These are the permissions/actions available for each area
    ACTION_CHOICES = [
        ("read", "Read"),
        ("write", "Write"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("admin", "Admin"),           # Full control over the area
        ("feedback", "Feedback/Vote"), # For Reviewers/SMEs
        ("promote", "Promote Status"), # To move content to Exec/Admin
    ]

    application_group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="rbac_rules")
    application_name = models.CharField(max_length=50, choices=APPLICATION_CHOICES, default="in-sight")
    application_area = models.CharField(max_length=50, choices=AREA_CHOICES)
    application_action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    def __str__(self):
        return f"{self.application_group.name} | {self.application_area} | {self.application_action}"

    class Meta:
        app_label = 'accounts'  # <--- ADD THIS
        unique_together = ("application_group", "application_area", "application_action")
        verbose_name = "RBAC Rule"


# --- Email OTP ---
# class EmailOTP(models.Model):
#     email = models.EmailField(unique=True)
#     otp = models.CharField(max_length=6)
#     full_name = models.CharField(max_length=255, null=True, blank=True)
#     password = models.CharField(max_length=255, null=True, blank=True)
#     is_verified = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         app_label = 'accounts'