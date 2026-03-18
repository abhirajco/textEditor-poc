from django.contrib import admin
from .models import Task, TaskHistory, Discussion


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display  = ('title', 'stage', 'assigned_to', 'assigned_by', 'created_at')
    list_filter   = ('stage',)
    search_fields = ('title', 'assigned_to__email', 'assigned_by__email')


@admin.register(TaskHistory)
class TaskHistoryAdmin(admin.ModelAdmin):
    list_display  = ('task', 'action', 'performed_by', 'timestamp')
    list_filter   = ('action',)
    readonly_fields = ('task', 'action', 'performed_by', 'detail', 'timestamp')


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display  = ('task', 'author', 'created_at')
    search_fields = ('task__title', 'author__email')
