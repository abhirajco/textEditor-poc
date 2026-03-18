from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group


# ==============================================================================
# USER MANAGER
# ==============================================================================
class UserManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user= self.model(email=email, full_name=full_name, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('group','admin')
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, full_name, password, **extra_fields)

    def get_by_natural_key(self, email):
        return self.get(email=email)


# ==============================================================================
# CUSTOM USER MODEL  (Insight structure — group + role)
# ==============================================================================
class User(AbstractBaseUser, PermissionsMixin):
    """
    Single user model for both Insight (content management) and Kanban (board).

    group— the organizational bucket a user belongs to
    role — the specific function they perform within that group

    Insight roles: exec_approver | writer | reviewer | sme
    Kanban roles: xecutive | writer | reviewer  (admin is shared)
    """

    GROUP_CHOICES = [
        ('admin', 'Admin'),
        ('executive','Executive'),
        ('internal', 'Internal Member'),
        ('external', 'External Member'),
        ('user', 'User'),           # default before assignment
    ]

    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('exec_approver','Executive Approver'),  # Insight — approves articles
        ('executive','Executive'),            # Kanban — can manage tasks
        ('writer','Writer'),               # shared
        ('reviewer','Reviewer'),             # shared
        ('sme','SME'),                  # Insight only
        ('none','None'),                 # just registered, no role yet
    ]

    email = models.EmailField(unique=True, max_length=255)
    full_name = models.CharField(max_length=255)
    group = models.CharField(max_length=20, choices=GROUP_CHOICES, default='user')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES,  default='none')
    is_active = models.BooleanField(default=True)
    is_staff= models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return f"{self.email} | {self.group} ({self.role})"

    class Meta:
        app_label = 'accounts'


# ==============================================================================
# RBAC MATRIX
# ==============================================================================
class RBAC(models.Model):
    """
    Stores which Django Group is allowed to perform which action on which area.
    Covers both Insight (content) and Kanban (board) areas in one table.

    Used by HasRBACPermission in utils/permissions/base.py.
    """

    APPLICATION_CHOICES = [("platform", "Platform")]

    AREA_CHOICES = [
        # Insight areas
        ("content", "Content Management"),
        ("reports", "Reports & Analytics"),
        ("settings","System Settings"),
        # Kanban area
        ("board","Kanban Board"),
        # Shared
        ("users", "User Management"),
    ]

    ACTION_CHOICES = [
        ("read", "Read"),
        ("write","Write"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("admin", "Admin"),            # full control over the area
        ("feedback","Feedback / Vote"),  # Insight reviewers/SMEs/execs
        ("promote", "Promote Status"),   # move content through workflow
    ]

    application_group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='rbac_rules')
    application_name = models.CharField(max_length=50, choices=APPLICATION_CHOICES, default='platform')
    application_area = models.CharField(max_length=50, choices=AREA_CHOICES)
    application_action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    def __str__(self):
        return f"{self.application_group.name} | {self.application_area} | {self.application_action}"

    class Meta:
        app_label= 'accounts'
        unique_together = ('application_group', 'application_area', 'application_action')
        verbose_name = 'RBAC Rule'
