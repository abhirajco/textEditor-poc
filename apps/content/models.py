import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from cloudinary.models import CloudinaryField


class Content(models.Model):
    """
    Main content/article model. Renamed from Article to Content.
    PK: content_id (UUID)
    """
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_reviewer", "Pending Reviewer"),
        ("pending_executive", "Pending Executive Review"),
        ("pending_admin","Pending Admin Review"),
        ("published",  "Published"),
    ]

    content_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, db_index=True)
    body= models.TextField()   # renamed from 'content' to avoid clash with model name
    image = CloudinaryField("image", null=True, blank=True)

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authored_contents",
        db_index=True,
    )

    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="draft", db_index=True
    )

    # Concurrency locking
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="locked_contents",
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    def __str__(self):
        return f"{self.title} | {self.status}"

    class Meta:
        app_label = "content"
        ordering = ["-updated_at"]
        indexes= [
            models.Index(fields=["locked_by", "status"]),
            models.Index(fields=["author", "status"]),
        ]


class ContentAssignment(models.Model):
    """Links a specific SME to a specific content piece. Renamed from ArticleAssignment."""

    assignment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(Content, on_delete=models.CASCADE, related_name="sme_assignments")
    sme = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "sme"},
        related_name="sme_tasks",
    )
    assigned_by= models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assignments_given",
    )
    assigned_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "content"
        unique_together = ("content", "sme")
        indexes = [
            models.Index(fields=["content", "sme"], name="idx_content_sme_lookup"),
        ]

    def __str__(self):
        return f"{self.sme.full_name} → {self.content.title}"


class ContentComment(models.Model):
    """
    Feedback on a content piece. Renamed from ArticleComment.
    When admin/executive comments, content is auto-reverted to draft.
    """

    comment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(Content, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    version = models.ForeignKey(
        "ContentVersion", on_delete=models.SET_NULL, null=True, blank=True
    )
    comment_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if hasattr(self.user, "group") and self.user.group in ["admin", "executive"]:
                self.content.status = "draft"
                self.content.locked_by = None
                self.content.locked_at = None
                self.content.save()
            super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment by {self.user.full_name} on {self.content.title}"

    class Meta:
        app_label = "content"
        ordering  = ["created_at"]


class ContentVersion(models.Model):
    """
    Immutable snapshot of a content piece at a point in time.
    Renamed from ArticleVersion.
    Write-heavy — created in background via Celery.
    """

    version_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(
        Content, on_delete=models.CASCADE, related_name="versions", db_index=True
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    image_url = models.URLField(max_length=500, null=True, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label= "content"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content", "created_at"]),
        ]

    def __str__(self):
        return f"Version of {self.content.title} at {self.created_at}"


class CommentMention(models.Model):
    """Tracks which users were @mentioned in which comment."""

    mention_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    comment = models.ForeignKey(ContentComment, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "content"
        unique_together = ("user", "comment")

    def __str__(self):
        return f"{self.user.full_name} mentioned in comment {self.comment_id}"
