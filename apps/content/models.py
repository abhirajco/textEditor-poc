#added reply_to field
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from cloudinary.models import CloudinaryField


class Content(models.Model):

    STATUS_CHOICES = [
        ("draft",  "Draft"),
        ("in_review",  "In Review"),
        ("rejected",   "Rejected"),
        ("approved",   "Approved"),
        ("published",  "Published"),
    ]

    content_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title= models.CharField(max_length=255, db_index=True)
    body= models.TextField()
    image = CloudinaryField("image", null=True, blank=True)

    content_type = models.CharField(
        max_length=100, blank=True, default="",
        help_text="e.g. blog, video, infographic, social-post",
        db_index=True,
    )
    tags = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Comma-separated tags, e.g. 'seo,product,q3'",
    )
    campaign = models.ForeignKey(
        "board.Campaign",
        on_delete=models.CASCADE,
        related_name="content_forms",
    )
    event = models.ForeignKey(
        "board.Event",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="content_forms",
    )
    task = models.ForeignKey(
        "board.Task",
        on_delete=models.CASCADE,
        related_name="content_forms",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authored_contents",
        db_index=True,
    )

    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="draft", db_index=True
    )

    # ── Concurrency locking (editing lock) ───────────────────────────────────
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="locked_contents",
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    # ── Permanent rejection lock ──────────────────────────────────────────────
    # When ANY approver rejects, this is set to True and no one can edit.
    locked_permanently = models.BooleanField(
        default=False,
        help_text="Set to True when content is rejected. Prevents all edits.",
    )

    # ── Approval flags ────────────────────────────────────────────────────────
    # Step 1: any internal member approves
    internal_approval    = models.BooleanField(default=False)
    # Step 2 (parallel after internal): admin (marketing sign-off) and executive (stakeholder sign-off)
    marketing_approval   = models.BooleanField(default=False)
    stakeholder_approval = models.BooleanField(default=False)

    # Timestamp when all 3 approvals were collected → triggers 24h auto-publish
    all_approved_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set when all three approvals are collected.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    def __str__(self):
        return f"{self.title} | {self.status}"

    def check_and_mark_all_approved(self):
        """
        Call after any approval flag is set.
        If all three are True and all_approved_at is not yet set, stamp it now.
        Publishing is MANUAL only — an admin must explicitly call action=publish.
        Returns True if this call completed the triple approval.
        """
        if (
            self.internal_approval
            and self.marketing_approval
            and self.stakeholder_approval
            and not self.all_approved_at
        ):
            self.all_approved_at = timezone.now()
            self.save(update_fields=["all_approved_at"])
            return True
        return False

    class Meta:
        app_label = "content"
        ordering  = ["-updated_at"]
        indexes   = [
            models.Index(fields=["locked_by", "status"]),
            models.Index(fields=["author", "status"]),
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["content_type", "status"]),
        ]


# ---------------------------------------------------------------------------
# Single canonical ContentAssignment (SME + executive linkage)
# ---------------------------------------------------------------------------

class ContentAssignment(models.Model):
    """
    Links a specific SME (and optionally executive) to a content piece.
    Used to gate SME-only access and notify executives.
    """

    assignment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(Content, on_delete=models.CASCADE, related_name="sme_assignments")
    executive = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "executive"},
        related_name="exe_tasks",
    )
    sme = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "sme"},
        related_name="sme_tasks",
        null= True,
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assignments_given",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label       = "content"
        unique_together = (("content", "sme"),)
        indexes = [
            models.Index(fields=["content", "sme"], name="idx_content_sme_lookup"),
        ]

    def __str__(self):
        sme_name = self.sme.full_name if self.sme else "No SME"
        return f"{sme_name} → {self.content.title}"


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

class ContentHistory(models.Model):
    ACTION_CHOICES = [
        ("initiated",            "Initiated"),
        ("draft_saved",          "Draft Saved"),
        ("submitted",            "Submitted for Review"),
        ("approved_internal",    "Approved by Internal Member"),
        ("approved_stakeholder", "Approved by Stakeholder/Executive"),
        ("approved_marketing",   "Approved by Admin/Marketing"),
        ("rejected",             "Rejected"),
        ("comment_added",        "Comment Added (reverted to draft)"),
        ("published",            "Published"),
        ("auto_published",       "Auto-Published after 24h"),
    ]

    history_id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content      = models.ForeignKey(Content, on_delete=models.CASCADE, related_name="history")
    action_type  = models.CharField(max_length=30, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    note      = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "content"
        ordering  = ["timestamp"]

    def __str__(self):
        who = self.performed_by.full_name if self.performed_by else "System"
        return f"{self.action_type} on {self.content.title} by {who}"


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

class ContentComment(models.Model):
    """
    Any approver/internal member can comment.
    Adding a comment → content reverts to 'draft' (unless rejected/published).
    """

    comment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.ForeignKey(Content, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    version  = models.ForeignKey(
        "ContentVersion", on_delete=models.SET_NULL, null=True, blank=True
    )
    comment_text = models.TextField()
    selected_text= models.TextField(null=True, blank=True)
    resolved  = models.BooleanField(default=False, db_index=True)
    reply_to  = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="replies",
        help_text="The parent comment this is a reply to (null = top-level comment).",
    )
    created_at   = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            content = self.content

            # If content is fully approved (all 3 flags true), enforce the 24-hour edit window.
            fully_approved = (
                content.internal_approval
                and content.marketing_approval
                and content.stakeholder_approval
                and content.all_approved_at is not None
            )
            if fully_approved:
                elapsed = timezone.now() - content.all_approved_at
                if elapsed.total_seconds() >= 86400:
                    raise ValueError(
                        "Content is locked: the 24-hour edit window after full approval has expired."
                    )

            # Revert to draft on comment (only when content is in a reviewable state)
            if content.status in ("in_review",):
                content.status    = None  # placeholder — set below
                content.locked_by = None
                content.locked_at = None
                # Reset approval flags so the flow restarts cleanly
                content.internal_approval    = False
                content.marketing_approval   = False
                content.stakeholder_approval = False
                content.all_approved_at      = None
                content.status               = "draft"
                content._skip_version = True
                content.save()
            elif fully_approved:
                # Comment on fully-approved (not yet published) content inside 24h window
                # → revert to draft and reset approvals
                content.status               = "draft"
                content.locked_by            = None
                content.locked_at            = None
                content.internal_approval    = False
                content.marketing_approval   = False
                content.stakeholder_approval = False
                content.all_approved_at      = None
                content._skip_version        = True
                content.save()

            super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment by {self.user.full_name} on {self.content.title}"

    class Meta:
        app_label = "content"
        ordering  = ["created_at"]


# ---------------------------------------------------------------------------
# Versions (immutable snapshots)
# ---------------------------------------------------------------------------

class ContentVersion(models.Model):

    version_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content    = models.ForeignKey(
        Content, on_delete=models.CASCADE, related_name="versions", db_index=True
    )
    title      = models.CharField(max_length=255)
    body       = models.TextField()
    image_url  = models.URLField(max_length=500, null=True, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "content"
        ordering  = ["-created_at"]
        indexes   = [
            models.Index(fields=["content", "created_at"]),
        ]

    def __str__(self):
        return f"Version of {self.content.title} at {self.created_at}"


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------

class CommentMention(models.Model):
    mention_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content    = models.ForeignKey(Content, on_delete=models.CASCADE)
    comment    = models.ForeignKey(ContentComment, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label       = "content"
        unique_together = (("user", "comment"),)

    def __str__(self):
        return f"{self.user.full_name} mentioned in comment {self.comment_id}"


# ---------------------------------------------------------------------------
# Initiation form (executive → kicks off the whole flow)
# ---------------------------------------------------------------------------

class ContentInitiationForm(models.Model):
    form_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    brief = models.TextField(help_text="What the content should be about")
    sme  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={"role": "sme"},
        related_name="initiated_as_sme",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "executive"},
        related_name="initiated_forms",
    )
    content_type = models.TextField(help_text="Mention the type of content")
    campaign = models.ForeignKey(
        "board.Campaign",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="contents",
    )
    event  = models.ForeignKey(
        "board.Event",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="contents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    content  = models.OneToOneField(
        "Content",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="initiation_form",
    )

    class Meta:
        app_label = "content"
        ordering  = ["-created_at"]

    def __str__(self):
        return f"Form: {self.title} by {self.created_by.full_name}"


