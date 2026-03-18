from rest_framework import serializers
from .models import Task, TaskHistory, Discussion


class DiscussionSerializer(serializers.ModelSerializer):
    author_name  =serializers.CharField(source='author.full_name', read_only=True)
    author_email = serializers.CharField(source='author.email',read_only=True)

    class Meta:
        model  = Discussion
        fields = ['id', 'author_name', 'author_email', 'message', 'created_at']


class TaskHistorySerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source='performed_by.full_name', read_only=True)

    class Meta:
        model  =TaskHistory
        fields =['id', 'action', 'performed_by_name', 'detail', 'timestamp']


class TaskSerializer(serializers.ModelSerializer):
    assigned_by_name = serializers.CharField(source='assigned_by.full_name', read_only=True)
    assigned_by_email= serializers.CharField(source='assigned_by.email', read_only=True)
    assigned_to_name= serializers.CharField(source='assigned_to.full_name', read_only=True)
    assigned_to_email= serializers.CharField(source='assigned_to.email', read_only=True)
    last_transferred_by_name = serializers.CharField(source='last_transferred_by.full_name', read_only=True)
    discussion= DiscussionSerializer(many=True, read_only=True)
    history= TaskHistorySerializer(many=True, read_only=True)

    class Meta:
        model  = Task
        fields = [
            'id', 'title', 'description', 'stage',
            'assigned_by', 'assigned_by_name', 'assigned_by_email',
            'assigned_to', 'assigned_to_name', 'assigned_to_email',
            'last_transferred_by_name',
            'created_at', 'updated_at',
            'discussion', 'history',
        ]
        read_only_fields = [
            'assigned_by', 'last_transferred_by',
            'created_at', 'updated_at',
        ]


class TaskListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views — excludes discussion & history."""
    assigned_by_name = serializers.CharField(source='assigned_by.full_name', read_only=True)
    assigned_to_name= serializers.CharField(source='assigned_to.full_name', read_only=True)
    assigned_to_email= serializers.CharField(source='assigned_to.email', read_only=True)

    class Meta:
        model  = Task
        fields = [
            'id', 'title', 'stage',
            'assigned_by_name',
            'assigned_to_name', 'assigned_to_email',
            'created_at', 'updated_at',
        ]
