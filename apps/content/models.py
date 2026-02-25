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
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='authored_articles'
    )
    # Track users mentioned in the content/description
    mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='mentioned_in_articles', 
        blank=True
    )
    
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    
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
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} | {self.status}"

    class Meta:
        app_label = 'content'
        ordering = ['-updated_at']


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
    


# from django.db import models
# from django.conf import settings
# from django.utils import timezone

# class Article(models.Model):
#     STATUS_CHOICES = [
#         ('draft', 'Draft'),
#         ('pending_executive', 'Pending Executive Review'),
#         ('pending_admin', 'Pending Admin Review'),
#         ('published', 'Published'),
#     ]

#     title = models.CharField(max_length=255)
#     content = models.TextField()
#     author = models.ForeignKey(
#         settings.AUTH_USER_MODEL, 
#         on_delete=models.CASCADE, 
#         related_name='authored_articles'
#     )
#     status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    
#     # --- Concurrency Locking Fields ---
#     # Only one person (Writer, Reviewer, or SME) can edit at a time
#     locked_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL, 
#         on_delete=models.SET_NULL, 
#         null=True, 
#         blank=True, 
#         related_name='locked_articles'
#     )
#     locked_at = models.DateTimeField(null=True, blank=True)

#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     def __str__(self):
#         return f"{self.title} - {self.status}"

#     class Meta:
#         ordering = ['-updated_at']


# class ArticleAssignment(models.Model):
#     """
#     Table to track which External Members (SMEs) are appointed to 
#     specific articles by Reviewers.
#     """
#     article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='sme_assignments')
#     sme = models.ForeignKey(
#         settings.AUTH_USER_MODEL, 
#         on_delete=models.CASCADE, 
#         limit_choices_to={'role': 'sme'}
#     )
#     assigned_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL, 
#         on_delete=models.SET_NULL, 
#         null=True, 
#         related_name='assignments_given'
#     )
#     assigned_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         unique_together = ('article', 'sme') # Prevent duplicate assignments

#     def __str__(self):
#         return f"{self.sme.full_name} assigned to {self.article.title}"


# class ArticleComment(models.Model):
#     """
#     Table for feedback. If an Executive or Admin comments, 
#     the status automatically reverts to 'draft'.
#     """
#     article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='comments')
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
#     comment_text = models.TextField()
#     created_at = models.DateTimeField(auto_now_add=True)

#     def save(self, *args, **kwargs):
#         # Business Logic Trigger: 
#         # If any Executive or Admin likes the content, they move it forward (via View).
#         # If they add a comment (requesting changes), it kicks back to Draft.
#         if self.user.group in ['admin', 'executive']:
#             self.article.status = 'draft'
#             self.article.save()
#         super().save(*args, **kwargs)

#     def __str__(self):
#         return f"Comment by {self.user.full_name} on {self.article.title}"
