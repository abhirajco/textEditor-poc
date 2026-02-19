# import random
# from django.db import models
# from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group

# # --- User Manager ---
# class UserManager(BaseUserManager):
#     def create_user(self, email, full_name, password=None):
#         if not email:
#             raise ValueError("Users must have an email address")
#         user = self.model(
#             email=self.normalize_email(email),
#             full_name=full_name,
#         )
#         user.set_unusable_password() # We use OTP, so no password initially
#         user.save(using=self._db)
#         return user

#     def create_superuser(self, email, full_name, password):
#         user = self.create_user(email, full_name, password)
#         user.is_staff = True
#         user.is_superuser = True
#         user.set_password(password) # Superuser can have a password for Admin Panel
#         user.save(using=self._db)
#         return user

# # --- Custom User Model ---
# class User(AbstractBaseUser, PermissionsMixin):
#     email = models.EmailField(unique=True, max_length=255)
#     full_name = models.CharField(max_length=255)
#     is_active = models.BooleanField(default=True)
#     is_staff = models.BooleanField(default=False)
#     date_joined = models.DateTimeField(auto_now_add=True)

#     objects = UserManager()

#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = ['full_name']

#     def __str__(self):
#         return self.email

# # --- RBAC Matrix ---
# class RBAC(models.Model):
#     APPLICATION_CHOICES = [("in-sight", "In-Sight")]
    
#     # You can add/remove areas here as the company grows
#     AREA_CHOICES = [
#         ("content", "Content Management"),
#         ("users", "User Management"),
#         ("reports", "Reports & Analytics"),
#     ]

#     ROLE_CHOICES = [
#         ("read", "Read"),
#         ("write", "Write"),
#         ("update", "Update"),
#         ("delete", "Delete"),
#         ("admin", "Admin"),
#     ]

#     application_group = models.ForeignKey(
#         Group, 
#         on_delete=models.CASCADE, 
#         related_name="rbac_rules"
#     )
#     application_name = models.CharField(max_length=50, choices=APPLICATION_CHOICES, default="in-sight")
#     application_area = models.CharField(max_length=50, choices=AREA_CHOICES)
#     application_role = models.CharField(max_length=20, choices=ROLE_CHOICES)

#     class Meta:
#         unique_together = ("application_group", "application_area", "application_role")
#         verbose_name = "RBAC Rule"

#     def __str__(self):
#         return f"{self.application_group.name} | {self.application_area} | {self.application_role}"

# # --- Email OTP ---
# class EmailOTP(models.Model):
#     email = models.EmailField(unique=True)
#     otp = models.CharField(max_length=6)
#     full_name = models.CharField(max_length=255, null=True, blank=True)
#     password = models.CharField(max_length=255, null=True, blank=True) # Stored temporarily
#     is_verified = models.BooleanField(default=False) # MUST BE A FIELD
#     created_at = models.DateTimeField(auto_now_add=True)


from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group

# --- User Manager ---
class UserManager(BaseUserManager):
    def create_user(self, email, full_name, password=None):
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(
            email=self.normalize_email(email),
            full_name=full_name,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password):
        user = self.create_user(email, full_name, password)
        user.is_staff = True
        user.is_superuser = True
        user.role = 'admin'
        user.set_password(password)
        user.save(using=self._db)
        return user

# --- Custom User Model ---
class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, max_length=255)
    full_name = models.CharField(max_length=255)
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('writer', 'Writer'),
        ('approver', 'Approver'),
        ('associate', 'Associate'),
        ('user', 'User'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        app_label = 'accounts'

    def __str__(self):
        return self.email


# --- RBAC Matrix ---
class RBAC(models.Model):
    APPLICATION_CHOICES = [("in-sight", "In-Sight")]
    AREA_CHOICES = [
        ("content", "Content Management"),
        ("users", "User Management"),
        ("reports", "Reports & Analytics"),
    ]
    ROLE_CHOICES = [
        ("read", "Read"),
        ("write", "Write"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("admin", "Admin"),
        ("feedback", "Feedback/Vote"), # Added this for Approvers
    ]

    application_group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="rbac_rules")
    application_name = models.CharField(max_length=50, choices=APPLICATION_CHOICES, default="in-sight")
    application_area = models.CharField(max_length=50, choices=AREA_CHOICES)
    application_role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    class Meta:
        unique_together = ("application_group", "application_area", "application_role")
        verbose_name = "RBAC Rule"
        app_label = 'accounts'

    def __str__(self):
        return f"{self.application_group.name} | {self.application_area} | {self.application_role}"


# --- Email OTP ---
class EmailOTP(models.Model):
    email = models.EmailField(unique=True)
    otp = models.CharField(max_length=6)
    full_name = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'accounts'