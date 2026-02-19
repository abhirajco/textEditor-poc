from rest_framework import serializers
from .models import ArticleDraft, ArticleVersion, PublishedContent

class ArticleVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleVersion
        fields = ['id', 'editor', 'content_snapshot', 'approver_comments', 'total_upvotes', 'total_downvotes', 'edited_at']

class ArticleDraftSerializer(serializers.ModelSerializer):
    # Fixed 'read_all' to 'read_only'
    versions = ArticleVersionSerializer(many=True, read_only=True)
    
    class Meta:
        model = ArticleDraft
        fields = ['id', 'title', 'original_author', 'flag_holder', 'status', 'created_at', 'versions']

class PublishedContentSerializer(serializers.ModelSerializer):
    author_name = serializers.ReadOnlyField(source='original_author.full_name')
    editor_name = serializers.ReadOnlyField(source='last_editor.full_name')

    class Meta:
        model = PublishedContent
        fields = ['id', 'title', 'final_content', 'author_name', 'editor_name', 'published_at']


#only for latest version
class DraftDashboardSerializer(serializers.ModelSerializer):
    # Use a MethodField to get only the latest version object
    latest_version = serializers.SerializerMethodField()
    author_name = serializers.ReadOnlyField(source='original_author.full_name')
    flag_holder_name = serializers.ReadOnlyField(source='flag_holder.full_name')

    class Meta:
        model = ArticleDraft
        fields = [
            'id', 'title', 'status', 'author_name', 
            'flag_holder_name', 'created_at', 'latest_version'
        ]

    def get_latest_version(self, obj):
        # Access the related 'versions' manager and get the last one
        last_version = obj.versions.last()
        if last_version:
            return ArticleVersionSerializer(last_version).data
        return None