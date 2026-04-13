from rest_framework import serializers
from .models import Content, ContentVersion, ContentAssignment, ContentComment, ContentInitiationForm


class ContentSerializer(serializers.ModelSerializer):
    author_name    = serializers.CharField(source="author.full_name", read_only=True)
    locked_by_name = serializers.CharField(
        source="locked_by.full_name", read_only=True, allow_null=True
    )
    can_publish_now = serializers.SerializerMethodField()

    class Meta:
        model  = Content
        fields = [
            # Identity
            "content_id", "title", "body", "image",
            "content_type", "tags",
            "campaign_id", "event_id", "task_id",

            # Authorship
            "author", "author_name",

            # Status & locking
            "status",
            "locked_by", "locked_by_name", "locked_at",
            "locked_permanently",

            # Approval flags
            "internal_approval",
            "marketing_approval",
            "stakeholder_approval",
            "all_approved_at",

            # Computed
            "can_publish_now",

            # Timestamps
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "content_id", "author", "task_id",
            "locked_permanently", "all_approved_at",
            "created_at", "updated_at",
        ]

    def get_can_publish_now(self, obj):
        return (
            obj.internal_approval
            and obj.marketing_approval
            and obj.stakeholder_approval
            and obj.status == "approved"
            and not obj.locked_permanently
        )


class ContentVersionSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.full_name", read_only=True, allow_null=True)

    class Meta:
        model  = ContentVersion
        fields = ["version_id", "content", "title", "body", "image_url",
                  "changed_by", "changed_by_name", "created_at"]
        read_only_fields = ["version_id", "created_at"]


class ContentCommentSerializer(serializers.ModelSerializer):
    user_name  = serializers.CharField(source="user.full_name", read_only=True)
    user_role  = serializers.CharField(source="user.role",      read_only=True)
    user_group = serializers.CharField(source="user.group",     read_only=True)

    class Meta:
        model  = ContentComment
        fields = ["comment_id", "content", "user", "user_name", "user_role", "user_group",
                  "comment_text", "resolved", "created_at"]
        read_only_fields = ["comment_id", "created_at"]


class ContentInitiationFormSerializer(serializers.ModelSerializer):
    sme_name = serializers.CharField(source="sme.full_name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    content_id = serializers.UUIDField(source="content.content_id", read_only=True)

    class Meta:
        model = ContentInitiationForm
        fields = [
            "form_id",
            "title",
            "brief",
            "content_type",
            "campaign",
            "event",
            "sme",
            "sme_name",
            "created_by",
            "created_by_name",
            "content",
            "content_id",
            "created_at",
        ]




# from rest_framework import serializers
# from .models import Content, ContentVersion, ContentAssignment, ContentComment


# class ContentSerializer(serializers.ModelSerializer):
#     author_name    = serializers.CharField(source="author.full_name", read_only=True)
#     locked_by_name = serializers.CharField(
#         source="locked_by.full_name", read_only=True, allow_null=True
#     )
#     can_publish_now = serializers.SerializerMethodField()

#     class Meta:
#         model  = Content
#         fields = [
#             # Identity
#             "content_id", "title", "body", "image",
#             "content_type", "tags",
#             "campaign_id", "event_id", "task_id",

#             # Authorship
#             "author", "author_name",

#             # Status & locking
#             "status",
#             "locked_by", "locked_by_name", "locked_at",
#             "locked_permanently",

#             # Approval flags
#             "internal_approval",
#             "marketing_approval",
#             "stakeholder_approval",
#             "all_approved_at",

#             # Computed
#             "can_publish_now",

#             # Timestamps
#             "created_at", "updated_at",
#         ]
#         read_only_fields = [
#             "content_id", "author", "task_id",
#             "locked_permanently", "all_approved_at",
#             "created_at", "updated_at",
#         ]

#     def get_can_publish_now(self, obj):
#         return (
#             obj.internal_approval
#             and obj.marketing_approval
#             and obj.stakeholder_approval
#             and obj.status != "published"
#             and not obj.locked_permanently
#         )


# class ContentVersionSerializer(serializers.ModelSerializer):
#     changed_by_name = serializers.CharField(source="changed_by.full_name", read_only=True, allow_null=True)

#     class Meta:
#         model  = ContentVersion
#         fields = ["version_id", "content", "title", "body", "image_url",
#                   "changed_by", "changed_by_name", "created_at"]
#         read_only_fields = ["version_id", "created_at"]


# class ContentCommentSerializer(serializers.ModelSerializer):
#     user_name  = serializers.CharField(source="user.full_name", read_only=True)
#     user_role  = serializers.CharField(source="user.role",      read_only=True)
#     user_group = serializers.CharField(source="user.group",     read_only=True)

#     class Meta:
#         model  = ContentComment
#         fields = ["comment_id", "content", "user", "user_name", "user_role", "user_group",
#                   "comment_text", "resolved", "created_at"]
#         read_only_fields = ["comment_id", "created_at"]
