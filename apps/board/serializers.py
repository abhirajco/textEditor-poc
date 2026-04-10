from rest_framework import serializers
from .models import Campaign, Event, Task, TaskHistory, Discussion


class CampaignSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    event_count= serializers.SerializerMethodField()
    task_count= serializers.SerializerMethodField()

    class Meta:
        model  = Campaign
        fields = [
            "campaign_id", "title", "description",
            "start_date", "end_date",
            "max_hierarchy_level",
            "created_by", "created_by_name",
            "event_count", "task_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["campaign_id", "created_by", "created_at", "updated_at"]

    def get_event_count(self, obj):
        return obj.events.count()

    def get_task_count(self, obj):
        return obj.task.count()


class EventSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    campaign_title = serializers.CharField(source="campaign.title", read_only=True)
    task_count= serializers.SerializerMethodField()

    class Meta:
        model  = Event
        fields = [
            "event_id", "title", "description",
            "start_date", "end_date",
            "campaign", "campaign_title",
            "created_by", "created_by_name",
            "task_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["event_id", "created_by", "created_at", "updated_at"]

    def get_task_count(self, obj):
        return obj.task.count()


class DiscussionSerializer(serializers.ModelSerializer):
    author_name  =serializers.CharField(source="author.full_name", read_only=True)
    author_email= serializers.CharField(source="author.email",     read_only=True)

    class Meta:
        model= Discussion
        fields = ["discussion_id", "author_name", "author_email", "message", "created_at"]


class TaskHistorySerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source="performed_by.full_name", read_only=True)

    class Meta:
        model = TaskHistory
        fields = ["history_id", "action", "performed_by_name", "detail", "timestamp"]


class TaskSerializer(serializers.ModelSerializer):
    assigned_by_name = serializers.CharField(source="assigned_by.full_name",         read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name",         read_only=True)
    assigned_to_email = serializers.CharField(source="assigned_to.email",             read_only=True)
    last_transferred_by_name = serializers.CharField(source="last_transferred_by.full_name", read_only=True)
    tags_list = serializers.SerializerMethodField()
    discussion = DiscussionSerializer(many=True, read_only=True)
    history = TaskHistorySerializer(many=True, read_only=True)
    subtask_count = serializers.SerializerMethodField()
    campaign_title = serializers.CharField(source="campaign.title", read_only=True)
    event_title = serializers.CharField(source="event.title",    read_only=True)
    parent_task_title = serializers.CharField(source="parent_task.title", read_only=True)
    depth = serializers.SerializerMethodField()

    class Meta:
        model  = Task
        fields = [
            "task_id", "title", "description",
            "tags", "tags_list",
            "priority", "marketing_type", "due_date",
            "status",
            "campaign", "campaign_title",
            "event", "event_title",
            "parent_task", "parent_task_title",
            "subtask_count", "depth",
            "assigned_by", "assigned_by_name",
            "assigned_to", "assigned_to_name", "assigned_to_email",
            "last_transferred_by_name",
            "created_at", "updated_at",
            "discussion", "history",
        ]
        read_only_fields = ["task_id", "assigned_by", "last_transferred_by", "created_at", "updated_at"]

    def get_tags_list(self, obj):
        return obj.get_tags_list()

    def get_subtask_count(self, obj):
        return obj.subtasks.count()

    def get_depth(self, obj):
        return obj.get_depth()


class TaskListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views — no discussion or history."""
    assigned_by_name = serializers.CharField(source="assigned_by.full_name",read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name",read_only=True)
    assigned_to_email = serializers.CharField(source="assigned_to.email", read_only=True)
    tags_list = serializers.SerializerMethodField()
    subtask_count = serializers.SerializerMethodField()
    campaign_title = serializers.CharField(source="campaign.title", read_only=True)
    event_title  = serializers.CharField(source="event.title", read_only=True)
    depth = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "task_id", "title",
            "tags", "tags_list",
            "priority", "marketing_type", "due_date",
            "status",
            "campaign", "campaign_title",
            "event", "event_title",
            "parent_task",
            "subtask_count", "depth",
            "assigned_by_name",
            "assigned_to_name", "assigned_to_email",
            "created_at", "updated_at",
        ]

    def get_tags_list(self, obj):
        return obj.get_tags_list()

    def get_subtask_count(self, obj):
        return obj.subtasks.count()

    def get_depth(self, obj):
        return obj.get_depth()
