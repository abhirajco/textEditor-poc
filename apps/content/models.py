from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db import transaction

class Article(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_executive', 'Pending Executive Review'),
        ('pending_admin', 'Pending Admin Review'),
        ('published', 'Published'),
    ]

    title = models.CharField(max_length=255)
    content = models.TextField()
    
    # Relationships
    # Index 1: Speeds up "My Articles" dashboard
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='authored_articles',
        db_index=True
    )
    # Track users mentioned in the content/description
    mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='mentioned_in_articles', 
        blank=True
    )
    
    # Index 2: Critical for filtering Published vs Active lists
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft', db_index=True)
    
    # --- Concurrency Locking Fields ---
    # Prevents "Race Conditions" where two people edit simultaneously
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='locked_articles'
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    #increases speed for updated at
    updated_at = models.DateTimeField(auto_now=True , db_index=True)

    def __str__(self):
        return f"{self.title} | {self.status}"

    class Meta:
        app_label = 'content'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['locked_by', 'status']),
        ]


class ArticleAssignment(models.Model):
    """
    Business Logic: Tracks which External Members (SMEs) are 
    appointed to specific articles by Reviewers.
    """
    article = models.ForeignKey(
        Article, 
        on_delete=models.CASCADE, 
        related_name='sme_assignments'
    )
    sme = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        limit_choices_to={'role': 'sme'},
        related_name='sme_tasks'
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='assignments_given'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'content'
        unique_together = ('article', 'sme') # Atomic protection against duplicate assignments
        # Index 4: Speeds up the "Is this SME assigned to this article?" check
        indexes = [
            models.Index(fields=['article', 'sme'], name='idx_article_sme_lookup'),
        ]

    def __str__(self):
        return f"{self.sme.full_name} assigned to {self.article.title}"


class ArticleComment(models.Model):
    """
    Feedback Loop: Supports @mentions and triggers status reverts.
    """
    article = models.ForeignKey(
        Article, 
        on_delete=models.CASCADE, 
        related_name='comments'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE
    )
    version = models.ForeignKey('ArticleVersion', on_delete=models.SET_NULL, null=True, blank=True)
    comment_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """
        Atomic Trigger: If Admin or Executive comments, 
        kick the article back to 'draft' status automatically.
        """
        with transaction.atomic():
            # Check user role from the accounts app
            if hasattr(self.user, 'group') and self.user.group in ['admin', 'executive']:
                # Update parent article status
                self.article.status = 'draft'
                # Clear any existing locks so the writer can fix it
                self.article.locked_by = None
                self.article.locked_at = None
                self.article.save()
            
            super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment by {self.user.full_name} on {self.article.title}"

    class Meta:
        app_label = 'content'


class ArticleVersion(models.Model):
    article = models.ForeignKey(
        'Article', 
        on_delete=models.CASCADE, 
        related_name='versions'
    )
    content = models.TextField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at'] 
        app_label = 'content' # Added for consistency with your other models

    def __str__(self):
        # Change 'article.title' to 'self.article.title'
        return f"Version of {self.article.title} at {self.created_at}"
    

