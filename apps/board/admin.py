from django.contrib import admin
from .models import Campaign, Event, Task, TaskHistory, Discussion


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display  =("title", "max_hierarchy_level", "created_by", "start_date", "end_date")
    search_fields =("title",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display  =("title", "campaign", "created_by", "start_date", "end_date")
    list_filter   = ("campaign",)
    search_fields = ("title",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display  =("title", "status", "priority", "campaign", "event", "assigned_to", "due_date")
    list_filter = ("status", "priority", "campaign")
    search_fields = ("title", "assigned_to__email")


@admin.register(TaskHistory)
class TaskHistoryAdmin(admin.ModelAdmin):
    list_display  = ("task", "action", "performed_by", "timestamp")
    readonly_fields = ("task", "action", "performed_by", "detail", "timestamp")


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ("task", "author", "created_at")
