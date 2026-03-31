"""
Content views — unified save/edit/submit flow.
Renamed from Article to Content throughout.
"""
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import Content, ContentAssignment, ContentComment, ContentVersion, CommentMention
from accounts.models import User
from utils.notifications.services import handle_mentions_and_notifications
from .serializers import ContentSerializer
from utils.permissions.base import HasRBACPermission
from django.db.models import OuterRef, Subquery
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers


# ── 1. LIST VIEWS ─────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ActiveContentListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "feedback", "admin"]

    def get(self, request):
        cache_key   = "active_contents_list"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        contents   = Content.objects.exclude(status="published").order_by("-updated_at")
        serializer = ContentSerializer(contents, many=True)
        cache.set(cache_key, serializer.data, timeout=300)
        return Response(serializer.data)


@extend_schema(tags=["Content"])
class PublishedContentListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "feedback", "admin"]

    def get(self, request):
        cache_key   = "published_contents_list"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        contents   = Content.objects.filter(status="published").order_by("-updated_at")
        serializer = ContentSerializer(contents, many=True)
        cache.set(cache_key, serializer.data, timeout=900)
        return Response(serializer.data)


# ── 2. CONTENT DETAIL ─────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ContentDetailView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "feedback", "admin"]

    def get(self, request, content_id):
        try:
            c         = Content.objects.get(content_id=content_id)
            is_locked = c.locked_by is not None and c.locked_by != request.user
            return Response({
                "content_id": str(c.content_id),
                "title":      c.title,
                "body":       c.body,
                "image_url":  c.image.url if c.image else None,
                "status":     c.status,
                "author":     c.author.full_name,
                "locked_by":  c.locked_by.full_name if c.locked_by else None,
                "is_locked":  is_locked,
            })
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)


# ── 3. LOCK ───────────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ContentLock(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "update"]

    def post(self, request, content_id):
        with transaction.atomic():
            try:
                c = Content.objects.select_for_update().get(content_id=content_id)
                if request.user.role == "sme":
                    if not ContentAssignment.objects.filter(content=c, sme=request.user).exists():
                        return Response({"error": "You are not assigned to this content."}, status=403)
                if c.locked_by and c.locked_by != request.user:
                    return Response({"error": f"Locked by {c.locked_by.full_name}"}, status=423)
                c.locked_by   = request.user
                c.locked_at   = timezone.now()
                c._skip_version = True
                c.save()
                return Response({"message": "Lock acquired."})
            except Content.DoesNotExist:
                return Response({"error": "Content not found."}, status=404)

    def delete(self, request, content_id):
        try:
            c = Content.objects.get(content_id=content_id)
            if c.locked_by == request.user:
                c.locked_by   = None
                c.locked_at   = None
                c._skip_version = True
                c.save()
                return Response({"message": "Lock released."})
            return Response({"error": "You do not hold the lock."}, status=403)
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)


# ── 4. UNIFIED SAVE VIEW ──────────────────────────────────────────────────────

@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="SaveContentRequest",
        fields={
            "title":           drf_serializers.CharField(),
            "body":            drf_serializers.CharField(),
            "content_id":      drf_serializers.UUIDField(required=False),
            "image":           drf_serializers.ImageField(required=False),
            "submit":          drf_serializers.BooleanField(required=False, default=False),
            "notify_user_ids": drf_serializers.ListField(
                                   child=drf_serializers.UUIDField(), required=False),
        }
    )
)
class SaveContentView(APIView):
    """
    POST /api/content/contents/save/

    A — No content_id: creates fresh content, auto-acquires lock.
    B — content_id, submit=false: saves draft (lock required).
    C — content_id, submit=true: submits for review, notifies selected users.
    """
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "update"]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request):
        title      = request.data.get("title", "").strip()
        body       = request.data.get("body", "").strip()
        content_id = request.data.get("content_id")
        submit     = request.data.get("submit", False)
        notify_ids = request.data.get("notify_user_ids", [])
        image_file = request.FILES.get("image")

        if not title:
            return Response({"error": "title is required."}, status=400)
        if not body:
            return Response({"error": "body is required."}, status=400)
        if submit and not notify_ids:
            return Response({"error": "notify_user_ids required when submit=true."}, status=400)

        try:
            with transaction.atomic():
                user = request.user

                if not content_id:
                    # Scenario A — fresh content
                    c = Content.objects.create(
                        title = title,
                        body = body,
                        author= user,
                        status = "draft",
                        locked_by = user,
                        locked_at = timezone.now(),
                    )
                    if image_file:
                        c.image = image_file
                    c._version_data = {"title": title, "body": body,
                                       "image_url": c.image.url if c.image else None,
                                       "changed_by_id": str(user.user_id)}
                    c.save()
                    return Response({
                        "content_id": str(c.content_id),
                        "message":    "Draft created. Lock auto-acquired.",
                        "status":     c.status,
                    }, status=201)

                # Scenario B/C — existing content
                c = Content.objects.select_for_update().get(content_id=content_id)

                is_author= (c.author == user)
                is_reviewer = (user.role == "reviewer")
                is_assigned_sme = (
                    user.role == "sme" and
                    ContentAssignment.objects.filter(content=c, sme=user).exists()
                )
                if not (is_author or is_reviewer or is_assigned_sme):
                    return Response({"error": "Access denied."}, status=403)

                if c.locked_by is None:
                    return Response({"error": "Acquire the lock first."}, status=423)
                if c.locked_by != user:
                    return Response({"error": f"Locked by {c.locked_by.full_name}."}, status=423)

                c.title = title
                c.body = body
                if image_file:
                    c.image = image_file

                c._version_data = {"title": title, "body": body,
                                   "image_url": c.image.url if c.image else None,
                                   "changed_by_id": str(user.user_id)}

                if submit:
                    c.status = "pending_reviewer"
                    c.locked_by = None
                    c.locked_at = None
                    c.save()
                    from content.tasks import send_approval_email_task
                    send_approval_email_task.delay(
                        user_ids   = [str(uid) for uid in notify_ids],
                        content_id = str(c.content_id),
                        stage      = "pending_reviewer",
                    )
                    return Response({"content_id": str(c.content_id), "status": c.status,
                                     "message": "Submitted for review."})
                else:
                    c.save()
                    return Response({"content_id": str(c.content_id), "status": c.status,
                                     "message": "Draft saved, version created."})

        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


# ── 5. REVIEWER LIST ─────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ReviewerListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write"]

    def get(self, request):
        users = User.objects.filter(role__in=["reviewer","writer"], is_active=True).exclude(user_id=request.user.user_id)
        data  = [{"user_id": str(u.user_id), "full_name": u.full_name, "email": u.email, "role": u.role} for u in users]
        return Response(data)


# ── 6. NOTIFY CANDIDATES ─────────────────────────────────────────────────────

@extend_schema(
    tags=["Content"],
    parameters=[OpenApiParameter("stage", OpenApiTypes.STR, OpenApiParameter.QUERY,
                                  enum=["pending_executive","pending_admin"])]
)
class NotifyCandidatesView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["feedback", "promote", "admin"]

    def get(self, request, content_id):
        stage = request.query_params.get("stage", "")
        role_map = {"pending_executive": "exec_approver", "pending_admin": "admin"}
        target_role = role_map.get(stage)
        if not target_role:
            return Response({"error": "stage must be pending_executive or pending_admin"}, status=400)
        users = User.objects.filter(role=target_role, is_active=True)
        data  = [{"user_id": str(u.user_id), "full_name": u.full_name, "email": u.email} for u in users]
        return Response(data)


# ── 7. ASSIGN SME ────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Content"],
    request=inline_serializer(name="AssignSMERequest",
                               fields={"sme_id": drf_serializers.UUIDField()})
)
class AssignSMEView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["feedback"]

    def post(self, request, content_id):
        sme_id = request.data.get("sme_id")
        try:
            with transaction.atomic():
                c   = Content.objects.select_for_update().get(content_id=content_id)
                sme = User.objects.get(user_id=sme_id, role="sme")
                assignment, created = ContentAssignment.objects.get_or_create(
                    content=c, sme=sme, defaults={"assigned_by": request.user}
                )
                if created:
                    from content.tasks import send_sme_assignment_email_task
                    send_sme_assignment_email_task.delay(str(c.content_id))
                    return Response({"message": f"Assigned {sme.full_name}."})
                return Response({"error": "SME already assigned."}, status=400)
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except User.DoesNotExist:
            return Response({"error": "SME not found."}, status=404)


# ── 8. APPROVE ───────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Content"],
    request=inline_serializer(name="ApproveContentRequest",
                               fields={"notify_user_ids": drf_serializers.ListField(child=drf_serializers.UUIDField())})
)
class ApproveContent(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["feedback", "admin", "promote"]

    def post(self, request, content_id):
        notify_ids = request.data.get("notify_user_ids", [])
        try:
            with transaction.atomic():
                c         = Content.objects.select_for_update().get(content_id=content_id)
                user      = request.user
                user_role = user.role
                from content.tasks import send_approval_email_task

                if c.status == "pending_reviewer":
                    if user_role not in ["reviewer", "sme"]:
                        return Response({"error": "Only reviewers or SMEs can approve at this stage."}, status=403)
                    if user_role == "sme" and not ContentAssignment.objects.filter(content=c, sme=user).exists():
                        return Response({"error": "Not the assigned SME."}, status=403)
                    if not notify_ids:
                        return Response({"error": "notify_user_ids required."}, status=400)
                    c.status = "pending_executive"
                    c.save()
                    send_approval_email_task.delay([str(u) for u in notify_ids], str(c.content_id), "pending_executive")
                    return Response({"message": "Sent to executives.", "status": c.status})

                elif user_role == "exec_approver" and c.status == "pending_executive":
                    if not notify_ids:
                        return Response({"error": "notify_user_ids required."}, status=400)
                    c.status = "pending_admin"
                    c.save()
                    send_approval_email_task.delay([str(u) for u in notify_ids], str(c.content_id), "pending_admin")
                    return Response({"message": "Sent to admins.", "status": c.status})

                elif user_role == "admin" and c.status == "pending_admin":
                    c.status = "published"
                    c.save()
                    return Response({"message": "Content published!", "status": c.status})

                return Response({"error": "Invalid stage or permissions."}, status=403)
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)


# ── 9. VERSION HISTORY ───────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ContentVersionHistory(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "feedback", "admin", "promote"]

    def get(self, request, content_id):
        try:
            c  = Content.objects.get(content_id=content_id)
            user = request.user
            is_sme = user.role == "sme" and ContentAssignment.objects.filter(content=c, sme=user).exists()
            if not (c.author == user or user.role in ["reviewer","admin","exec_approver"] or is_sme):
                return Response({"error": "Permission denied."}, status=403)
            versions = ContentVersion.objects.filter(content=c).select_related("changed_by")
            data = [{
                "version_id":      str(v.version_id),
                "changed_by": v.changed_by.full_name if v.changed_by else "Unknown",
                "role": v.changed_by.role if v.changed_by else "N/A",
                "timestamp": v.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "title": v.title,
                "image_url": v.image_url,
                "body_preview":v.body[:100] + "...",
            } for v in versions]
            return Response({"content_id": str(c.content_id), "title": c.title,
                             "status": c.status, "history": data})
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)


# ── 10. VIEW SPECIFIC VERSION ────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ContentVersionDetailView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "feedback", "admin"]

    def get(self, request, content_id, version_id):
        try:
            c = Content.objects.get(content_id=content_id)
            v = ContentVersion.objects.get(version_id=version_id, content=c)
            return Response({
                "version_id": str(v.version_id),
                "content_id": str(c.content_id),
                "title": v.title,
                "body": v.body,
                "image_url": v.image_url,
                "changed_by":v.changed_by.full_name if v.changed_by else "Unknown",
                "saved_at": v.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except ContentVersion.DoesNotExist:
            return Response({"error": "Version not found."}, status=404)


# ── 11. LATEST VERSION ───────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class LatestVersionView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "feedback", "admin"]

    def get(self, request, content_id):
        try:
            c = Content.objects.get(content_id=content_id)
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        v = ContentVersion.objects.filter(content=c).order_by("-created_at").first()
        if not v:
            return Response({"error": "No versions found."}, status=404)
        return Response({"version_id": str(v.version_id), "content_id": str(c.content_id),
                         "title": v.title, "body": v.body, "image_url": v.image_url,
                         "changed_by": v.changed_by.full_name if v.changed_by else "Unknown",
                         "saved_at": v.created_at.strftime("%Y-%m-%d %H:%M:%S")})


# ── 12. COMMENT ──────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"],
               request=inline_serializer(name="WriteCommentRequest",
                                          fields={"comment_text": drf_serializers.CharField()}))
class WriteComment(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["feedback", "admin"]

    def post(self, request, content_id):
        text = request.data.get("comment_text", "").strip()
        if not text:
            return Response({"error": "comment_text is required."}, status=400)
        try:
            with transaction.atomic():
                c = Content.objects.select_for_update().get(content_id=content_id)
                if request.user.role == "sme":
                    if not ContentAssignment.objects.filter(content=c, sme=request.user).exists():
                        return Response({"error": "Not assigned to this content."}, status=403)
                c.status= "draft"
                c.locked_by = None
                c.locked_at = None
                c._skip_version = True
                c.save()
                latest = ContentVersion.objects.filter(content=c).order_by("-created_at").first()
                comment = ContentComment.objects.create(content=c, user=request.user,
                                                        comment_text=text, version=latest)
                cache.delete(f"content_comments_{content_id}")
                handle_mentions_and_notifications(text, c, comment, sender=request.user)
                return Response({"message": "Feedback recorded.", "new_status": c.status})
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


# ── 13. COMMENT HISTORY ──────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ContentCommentHistoryView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "feedback", "admin", "promote"]

    def get(self, request, content_id):
        cache_key = f"content_comments_{content_id}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        try:
            c = Content.objects.get(content_id=content_id)
            version_subquery = ContentVersion.objects.filter(
                content=c, created_at__lte=OuterRef("created_at")
            ).order_by("-created_at").values("version_id")[:1]
            comments = ContentComment.objects.filter(content=c).select_related("user").annotate(
                detected_version_id=Subquery(version_subquery)
            ).order_by("created_at")
            data = [{"comment_id": str(cm.comment_id), "user": cm.user.full_name,
                     "role": cm.user.role, "text": cm.comment_text,
                     "timestamp": cm.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                     "version_at_time": str(cm.detected_version_id) if cm.detected_version_id else "Initial Draft"}
                    for cm in comments]
            response_data = {"content_title": c.title, "comments": data}
            cache.set(cache_key, response_data, timeout=600)
            return Response(response_data)
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)


# ── 14. COMMENT EDIT/DELETE ──────────────────────────────────────────────────

@extend_schema(tags=["Content"],
               request=inline_serializer(name="CommentEditRequest",
                                          fields={"comment_text": drf_serializers.CharField()}))
class CommentEditDelete(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles= ["feedback", "admin"]

    def patch(self, request, comment_id):
        try:
            comment = ContentComment.objects.get(comment_id=comment_id)
            if comment.user != request.user:
                return Response({"error": "You did not write this comment."}, status=403)
            new_text = request.data.get("comment_text", "").strip()
            if not new_text:
                return Response({"error": "comment_text required."}, status=400)
            comment.comment_text = new_text
            comment.save()
            cache.delete(f"content_comments_{comment.content.content_id}")
            return Response({"message": "Comment updated."})
        except ContentComment.DoesNotExist:
            return Response({"error": "Comment not found."}, status=404)

    def delete(self, request, comment_id):
        try:
            comment = ContentComment.objects.get(comment_id=comment_id)
            if comment.user != request.user:
                return Response({"error": "You can only delete your own comments."}, status=403)
            content_id = comment.content.content_id
            comment.delete()
            cache.delete(f"content_comments_{content_id}")
            return Response({"message": "Comment removed."})
        except ContentComment.DoesNotExist:
            return Response({"error": "Comment not found."}, status=404)
