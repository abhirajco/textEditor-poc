from rest_framework import serializers
from .models import Article

class ArticleSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.full_name', read_only=True)
    locked_by_name = serializers.CharField(source='locked_by.full_name', read_only=True, default="None")

    class Meta:
        model = Article
        fields = [
            'id', 'title', 'content', 'status', 
            'author_name','image_url', 'locked_by_name', 
            'created_at', 'updated_at'
        ]

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None

   