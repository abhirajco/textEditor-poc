import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group


class UserManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user  = self.model(email=email, full_name=full_name, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff",     True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("group","admin")
        extra_fields.setdefault("role", "admin")
        return self.create_user(email, full_name, password, **extra_fields)

    def get_by_natural_key(self, email):
        return self.get(email=email)


class User(AbstractBaseUser, PermissionsMixin):
    """
    PK is user_id (UUID).
    group = organisational bucket.
    role  = functional role (used for RBAC and business logic).
    """

    GROUP_CHOICES = [
        ("admin", "Admin"),
        ("executive","Executive"),
        ("internal", "Internal Member"),
        ("external", "External Member"),
        ("user", "User"),
    ]

    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("exec_approver", "Executive Approver"),
        ("executive","Executive"),
        ("writer", "Writer"),
        ("reviewer", "Reviewer"),
        ("sme","SME"),
        ("none", "None"),
    ]

    ##no need of unique=True but still adding it, as it is alreday primary_key
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False , unique=True)
    email = models.EmailField(unique=True, max_length=255)
    full_name = models.CharField(max_length=255)
    group = models.CharField(max_length=20, choices=GROUP_CHOICES, default="user")
    role  = models.CharField(max_length=20, choices=ROLE_CHOICES,  default="none")
    is_active = models.BooleanField(default=True)
    is_staff  = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["full_name"]

    def __str__(self):
        return f"{self.email} | {self.group} ({self.role})"

    class Meta:
        app_label = "accounts"


class RBAC(models.Model):
    """Maps Django Groups to application areas and actions."""

    AREA_CHOICES = [
        ("content","Content Management"),
        ("reports","Reports & Analytics"),
        ("settings","System Settings"),
        ("board","Kanban Board"),
        ("users", "User Management"),
    ]
    ACTION_CHOICES = [
        ("read", "Read"),
        ("write", "Write"),
        ("update","Update"),
        ("delete",  "Delete"),
        ("admin", "Admin"),
        ("feedback", "Feedback / Vote"),
        ("promote", "Promote Status"),
    ]

    rbac_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False ,unique=True)
    application_group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="rbac_rules")
    application_name = models.CharField(max_length=50, default="platform")
    application_area = models.CharField(max_length=50, choices=AREA_CHOICES)
    application_action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    def __str__(self):
        return f"{self.application_group.name} | {self.application_area} | {self.application_action}"

    class Meta:
        app_label = "accounts"
        unique_together = ("application_group", "application_area", "application_action")
        verbose_name = "RBAC Rule"
