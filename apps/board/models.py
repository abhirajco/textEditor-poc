from django.db import models
from django.conf import settings


class Task(models.Model):

    STATUS_CHOICES = [
        ('to_do', 'To Do'),
        ('in_progress', 'In Progress'),
        ('completed',   'Completed'),
        ('blocked',     'Blocked'),
        ('approved',    'Approved'),
    ]

    PRIORITY_CHOICES = [
        ('low',    'Low'),
        ('medium', 'Medium'),
        ('high',   'High'),
    ]

    title  = models.CharField(max_length=255)
    description= models.TextField(blank=True)
    tags=models.CharField(
            max_length=500, 
            blank=True, default='',
            help_text="Comma-separated tags e.g. design,ux,launch"
    )

    priority= models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    marketing_type = models.CharField(
        max_length=255, blank=True, default='',
        help_text="e.g. Social Media, Blog, Email Campaign"
    )

    due_date = models.DateField(null=True, blank=True)

    # renamed from stage to status (but keeping DB column same via db_column)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='to_do',
        db_index=True,
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='tasks_created',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='tasks_assigned',
    )
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
        indexes   = [
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['due_date']),
            models.Index(fields=['assigned_to', 'status']),
        ]

    def get_tags_list(self):
        """Returns tags as a Python list."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def __str__(self):
        return f"[{self.status}] {self.title} → {self.assigned_to}"



class TaskHistory(models.Model):
    """
    Immutable audit log for every stage change and transfer.
    Written automatically by the views — never edited.
    """

    ACTION_CHOICES = [
        ('created',       'Created'),
        ('transferred',   'Transferred'),
        ('stage_changed', 'Stage Changed'),
        ('updated',       'Updated'),       # ← add this line
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
