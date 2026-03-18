from django.db import models
from django.conf import settings


class Task(models.Model):
    """
    The core Kanban card.
    - Anyone (any role) can create and assign a task to anyone.
    - The current assignee can transfer it to someone else.
    - Three stages: to_do → in_progress → completed.
    - Full audit trail: assigned_by is always the original creator,
      assigned_to is the current holder, last_transferred_by shows who moved it last.
    """

    STAGE_CHOICES = [
        ('to_do','To Do'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    title= models.CharField(max_length=255)
    description = models.TextField(blank=True)
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='to_do')

    # Who originally created and assigned this task — never changes
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='tasks_created',
    )

    # Who currently holds this task — changes on transfer
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='tasks_assigned',
    )

    # Who performed the last transfer (null if task was never transferred)
    last_transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks_transferred',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'board'
        ordering  = ['-created_at']

    def __str__(self):
        return f"[{self.stage}] {self.title} → {self.assigned_to}"


class TaskHistory(models.Model):
    """
    Immutable audit log for every stage change and transfer.
    Written automatically by the views — never edited.
    """
    ACTION_CHOICES = [
        ('created','Created'),
        ('transferred','Transferred'),
        ('stage_changed', 'Stage Changed'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='history')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by= models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='task_actions',
    )
    detail = models.CharField(max_length=512, blank=True)  # human-readable note
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'board'
        ordering  = ['-timestamp']

    def __str__(self):
        return f"{self.task.title} | {self.action} by {self.performed_by} at {self.timestamp}"


class Discussion(models.Model):
    """
    Flat (non-nested) comments on a task.
    Anyone can post. Stores: message + who wrote it + when.
    """
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='discussion')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='comments',
    )
    message = models.TextField()
    created_at= models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'board'
        ordering  = ['created_at']

    def __str__(self):
        return f"Comment by {self.author} on '{self.task.title}'"
