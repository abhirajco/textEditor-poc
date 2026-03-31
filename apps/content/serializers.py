from rest_framework import serializers
from .models import Content, ContentVersion, ContentAssignment, ContentComment


class ContentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)
    locked_by_name = serializers.CharField(source="locked_by.full_name", read_only=True)

    class Meta:
        model  = Content
        fields = [
            "content_id", "title", "body", "image",
            "author", "author_name",
            "status",
            "locked_by", "locked_by_name", "locked_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["content_id", "author", "created_at", "updated_at"]
