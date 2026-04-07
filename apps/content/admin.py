from django.contrib import admin
from .models import (
    Content, ContentVersion, ContentAssignment, ContentComment,
    CommentMention, ContentInitiationForm, ContentHistory,
)


@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display = (
        "title", "status", "author",
        "internal_approval", "marketing_approval", "stakeholder_approval",
        "locked_permanently", "all_approved_at", "created_at",
    )
    list_filter  = (
        "status",
        "internal_approval", "marketing_approval", "stakeholder_approval",
        "locked_permanently",
    )
    search_fields = ("title", "author__email")
    readonly_fields = ("content_id", "all_approved_at", "created_at", "updated_at")

    fieldsets = (
        ("Content", {
            "fields": ("content_id", "title", "body", "image", "content_type", "tags"),
        }),
        ("Relations", {
            "fields": ("author", "campaign", "event", "task_id"),
        }),
        ("Status & Locking", {
            "fields": ("status", "locked_by", "locked_at", "locked_permanently"),
        }),
        ("Approvals", {
            "fields": (
                "internal_approval", "marketing_approval",
                "stakeholder_approval", "all_approved_at",
            ),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(ContentVersion)
class ContentVersionAdmin(admin.ModelAdmin):
    list_display    = ("content", "changed_by", "created_at")
    readonly_fields = ("content", "title", "body", "image_url", "changed_by", "created_at")


@admin.register(ContentAssignment)
class ContentAssignmentAdmin(admin.ModelAdmin):
    list_display = ("content", "sme", "executive", "assigned_by", "assigned_at")


@admin.register(ContentComment)
class ContentCommentAdmin(admin.ModelAdmin):
    list_display  = ("content", "user", "resolved", "created_at")
    list_filter   = ("resolved",)


@admin.register(CommentMention)
class CommentMentionAdmin(admin.ModelAdmin):
    list_display = ("user", "content", "comment", "created_at")


@admin.register(ContentInitiationForm)
class ContentInitiationFormAdmin(admin.ModelAdmin):
    list_display  = ("title", "created_by", "sme", "created_at")
    search_fields = ("title", "created_by__email")


@admin.register(ContentHistory)
class ContentHistoryAdmin(admin.ModelAdmin):
    list_display    = ("content", "action_type", "performed_by", "timestamp")
    list_filter     = ("action_type",)
    readonly_fields = ("content", "action_type", "performed_by", "note", "timestamp")
