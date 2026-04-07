import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Campaign(models.Model):
    """
    Top-level container. Everything (Events and Tasks) lives under a Campaign.
    max_hierarchy_level controls how deep subtasks can go:
        1 = only root tasks (no subtasks)
        2 = root tasks + 1 level of subtasks
        3 = root tasks + 2 levels of subtasks
    """
    campaign_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="campaigns_created",
    )
    max_hierarchy_level = models.PositiveIntegerField(
        default=2,
        help_text="Minimum 1 (root tasks only). 2 = one level of subtasks. 3 = two levels. etc."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "board"
        ordering  = ["-created_at"]

    def clean(self):
        if self.max_hierarchy_level < 1:
            raise ValidationError("max_hierarchy_level must be at least 1.")

    def __str__(self):
        return self.title


class Event(models.Model):
    """
    A grouping of tasks within a Campaign.
    An Event cannot exist without a Campaign.
    """
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="events_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "board"
        ordering  = ["-created_at"]

    def __str__(self):
        return f"{self.title} [{self.campaign.title}]"


class Task(models.Model):
    """
    A board task.  Created automatically when an executive submits the
    Content Initiation Form.  The resulting task_id is written back to
    Content.task_id so the two records are linked.

    Fields intentionally nullable on creation (filled in later by PM / admin):
      assigned_to, due_date, estimated_hours
    """

    STATUS_CHOICES = [
        ("todo",        "To Do"),
        ("in_progress", "In Progress"),
        ("blocked",   "Blocked"),
        ("completed", "Completed"),
    ]

    PRIORITY_CHOICES = [
        ("low",    "Low"),
        ("medium", "Medium"),
        ("high",   "High"),
    ]

    task_id  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")

    # mirrors Content fields so board context is self-contained
    content_type = models.CharField(max_length=100, blank=True, default="")
    campaign = models.ForeignKey(Campaign , on_delete=models.CASCADE, related_name="task")
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="task", blank=True, null=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES,default="todo",db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")

    # always known — the executive who triggered initiation
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='tasks_created',
    )

    # filled in later — nullable on creation
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="assigned_tasks",
    )
    due_date = models.DateField(null=True, blank=True)
    estimated_hours =models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    created_at =models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "board"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campaign_id", "status"], name="board_campaign_status_idx"),
            models.Index(fields=["assigned_to",  "status"], name="board_assigned_status_idx"),
        ]

    def __str__(self):
        return f"{self.title} [{self.status}]"


class TaskHistory(models.Model):

    ACTION_CHOICES = [
        ("created", "Created"),
        ("transferred", "Transferred"),
        ("stage_changed", "Stage Changed"),
        ("updated", "Updated"),
    ]

    history_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="history")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="task_actions",
    )
    detail = models.CharField(max_length=512, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "board"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.task.title} | {self.action} at {self.timestamp}"


class Discussion(models.Model):

    discussion_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task= models.ForeignKey(Task, on_delete=models.CASCADE, related_name="discussion")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="task_comments",
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "board"
        ordering  = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author} on '{self.task.title}'"
