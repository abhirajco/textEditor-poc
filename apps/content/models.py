from django.db import models
from django.conf import settings

class ArticleDraft(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft/Pending'),
        ('published', 'Published'),
        ('rejected', 'Rejected - Needs Edit')
    ]
    
    title = models.CharField(max_length=255)
    original_author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="authored_articles"
    )
    # The "Flag" - Only this person can save a new version
    flag_holder = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="current_flags"
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class ArticleVersion(models.Model):
    """
    Every time a writer saves, a new row is created here.
    Feedback and Votes are tied directly to this specific 'edit'.
    """
    article = models.ForeignKey(ArticleDraft, on_delete=models.CASCADE, related_name="versions")
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content_snapshot = models.TextField()
    
    # We store feedback directly as JSON or a simple field if you don't want a separate table
    # This keeps 'all the feedbacks given to the draft' inside the version record
    approver_comments = models.JSONField(default=list)  # Stores: [{"approver": "name", "comment": "...", "vote": True}]
    
    total_upvotes = models.IntegerField(default=0)
    total_downvotes = models.IntegerField(default=0)
    
    edited_at = models.DateTimeField(auto_now_add=True)

class PublishedContent(models.Model):
    """The Final Archive. Admin-controlled only."""
    draft_reference = models.OneToOneField(ArticleDraft, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    final_content = models.TextField()
    
    # Add unique related_names here:
    original_author = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="published_authored_set" # Change this
    )
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="published_edited_set"   # And this
    )
    
    published_at = models.DateTimeField(auto_now_add=True)