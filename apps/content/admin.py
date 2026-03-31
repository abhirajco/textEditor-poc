from django.contrib import admin
from .models import Content, ContentVersion, ContentAssignment, ContentComment, CommentMention


@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display =("title", "status", "author", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "author__email")


@admin.register(ContentVersion)
class ContentVersionAdmin(admin.ModelAdmin):
    list_display= ("content", "changed_by", "created_at")
    readonly_fields = ("content", "title", "body", "image_url", "changed_by", "created_at")


@admin.register(ContentAssignment)
class ContentAssignmentAdmin(admin.ModelAdmin):
    list_display = ("content", "sme", "assigned_by", "assigned_at")


@admin.register(ContentComment)
class ContentCommentAdmin(admin.ModelAdmin):
    list_display = ("content", "user", "created_at")


@admin.register(CommentMention)
class CommentMentionAdmin(admin.ModelAdmin):
    list_display = ("user", "content", "comment", "created_at")
