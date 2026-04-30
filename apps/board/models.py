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

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium","Medium"),
        ("high", "High"),
    ]
    #Planning, In Progress, Upcoming
    STATUS_CHOICES = [
        ("planning", "Planning"),
        ("in_progress", "In Progress"),
        ("upcoming", "Upcoming"),
    ]

    campaign_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    campaign_type = models.CharField(max_length=255)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="to_do", db_index=True)
    location = models.CharField(max_length=255)
    tags = models.CharField(max_length=500, blank=True, default="",
            help_text="Comma-separated tags e.g. design,ux,launch")
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
    Kanban task. Now part of Campaign → Event → Task hierarchy.

    Hierarchy rules:
    - campaign is always required
    - event is optional (task can live directly under campaign)
    - parent_task is optional (task can be a subtask of another task)
    - Subtask depth is validated against campaign.max_hierarchy_level
    """

    STATUS_CHOICES = [
        ("to_do", "To Do"),
        ("in_progress", "In Progress"),
        ("completed","Completed"),
        ("blocked", "Blocked"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium","Medium"),
        ("high", "High"),
    ]

    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name="tasks",
        help_text="Every task must belong to a campaign.",
    )
    event = models.ForeignKey(
        Event, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tasks",
        help_text="Optional. Task can be directly under campaign or under an event.",
    )
    parent_task = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True,
        related_name="subtasks",
        help_text="Optional. Set this to make the task a subtask of another task.",
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True, default="",
            help_text="Comma-separated tags e.g. design,ux,launch")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    marketing_type = models.CharField(max_length=255, blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="to_do", db_index=True)

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="tasks_created",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="tasks_assigned",
    )
    last_transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tasks_transferred",
    )

    created_at= models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "board"
        ordering  = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["event"]),
        ]

    def get_depth(self):
        """
        Calculate how deep this task is in the hierarchy.
        Root task (no parent) = depth 1.
        Subtask = depth 2. Sub-subtask = depth 3. etc.
        """
        depth = 1
        current = self
        while current.parent_task_id is not None:
            depth += 1
            current = current.parent_task
            if depth > 10:  # safety guard against circular references
                break
        return depth

    def clean(self):
        # Validate event belongs to same campaign
        if self.event and self.event.campaign_id != self.campaign_id:
            raise ValidationError("The event must belong to the same campaign as the task.")

        # Validate parent_task belongs to same campaign
        if self.parent_task and self.parent_task.campaign_id != self.campaign_id:
            raise ValidationError("The parent task must belong to the same campaign.")

        # Validate hierarchy depth
        if self.parent_task:
            parent_depth = self.parent_task.get_depth()
            new_depth = parent_depth + 1
            if new_depth > self.campaign.max_hierarchy_level:
                raise ValidationError(
                    f"Cannot create subtask. Campaign allows max hierarchy level "
                    f"{self.campaign.max_hierarchy_level}. "
                    f"This task would be at level {new_depth}."
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def get_tags_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def __str__(self):
        return f"[{self.status}] {self.title}"


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