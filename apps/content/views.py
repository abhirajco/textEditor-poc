"""
Content views — added .

APPROVAL FLOW:
  1. Writer submits → status becomes 'in_review'
  2. Any internal member approves → internal_approval=True
     → notifications sent to ALL executives (stakeholder) and ALL admins (marketing)
  3. Executive approves  → stakeholder_approval=True
     Admin approves      → marketing_approval=True   (these two are PARALLEL)
  4. When all 3 flags are True:
     → all_approved_at is stamped
     → status transitions to 'approved'
     → Admin gets a manual "publish now" button via POST /approve/ with action=publish
     → After 24h from approval, content is permanently locked (no comments, no edits)
  5. If ANYONE rejects → status='rejected', locked_permanently=True (no edits allowed)
  6. If a comment is added while status='in_review' OR status='approved' (within 24h)
     → reverts to 'draft', all flags reset

STAGES (5):
  draft | in_review | approved | rejected | published

STATUS COUNTS API:
  GET /api/content/contents/stats/          — draft / in_review / approved / rejected / published / total
  GET /api/content/contents/stage/<stage>/  — paginated list for a specific stage
"""

from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Q, Count, OuterRef, Subquery
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer,
)
from rest_framework import serializers as drf_serializers

from .models import Content, ContentAssignment, ContentComment, ContentVersion, CommentMention, ContentHistory, ContentInitiationForm
from .serializers import ContentSerializer, ContentInitiationFormSerializer, ContentHistorySerializer
from accounts.models import User
from utils.notifications.services import handle_mentions_and_notifications
from utils.permissions.base import HasRBACPermission
from django.utils import timezone
from django.shortcuts import get_object_or_404


LOCK_WINDOW_SECONDS =  120


def is_content_locked(content):
    """
    Returns True if content is locked after 24 hours of full approval.
    """

    if (
        content.internal_approval
        and content.marketing_approval
        and content.stakeholder_approval
        and content.all_approved_at is not None
    ):
        elapsed = timezone.now() - content.all_approved_at
        return elapsed.total_seconds() >= LOCK_WINDOW_SECONDS

    return False


def get_content_lock_error():
    """
    Standard error response for locked content.
    """
    return {
        "error": "Content is locked: the 24-hour edit window after full approval has expired."
    }


def _notify_exec_admin_and_assignees(content):
    """
    Send notifications to:
    - All admins
    - Assigned executive
    - Assigned SME
    """
    from content.tasks import send_approval_email_task

    # ✅ Get all admins
    admin_ids = list(
        User.objects.filter(group="admin", is_active=True)
        .values_list("user_id", flat=True)
    )

    # ✅ Get single assignment
    assignment = ContentAssignment.objects.select_related(
        "executive", "sme"
    ).filter(content=content).first()

    exec_id = None
    sme_id = None

    if assignment:
        if assignment.executive:
            exec_id = str(assignment.executive.user_id)
        if assignment.sme:
            sme_id = str(assignment.sme.user_id)

    # ✅ Combine all recipients
    all_ids = set(str(uid) for uid in admin_ids)

    if exec_id:
        all_ids.add(exec_id)

    if sme_id:
        all_ids.add(sme_id)

    # ✅ Send email
    if all_ids:
        send_approval_email_task.delay(
            list(all_ids),
            str(content.content_id),
            "pending_exec_admin"
        )



@extend_schema(tags=["Content"])
class ContentDetailView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "admin"]

    def get(self, request, content_id):
        try:
            c = Content.objects.get(content_id=content_id)
            is_locked = c.locked_by is not None and c.locked_by != request.user
            return Response({
                "content_id": str(c.content_id),
                "title": c.title,
                "body": c.body,
                "image_url": c.image.url if c.image else None,
                "status": c.status,
                "content_type": c.content_type,
                "tags": c.tags,
                "campaign_id":   c.campaign_id,
                "event_id": c.event_id,
                # "task_id": str(c.task_id) if c.task_id else None,
                "task_id": c.task_id,
                "author": c.author.full_name,
                "locked_by": c.locked_by.full_name if c.locked_by else None,
                "is_locked": is_locked,
                "locked_permanently": c.locked_permanently,
                "internal_approval": c.internal_approval,
                "marketing_approval":  c.marketing_approval,
                "stakeholder_approval": c.stakeholder_approval,
                "all_approved_at": c.all_approved_at.isoformat() if c.all_approved_at else None,
                "can_publish_now": (
                    c.internal_approval and c.marketing_approval and c.stakeholder_approval
                    and c.status == "approved"
                ),
            
            })
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# 3. LOCK
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ContentLock(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "update" , "admin"]

    def post(self, request, content_id):
        with transaction.atomic():
            try:
                c = Content.objects.select_for_update().get(content_id=content_id)

                # Permanently locked (rejected) content cannot be edited
                if c.locked_permanently:
                    return Response(
                        {"error": "Content is permanently locked due to rejection and cannot be edited."},
                        status=423,
                    )

                if is_content_locked(c):
                    return Response(get_content_lock_error(), status=423)

                if request.user.role == "sme":
                    if not ContentAssignment.objects.filter(content=c, sme=request.user).exists():
                        return Response({"error": "You are not assigned to this content."}, status=403)
                if c.locked_by and c.locked_by != request.user:
                    return Response({"error": f"Locked by {c.locked_by.full_name}"}, status=423)
                c.locked_by = request.user
                c.locked_at = timezone.now()
                c._skip_version = True
                c.save()
                return Response({"message": "Lock acquired."})
            except Content.DoesNotExist:
                return Response({"error": "Content not found."}, status=404)
            except Exception as e:
                return Response({"error": str(e)} , status=500)

    def delete(self, request, content_id):
        try:
            c = Content.objects.get(content_id=content_id)
            if c.locked_by == request.user:
                c.locked_by = None
                c.locked_at = None
                c._skip_version = True
                c.save()
                return Response({"message": "Lock released."})
            return Response({"error": "You do not hold the lock."}, status=403)
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)



# ─────────────────────────────────────────────────────────────────────────────
# 4. SAVE VIEW (version creation — draft mode only)
# ─────────────────────────────────────────────────────────────────────────────


@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="SaveContentRequest",
        fields={
            "title":      drf_serializers.CharField(),
            "body":       drf_serializers.CharField(),
            "content_id": drf_serializers.UUIDField(
                              help_text="ID of the existing draft content to save a new version of."),
            "image":      drf_serializers.ImageField(required=False),
        }
    )
)
class SaveContentView(APIView):
    """
    POST /api/content/contents/save/

    Creates a new version of an existing draft content.

    Rules:
      • content_id is always required 
      • Content must be in 'draft' status — saving is blocked for any other status.
      • Content must not be permanently locked (rejected).
      • The 24-hour post-full-approval edit window must not have expired.
      • The calling user must be the author and must hold the lock.
    """
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "update" , "admin"]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request):
        title = request.data.get("title", "").strip()
        body = request.data.get("body", "").strip()
        content_id = request.data.get("content_id")
        image_file = request.FILES.get("image")

        if not title:
            return Response({"error": "title is required."}, status=400)
        if not body:
            return Response({"error": "body is required."}, status=400)
        if not content_id:
            return Response({"error": "content_id is required."}, status=400)

        try:
            with transaction.atomic():
                user = request.user
                c = Content.objects.select_for_update().get(content_id=content_id)

                # ── Guard: permanently locked (rejected) ──────────────────────
                if c.locked_permanently:
                    return Response(
                        {"error": "Content is permanently locked due to rejection and cannot be edited."},
                        status=423,
                    )

                # ── Guard: 24-hour post-full-approval window expired ───────────
                # if (
                #     c.internal_approval and c.marketing_approval and c.stakeholder_approval
                #     and c.all_approved_at is not None
                # ):
                #     elapsed = (timezone.now() - c.all_approved_at).total_seconds()
                #     if elapsed >= 86400:
                #         return Response(
                #             {"error": "Content is locked: the 24-hour edit window after full approval has expired."},
                #             status=423,
                #         )

                if is_content_locked(c):
                    return Response(get_content_lock_error(), status=423)

                # ── Guard: only draft content can be saved ────────────────────
                # if c.status != "draft":
                #     return Response(
                #         {"error": f"Content cannot be saved in '{c.status}' status. Only draft content can be saved."},
                #         status=400,
                #     )

                # ── Guard: only the author may save ──────────────────────────
                # if c.author != user:
                #     return Response({"error": "Access denied. Only the author can save this content."}, status=403)

                # ── Guard: lock must be held by this user ─────────────────────
                if c.locked_by is None:
                    return Response({"error": "Acquire the lock first before saving."}, status=423)
                if c.locked_by != user:
                    return Response({"error": f"Content is locked by {c.locked_by.full_name}."}, status=423)

                # ── Apply changes & create version ────────────────────────────
                c.title = title
                c.body  = body
                if image_file:
                    c.image = image_file

                c._version_data = {
                    "title": title,
                    "body": body,
                    "image_url": c.image.url if c.image else None,
                    "changed_by_id": str(user.user_id),
                }
                c.save()

                ContentHistory.objects.create(
                    content=c, action_type="draft_saved", performed_by=user
                )
                return Response({
                    "content_id": str(c.content_id),
                    "status":     c.status,
                    "message":    "Draft version saved.",
                })

        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


# 4b. SUBMIT CONTENT VIEW (draft → preview; notifies internal members)
# ─────────────────────────────────────────────────────────────────────────────



@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="SubmitContentRequest",
        fields={
            "content_id": drf_serializers.UUIDField(
                              help_text="ID of the draft content to submit for internal review."),
        }
    )
)
class SubmitContentView(APIView):
    """
    POST /api/content/contents/submit/

    Submits a draft content for internal review (preview stage).

    On success:
      • status → 'in_review'
      • Lock is released.
      • All prior approval flags are reset.
      • All internal members with role 'writer' or 'reviewer', except the
        author, are automatically notified via email.
      • A ContentHistory record is created with action_type='submitted'.

    Rules:
      • Content must be in 'draft' status.
      • Content must not be permanently locked.
      • The 24-hour post-full-approval window must not have expired.
      • The calling user must be the author and must hold the lock.
    """
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "admin"]

    def post(self, request):
        content_id = request.data.get("content_id")

        if not content_id:
            return Response({"error": "content_id is required."}, status=400)

        try:
            with transaction.atomic():
                user = request.user
                c = Content.objects.select_for_update().get(content_id=content_id)

                # ── Guard: permanently locked ─────────────────────────────────
                if c.locked_permanently:
                    return Response(
                        {"error": "Content is permanently locked due to rejection and cannot be submitted."},
                        status=423,
                    )

                # ── Guard: 24-hour post-full-approval window ──────────────────
                # if (
                #     c.internal_approval and c.marketing_approval and c.stakeholder_approval
                #     and c.all_approved_at is not None
                # ):
                #     elapsed = (timezone.now() - c.all_approved_at).total_seconds()
                #     if elapsed >= 86400:
                #         return Response(
                #             {"error": "Content is locked: the 24-hour edit window after full approval has expired."},
                #             status=423,
                #         )


                if is_content_locked(c):
                    return Response(get_content_lock_error(), status=423)

                # ── Guard: only draft content can be submitted ────────────────
                if c.status != "draft":
                    return Response(
                        {"error": f"Only draft content can be submitted. Current status: '{c.status}'."},
                        status=400,
                    )

                # ── Guard: only the author may submit ─────────────────────────
                # if c.author != user:
                #     return Response({"error": "Access denied. Only the author can submit this content."}, status=403)

                # ── Guard: lock must be held by the author ────────────────────
                if c.locked_by is None:
                    return Response({"error": "Acquire the lock first before submitting."}, status=423)
                if c.locked_by != user:
                    return Response({"error": f"Content is locked by {c.locked_by.full_name}."}, status=423)

                # ── Collect all writers + reviewers, excluding the author ──────
                from django.contrib.auth import get_user_model
                User = get_user_model()
                internal_members = User.objects.filter(
                    role__in=["writer", "reviewer"],
                    is_active=True,
                ).exclude(user_id=user.user_id)
                notify_ids = [str(m.user_id) for m in internal_members]

                # ── Transition to in_review (preview) ────────────────────────
                c.status               = "in_review"
                c.locked_by            = None
                c.locked_at            = None
                c.internal_approval    = False
                c.marketing_approval   = False
                c.stakeholder_approval = False
                c.all_approved_at      = None
                c.save()

                # ── Fire notification emails via Celery ───────────────────────
                from content.tasks import send_approval_email_task
                send_approval_email_task.delay(
                    user_ids   = notify_ids,
                    content_id = str(c.content_id),
                    stage      = "in_review",
                )

                ContentHistory.objects.create(
                    content=c, action_type="submitted", performed_by=user,
                    note="Submitted for internal review.",
                )
                return Response({
                    "content_id":        str(c.content_id),
                    "status":            c.status,
                    "notified_count":    len(notify_ids),
                    "message":           "Content submitted for internal review. All internal members have been notified.",
                })

        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)




@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="InitiateContentRequest",
        fields={
            "title":drf_serializers.CharField(),
            "brief":  drf_serializers.CharField(),
            "content_type": drf_serializers.CharField(),
            "campaign_id": drf_serializers.CharField(),
            "tags":drf_serializers.CharField(required=False, allow_blank=True),
            "event_id": drf_serializers.CharField(required=False, allow_blank=True, allow_null=True),
        }
    )
)
class NewContentButton(APIView):
    
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write" , "admin"]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request):
     try:
        # (unchanged logic — kept from original)
        from board.models import Campaign, Event, Task, TaskHistory
        title  = request.data.get("title", "").strip()
        brief = request.data.get("brief", "").strip()
        content_type = request.data.get("content_type", "").strip()
        campaign_id  = request.data.get("campaign_id", "").strip()
        tags   = request.data.get("tags", "").strip()
        event_id = request.data.get("event_id") or None
        #sme_id = request.data.get("sme_id")  #from the form itself
        executive_id = request.data.get("executive_id")

        ex = User.objects.get(user_id=executive_id, role="exec_approver")

        if not all([title, brief, content_type, campaign_id]):
            return Response({"error": "title, brief, content_type, campaign_id and sme id are required."}, status=400)

        try:
            campaign = Campaign.objects.get(pk=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)

        event = None
        if event_id:
            try:
                event = Event.objects.get(pk=event_id, campaign=campaign)
            except Event.DoesNotExist:
                return Response({"error": "Event not found for this campaign."}, status=404)

        ##have to add the brief also in the task
        try:
            with transaction.atomic():
                task = Task.objects.create(
                    title = f"[Content] {title}",
                    description= brief,
                    campaign  = campaign,
                    event = event,
                    assigned_to  = request.user,
                    assigned_by = request.user,
                )
                TaskHistory.objects.create(
                    task         = task,
                    action       = "created",
                    performed_by = request.user,
                    detail       = f"Task created via content popup for '{title}'.",
                )
                content = Content.objects.create(
                    title  = title,
                    body = brief,
                    author= request.user,
                    status = "draft",
                    content_type = content_type,
                    tags  = tags,
                    campaign = campaign,
                    event = event,
                    task  = task,
                )
                ContentHistory.objects.create(
                    content=content, action_type="initiated", performed_by=request.user
                )
                # sme_user = User.objects.get(user_id=sme_id, role="sme")
    
                return Response({
                    "content_id": str(content.content_id),
                    "task_id":    str(task.pk),
                    "executive_id": executive_id,
                    "status":     content.status,
                    "message":    "New content created",
                }, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
     except Exception as e:
            return Response({"error": str(e)}, status=500)

###see that if the tags are getting added in task
# ─────────────────────────────────────────────────────────────────────────────
# 4b. INITIATION FORM (executive)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="InitiateContentRequest",
        fields={
            "title":drf_serializers.CharField(),
            "brief":  drf_serializers.CharField(),
            "content_type": drf_serializers.CharField(),
            "campaign_id": drf_serializers.CharField(),
            "sme_id": drf_serializers.CharField(),
            "tags":drf_serializers.CharField(required=False, allow_blank=True),
            "event_id": drf_serializers.CharField(required=False, allow_blank=True, allow_null=True),
        }
    )
)
class InitiateContentView(APIView):
    """POST /api/content/contents/initiate/ — executive fills initiation form."""
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["initiate" , "admin"]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request):
        # (unchanged logic — kept from original)
        from board.models import Campaign, Event, Task
        title  = request.data.get("title", "").strip()
        brief = request.data.get("brief", "").strip()
        content_type = request.data.get("content_type", "").strip()
        campaign_id  = request.data.get("campaign_id", "").strip()
        #tags   = request.data.get("tags", "").strip()
        event_id = request.data.get("event_id") or None
        sme_id = request.data.get("sme_id")

        if not all([title, brief, content_type, campaign_id, sme_id]):
            return Response({"error": "title, brief, content_type, campaign_id and sme id are required."}, status=400)

        try:
            campaign = Campaign.objects.get(pk=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)

        event = None
        if event_id:
            try:
                event = Event.objects.get(pk=event_id, campaign=campaign)
            except Event.DoesNotExist:
                return Response({"error": "Event not found for this campaign."}, status=404)

        ##have to add the brief also in the task
        try:
            with transaction.atomic():
                
                try:
                    sme_user = User.objects.get(pk=sme_id, role="sme")
                except sme_user.DoesNotExist:
                    return Response({"error": "SME not found."}, status=404)

                #sme_user = User.objects.get(pk=sme_id, role="sme")
                form = ContentInitiationForm.objects.create(
                    title=title,
                    brief=brief,
                    sme=sme_user,
                    created_by=request.user,
                    content_type=content_type,
                    campaign=campaign,
                    event=event,
                    # content=content,  # linking content
                )
                return Response({
                    "form_id": str(form.form_id),
                    "sme_id": sme_id,
                    "executive_id": request.user.user_id,
                    "message":    "form submitted",
                }, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


@extend_schema(tags=["Content"])
class FormListView(APIView):
    """
    
    View all initiation forms
    """
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "admin"]  # writer reviwer and admin

    def get(self, request):
        try:
            queryset = ContentInitiationForm.objects.select_related(
                "sme", "created_by", "content", "campaign", "event"
            ).all()

            
            sme_id = request.query_params.get("sme_id")
            campaign_id = request.query_params.get("campaign_id")
            created_by = request.query_params.get("created_by")

            if sme_id:
                queryset = queryset.filter(sme__user_id=sme_id)

            if campaign_id:
                queryset = queryset.filter(campaign__campaign_id=campaign_id)

            if created_by:
                queryset = queryset.filter(created_by__user_id=created_by)

            serializer = ContentInitiationFormSerializer(queryset, many=True)

            return Response({
                "count": queryset.count(),
                "results": serializer.data
            })

        except Exception as e:
            return Response({"error": str(e)}, status=500)



class ParticularFormView(APIView):
    """
    particular form
    """
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "admin"]  # adjust if needed

    def get(self, request , form_id):
        try:
    
            form = ContentInitiationForm.objects.get(form_id=form_id)

            serializer = ContentInitiationFormSerializer(form)

            return Response(serializer.data, status=200)
            
        except Exception as e:
            return Response({"error": str(e)}, status=500)


@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="InitiateContentRequest",
        fields={
            "title":drf_serializers.CharField(),
            "brief":  drf_serializers.CharField(),
            "content_type": drf_serializers.CharField(),
            "campaign_id": drf_serializers.CharField(),
            "form_id": drf_serializers.CharField(),
            "tags":drf_serializers.CharField(required=False, allow_blank=True),
            "event_id": drf_serializers.CharField(required=False, allow_blank=True, allow_null=True),
        }
    )
)
class StartFromForm(APIView):
    """POST /api/content/contents/startFromForm/ — executive fills initiation form."""
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "admin"] #only writer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request):
     try:
        # (unchanged logic — kept from original)
        from board.models import Campaign, Event, Task, TaskHistory
        title  = request.data.get("title", "").strip()
        brief = request.data.get("brief", "").strip()
        content_type = request.data.get("content_type", "").strip()
        campaign_id  = request.data.get("campaign_id", "").strip()
        tags   = request.data.get("tags", "").strip()
        event_id = request.data.get("event_id") or None
        sme_id = request.data.get("sme_id") or None  #from the form itself
        executive_id = request.data.get("created_by")
        form_id = request.data.get("form_id")

        ex = get_object_or_404(User ,user_id=executive_id)

        if not all([title, brief, content_type, campaign_id]):
            return Response({"error": "title, brief, content_type and campaign_id are required."}, status=400)

        try:
            campaign = Campaign.objects.get(pk=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)

        event = None
        if event_id:
            try:
                event = Event.objects.get(pk=event_id, campaign=campaign)
            except Event.DoesNotExist:
                return Response({"error": "Event not found for this campaign."}, status=404)

        form = get_object_or_404(ContentInitiationForm ,pk=form_id)
        
        ##have to add the brief also in the task
        try:
            with transaction.atomic():
                task = Task.objects.create(
                    title       = title,
                    campaign    = campaign,
                    event       = event,
                    assigned_to  = request.user,
                    assigned_by = ex
                )
                TaskHistory.objects.create(
                     task         = task,
                     action       = "created",
                     performed_by = request.user,
                     detail       = f"Task created via content popup for '{title}'.",
                 )
                # content = Content.objects.create(
                #     title        = title,
                #     body         = brief,
                #     author       = request.user,
                #     status       = "draft",
                #     content_type = content_type,
                #     tags         = tags,
                #     campaign     = campaign,
                #     event   = event,
                #     task = task,
                # )

                content = Content(
                    title        = title,
                    body    = brief,
                    author       = request.user,
                    status       = "draft",
                    content_type = content_type,
                    tags         = tags,
                    campaign     = campaign,
                    event        = event,
                    task         = task,
                )

                content._version_data = {
                    "title": title,
                    "body": brief,
                    "image_url": None,
                    "changed_by_id": str(request.user.user_id),
                }

                content.save()
                ContentHistory.objects.create(
                    content=content, action_type="initiated", performed_by=request.user
                )

                form.initiated = True
                form.content = content
                form.save()
                # sme_user = User.objects.get(user_id=sme_id, role="sme")
    
                return Response({
                    "content_id": str(content.content_id),
                    "task_id":    str(task.pk),
                    "sme_id": sme_id,
                    "executive_id": executive_id,
                    "status":     content.status,
                    "message":    "form submitted",
                }, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
     except Exception as e:
            return Response({"error": str(e)}, status=500)


        
# ─────────────────────────────────────────────────────────────────────────────
# 5. REVIEWER LIST
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ReviewerListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "admin"]

    def get(self, request):
        internal = User.objects.filter(group="internal", is_active=True)
        return Response([
            {"user_id": str(u.user_id), "full_name": u.full_name, "email": u.email}
            for u in internal
        ])


# ─────────────────────────────────────────────────────────────────────────────
# 6. NOTIFY CANDIDATES
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class NotifyCandidatesView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "initiate" , "admin"]

    def post(self, request, content_id):
        notify_ids = request.data.get("notify_user_ids", [])
        if not notify_ids:
            return Response({"error": "notify_user_ids required."}, status=400)
        try:
            c = Content.objects.get(content_id=content_id)
            from content.tasks import send_approval_email_task
            send_approval_email_task.delay(
                [str(uid) for uid in notify_ids], str(c.content_id), "in_review"
            )
            return Response({"message": "Notifications sent."})
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)


# ─────────────────────────────────────────────────────────────────────────────
# 6b/6c. CAMPAIGN & EVENT DROPDOWNS
# ─────────────────────────────────────────────────────────────────────────────




####have to change the logic
# ─────────────────────────────────────────────────────────────────────────────
# 7. ASSIGN SME
# ─────────────────────────────────────────────────────────────────────────────


###sme drop down
@extend_schema(tags=["Content"])
class SMEListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "admin"]

    def get(self, request):
        smes = User.objects.filter(group="external", is_active=True)
        return Response([
            {"user_id": str(u.user_id), "full_name": u.full_name, "email": u.email}
            for u in smes
        ])


@extend_schema(tags=["Content"])
class ExeListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "admin"]

    def get(self, request):
        smes = User.objects.filter(group="executive", is_active=True)
        return Response([
            {"user_id": str(u.user_id), "full_name": u.full_name, "email": u.email}
            for u in smes
        ])


@extend_schema(tags=["Content"])
class WriterListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "admin"]

    def get(self, request):
        smes = User.objects.filter(role="writer", is_active=True)
        return Response([
            {"user_id": str(u.user_id), "full_name": u.full_name, "email": u.email}
            for u in smes
        ])
    

@extend_schema(tags=["Content"])
class OnlyReviewerListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "admin"]

    def get(self, request):
        smes = User.objects.filter(role="reviewer", is_active=True)
        return Response([
            {"user_id": str(u.user_id), "full_name": u.full_name, "email": u.email}
            for u in smes
        ])


@extend_schema(tags=["Content"])
class AssignSMEndExeView(APIView):
  permission_classes = [HasRBACPermission]
  required_area = "content"
  required_roles = ["admin", "initiate" , "write"]

  def post(self, request, content_id):
    sme_id = request.data.get("sme_id")
    executive_id = request.data.get("executive_id")

    if not executive_id:
        return Response(
            {"error": "executive_id is required."},
            status=400
        )

    try:
        with transaction.atomic():
            content = Content.objects.select_for_update().get(content_id=content_id)

            # ✅ Validate Executive (required)
            try:
                executive = User.objects.get(user_id=executive_id, role="exec_approver")
            except User.DoesNotExist:
                return Response({"error": "Executive not found"}, status=404)

            # ✅ Validate SME (optional)
            sme = None
            if sme_id:
                try:
                    sme = User.objects.get(user_id=sme_id, role="sme")
                except User.DoesNotExist:
                    return Response({"error": "SME not found"}, status=404)

            # ✅ Create assignment
            assignment, created = ContentAssignment.objects.get_or_create(
                content=content,
                sme=sme,
                executive=executive,
                defaults={
                    "assigned_by": request.user,
                }
            )

            if not created:
                return Response(
                    {"error": "Assignment already exists."},
                    status=400
                )

            # ✅ Async task
            from content.tasks import send_sme_assignment_email_task
            send_sme_assignment_email_task.delay(str(content.content_id))

            return Response({
                "message": f"{'No SME' if not sme else sme.full_name} assigned under {executive.full_name}."
            })

    except Content.DoesNotExist:
        return Response({"error": "Content not found."}, status=404)

    except Exception as e:
        return Response(
            {"error": "Something went wrong.", "details": str(e)},
            status=500
        )



#for timeline
class ContentHistory2APIView(APIView):
    """
    Get full history of a specific content
    """

    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read" , "admin"]

    def get(self, request, content_id):
     try:
        try:
            content = Content.objects.get(content_id=content_id)
        except Content.DoesNotExist:
            return Response(
                {"error": "Content not found"},
                status=404
            )

        history = ContentHistory.objects.filter(content=content).select_related("performed_by")

        serializer = ContentHistorySerializer(history, many=True)

        return Response(
            {
                "content_id": str(content.content_id),
                "content_title": content.title,
                "history": serializer.data,
            },
            status=200
        )
     except Exception as e:
         return Response({"error": str(e)})




@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="ApproveOnlyRequest",
        fields={}
    )
)
class ApproveContent(APIView):
    
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["approve" , "admin"]

    INTERNAL_GROUPS = {"internal"}
    EXECUTIVE_GROUPS = {"executive"}
    ADMIN_GROUPS = {"admin"}

    def post(self, request, content_id):
        user = request.user
        group = getattr(user, "group", "")

        try:
            with transaction.atomic():
                c = Content.objects.select_for_update().get(content_id=content_id)

                if c.status != "in_review":
                    return Response(
                        {"error": f"Content must be 'in_review'. Current: {c.status}"},
                        status=400
                    )

                if c.locked_permanently:
                    return Response({"error": "Content is permanently locked."}, status=423)

                # INTERNAL APPROVAL
                if group in self.INTERNAL_GROUPS:

                    if c.author == user:  
                        return Response({"error": "Author cannot approve their own content"},status=403)
                    
                    if c.internal_approval:
                        return Response({"message": "Already internally approved"})

                    c.internal_approval = True

                    triple = c.check_and_mark_all_approved()

                    if triple:
                        c.status= "approved"

                    c.save(update_fields=["internal_approval"])

                    ContentHistory.objects.create(
                        content=c,
                        action_type="approved_internal",
                        performed_by=user
                    )

                    _notify_exec_admin_and_assignees(c)

                    return Response({"message": "Internal approval recorded"})

                # EXECUTIVE APPROVAL
                elif group in self.EXECUTIVE_GROUPS:
                    assignment = ContentAssignment.objects.select_related("executive").filter(
                                content=c).first()

                    if not assignment or not assignment.executive:
                        return Response(
                            {"error": "No executive assigned to this content"}, status=403)

  
                    if str(assignment.executive.user_id) != str(user.user_id):
                        return Response(
                            {"error": "You are not authorized to approve this content"},status=403)
                    if c.stakeholder_approval:
                        return Response({"message": "Already approved by executive"})

                    c.stakeholder_approval = True


                    triple = c.check_and_mark_all_approved()

                    if triple:
                        c.status= "approved"

                    c.save(update_fields=["stakeholder_approval" , "status"])

                    ContentHistory.objects.create(
                        content=c,
                        action_type="approved_stakeholder",
                        performed_by=user
                    )


                    return Response({
                        "message": "Executive approval recorded",
                        "all_approved": triple
                    })

                # ADMIN APPROVAL
                elif group in self.ADMIN_GROUPS:
                    # if not c.internal_approval:
                    #     return Response(
                    #         {"error": "Internal approval required first"},
                    #         status=400
                    #     )

                    if c.marketing_approval:
                        return Response({"message": "Already approved by admin"})

                    c.marketing_approval = True

                    triple = c.check_and_mark_all_approved()

                    if triple:
                        c.status= "approved"

                    c.save(update_fields=["marketing_approval" , "status"])

                    ContentHistory.objects.create(
                        content=c,
                        action_type="approved_marketing",
                        performed_by=user
                    )

                    

                    return Response({
                        "message": "Admin approval recorded",
                        "all_approved": triple
                    })

                return Response({"error": "No permission"}, status=403)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
        



    
@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="RejectRequest",
        fields={
            "reason": drf_serializers.CharField(required=True)
        }
    )
)
class RejectContentView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["approve" , "admin"]

    def post(self, request, content_id):
        reason = request.data.get("reason", "").strip()
        user = request.user

        if not reason:
            return Response({"error": "Reason is required"}, status=400)

        try:
            with transaction.atomic():
                c = Content.objects.select_for_update().get(content_id=content_id)

                if c.status not in ("draft", "in_review", "approved"):
                    return Response(
                        {"error": f"Cannot reject in '{c.status}' state"},
                        status=400
                    )

                c.status = "rejected"
                c.locked_permanently = True
                c.locked_by = user
                c.locked_at = None

                c.internal_approval = False
                c.marketing_approval = False
                c.stakeholder_approval = False
                c.all_approved_at = None

                c.save(update_fields=[
                    "status", "locked_permanently", "locked_by", "locked_at",
                    "internal_approval", "marketing_approval",
                    "stakeholder_approval", "all_approved_at"
                ])

                ContentHistory.objects.create(
                    content=c,
                    action_type="rejected",
                    performed_by=user,
                    note=reason
                )

                cache.delete(f"content_detail_{content_id}")

                return Response({
                    "message": "Content rejected and locked",
                    "status": c.status
                })

        except Content.DoesNotExist:
            return Response({"error": "Content not found"}, status=404)




@extend_schema(tags=["Content"])
class PublishContentView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["admin"]

    def post(self, request, content_id):
        user = request.user

        try:
            with transaction.atomic():
                c = Content.objects.select_for_update().get(content_id=content_id)

                if not (c.internal_approval and c.marketing_approval and c.stakeholder_approval):
                    return Response(
                        {"error": "All approvals required before publishing"},
                        status=400
                    )

                if c.status == "published":
                    return Response({"message": "Already published"})

                if c.status != "approved":
                    return Response(
                        {"error": f"Content must be 'approved'. Current: {c.status}"},
                        status=400
                    )

                c.status = "published"
                c.save(update_fields=["status"])

                ContentHistory.objects.create(
                    content=c,
                    action_type="published",
                    performed_by=user
                )

                cache.delete(f"content_detail_{content_id}")
                cache.delete("published_contents_list")

                return Response({
                    "message": "Content published successfully",
                    "status": c.status
                })

        except Content.DoesNotExist:
            return Response({"error": "Content not found"}, status=404)




# ─────────────────────────────────────────────────────────────────────────────
# 9–11. VERSION HISTORY
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ContentVersionHistory(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read" , "admin"]   #not sure for this, who all needs to see the version

    def get(self, request, content_id):
        try:
            c       = Content.objects.get(content_id=content_id)
            user    = request.user
            is_sme  = (user.role == "sme" and
                       ContentAssignment.objects.filter(content=c, sme=user).exists())
            if not (c.author == user or user.role in ["reviewer", "admin", "exec_approver"] or is_sme):
                return Response({"error": "Permission denied."}, status=403)
            versions = ContentVersion.objects.filter(content=c).select_related("changed_by")
            data = [{
                "version_id":   str(v.version_id),
                "changed_by":   v.changed_by.full_name if v.changed_by else "Unknown",
                "role":         v.changed_by.role if v.changed_by else "N/A",
                "timestamp":    v.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "title":        v.title,
                "image_url":    v.image_url,
                "body_preview": v.body[:100] + "...",
            } for v in versions]
            return Response({
                "content_id": str(c.content_id),
                "title":      c.title,
                "status":     c.status,
                "history":    data,
            })
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)


@extend_schema(tags=["Content"])
class ContentVersionDetailView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "admin"]

    def get(self, request, content_id, version_id):
        try:
            c = Content.objects.get(content_id=content_id)
            v = ContentVersion.objects.get(version_id=version_id, content=c)
            return Response({
                "version_id": str(v.version_id),
                "content_id": str(c.content_id),
                "title":      v.title,
                "body":       v.body,
                "image_url":  v.image_url,
                "changed_by": v.changed_by.full_name if v.changed_by else "Unknown",
                "saved_at":   v.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except ContentVersion.DoesNotExist:
            return Response({"error": "Version not found."}, status=404)


@extend_schema(tags=["Content"])
class LatestVersionView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "admin"]

    def get(self, request, content_id):
        try:
            c = Content.objects.get(content_id=content_id)
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        v = ContentVersion.objects.filter(content=c).order_by("-created_at").first()
        if not v:
            return Response({"error": "No versions found."}, status=404)
        return Response({
            "version_id": str(v.version_id),
            "content_id": str(c.content_id),
            "title":      v.title,
            "body":       v.body,
            "image_url":  v.image_url,
            "changed_by": v.changed_by.full_name if v.changed_by else "Unknown",
            "saved_at":   v.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })


# ─────────────────────────────────────────────────────────────────────────────
# 12. COMMENT (reverts to draft)
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Content"],
    request=inline_serializer(
        name="WriteCommentRequest",
        fields={
            "comment_text": drf_serializers.CharField(),
            "reply_to": drf_serializers.UUIDField(
                required=False, allow_null=True,
                help_text="comment_id of the comment being replied to (optional)",
            ),
        }
    )
)
class WriteComment(APIView):
    """
    POST /api/content/contents/<content_id>/comment/

    Adding a comment while content is 'in_review' OR 'approved' (within 24h window)
    reverts it to 'draft' and resets all approval flags so the whole flow restarts.
    After 24h from the 'approved' timestamp, content is permanently locked —
    comments are blocked and only an admin can publish it.
    Rejected/published content cannot be commented on.

    Optional field `reply_to` accepts a comment_id to thread the reply.
    """
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "admin"]

    def post(self, request, content_id):
        text = request.data.get("comment_text", "").strip()
        reply_to = request.data.get("reply_to", None)
        selected_text = request.data.get("selected_text", None)
        if not text:
            return Response({"error": "comment_text is required."}, status=400)
        try:
            with transaction.atomic():
                c = Content.objects.select_for_update().get(content_id=content_id)

                if c.status in ("rejected", "published"):
                    return Response(
                        {"error": f"Cannot comment on '{c.status}' content."},
                        status=400,
                    )

                # Enforce 24-hour post-approval lock
                # fully_approved = (
                #     c.internal_approval
                #     and c.marketing_approval
                #     and c.stakeholder_approval
                #     and c.all_approved_at is not None
                # )
                # if fully_approved:
                #     from django.utils import timezone
                #     elapsed = timezone.now() - c.all_approved_at
                #     if elapsed.total_seconds() >= 86400:
                #         return Response(
                #             {"error": "Content is locked: the 24-hour edit window after full approval has expired."},
                #             status=423,
                #         )

                if is_content_locked(c):
                    return Response(get_content_lock_error(), status=423)


                # Validate reply_to if provided
                parent_comment = None
                if reply_to:
                    try:
                        parent_comment = ContentComment.objects.get(comment_id=reply_to, content=c)
                    except ContentComment.DoesNotExist:
                        return Response({"error": "reply_to comment not found on this content."}, status=404)

                latest  = ContentVersion.objects.filter(content=c).order_by("-created_at").first()
                comment = ContentComment.objects.create(
                    content=c, user=request.user, comment_text=text,
                    version=latest, reply_to=parent_comment, selected_text=selected_text,
                )
                cache.delete(f"content_comments_{content_id}")

                ContentHistory.objects.create(
                    content=c, action_type="comment_added",
                    performed_by=request.user, note=text,
                )

                handle_mentions_and_notifications(text, c, comment, sender=request.user)
                return Response({
                    "message":    "Comment recorded. Content reverted to draft.",
                    "new_status": c.status,
                    "comment_id": str(comment.comment_id),
                    "reply_to":   str(parent_comment.comment_id) if parent_comment else None,
                })
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)
        except ValueError as e:
            return Response({"error": str(e)}, status=423)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# RESOLVE COMMENT
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ResolveComment(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["updare", "admin"]

    def patch(self, request, comment_id):
        try:
            with transaction.atomic():
                comment = ContentComment.objects.select_for_update().get(comment_id=comment_id)
                if comment.resolved:
                    return Response({"message": "Comment already resolved."})
                comment.resolved = True
                comment.save(update_fields=["resolved"])
                cache.delete(f"content_comments_{comment.content.content_id}")
                return Response({
                    "message":    "Comment resolved.",
                    "comment_id": str(comment.comment_id),
                    "resolved":   comment.resolved,
                })
        except ContentComment.DoesNotExist:
            return Response({"error": "Comment not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# 13. COMMENT HISTORY
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class ContentCommentHistoryView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "admin"]

    def get(self, request, content_id):
        cache_key   = f"content_comments_{content_id}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        try:
            c = Content.objects.get(content_id=content_id)
            version_subquery = ContentVersion.objects.filter(
                content=c, created_at__lte=OuterRef("created_at")
            ).order_by("-created_at").values("version_id")[:1]
            comments = (
                ContentComment.objects
                .filter(content=c)
                .select_related("user")
                .annotate(detected_version_id=Subquery(version_subquery))
                .order_by("created_at")
            )
            data = [{
                "comment_id":      str(cm.comment_id),
                "user": cm.user.full_name,
                "role":   cm.user.role,
                "group": cm.user.group,
                "text": cm.comment_text,
                "resolved": cm.resolved,
                "selected_text": cm.selected_text if cm.selected_text else None,
                "reply_to": str(cm.reply_to_id) if cm.reply_to_id else None,
                "timestamp":cm.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "version_at_time": str(cm.detected_version_id) if cm.detected_version_id else "Initial Draft",
            } for cm in comments]
            response_data = {"content_title": c.title, "comments": data}
            cache.set(cache_key, response_data, timeout=600)
            return Response(response_data)
        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)


# ─────────────────────────────────────────────────────────────────────────────
# 14. COMMENT EDIT / DELETE
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Content"])
class CommentEditDelete(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "admin"]

    def patch(self, request, comment_id):
        try:
            comment  = ContentComment.objects.get(comment_id=comment_id)
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
            comment    = ContentComment.objects.get(comment_id=comment_id)
            if comment.user != request.user:
                return Response({"error": "You can only delete your own comments."}, status=403)
            content_id = comment.content.content_id
            comment.delete()
            cache.delete(f"content_comments_{content_id}")
            return Response({"message": "Comment removed."})
        except ContentComment.DoesNotExist:
            return Response({"error": "Comment not found."}, status=404)


# ─────────────────────────────────────────────────────────────────────────────
# 15. CONTENT STATS — all 5 stages + counts
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Content – Analytics"],
    description=(
        "Returns count of content pieces per stage:\n"
        "  • **draft**     — in draft\n"
        "  • **in_review** — currently under review (awaiting any approval)\n"
        "  • **approved**  — all 3 approvals collected, pending publish or 24h lock\n"
        "  • **rejected**  — rejected and locked\n"
        "  • **published** — published\n"
        "  • **total**     — all content\n\n"
        "Optional `campaign_id` and `author_id` query params to narrow scope."
    ),
    parameters=[
        OpenApiParameter("campaign_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("author_id",   OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
    ],
)
class ContentStatsView(APIView):
    """
    GET /api/content/contents/stats/

    Response:
    {
        "draft":     12,
        "in_review": 5,
        "approved":  3,
        "rejected":  2,
        "published": 34,
        "total":     56
    }
    """
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "admin"]

    def get(self, request):
        qs = Content.objects.all()

        campaign_id = request.query_params.get("campaign_id", "").strip()
        author_id   = request.query_params.get("author_id", "").strip()
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)
        if author_id:
            qs = qs.filter(author__user_id=author_id)

        counts = qs.aggregate(
            draft     = Count("content_id", filter=Q(status="draft")),
            in_review = Count("content_id", filter=Q(status="in_review")),
            approved  = Count("content_id", filter=Q(status="approved")),
            rejected  = Count("content_id", filter=Q(status="rejected")),
            published = Count("content_id", filter=Q(status="published")),
            total     = Count("content_id"),
        )
        return Response(counts)


# ─────────────────────────────────────────────────────────────────────────────
# 16. CONTENT FILTER / ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(
    tags=["Content – Analytics"],
    parameters=[
        OpenApiParameter("content_type", OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("status", OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False,
                         description="draft | in_review | approved | rejected | published"),
        OpenApiParameter("author_id",OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("campaign_id", OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("tags", OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("year", OpenApiTypes.INT,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("month", OpenApiTypes.INT,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("quarter",OpenApiTypes.INT,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("group_by",OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False,
                         description="Pass 'period' for per-period breakdown"),
    ],
)
class ContentFilterView(APIView):
    permission_classes = [HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "admin"]

    QUARTER_MONTHS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}

    def get(self, request):
        qs = Content.objects.select_related("author").order_by("-created_at")

        content_type = request.query_params.get("content_type", "").strip()
        status = request.query_params.get("status", "").strip()
        author_id = request.query_params.get("author_id", "").strip()
        campaign_id  = request.query_params.get("campaign_id", "").strip()
        tags_raw = request.query_params.get("tags", "").strip()

        if content_type:
            qs = qs.filter(content_type__iexact=content_type)
        if status:
            qs = qs.filter(status=status)
        if author_id:
            qs = qs.filter(author__user_id=author_id)
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)
        if tags_raw:
            for tag in [t.strip() for t in tags_raw.split(",") if t.strip()]:
                qs = qs.filter(
                    Q(tags__iexact=tag) |
                    Q(tags__istartswith=tag + ",") |
                    Q(tags__iendswith="," + tag) |
                    Q(tags__icontains="," + tag + ",")
                )

        year_raw    = request.query_params.get("year")
        month_raw   = request.query_params.get("month")
        quarter_raw = request.query_params.get("quarter")
        year    = int(year_raw)    if year_raw    and year_raw.isdigit()    else None
        month   = int(month_raw)   if month_raw   and month_raw.isdigit()   else None
        quarter = int(quarter_raw) if quarter_raw and quarter_raw.isdigit() else None

        if year:
            qs = qs.filter(created_at__year=year)
            if month and 1 <= month <= 12:
                qs = qs.filter(created_at__month=month)
            elif quarter and quarter in self.QUARTER_MONTHS:
                m_start, m_end = self.QUARTER_MONTHS[quarter]
                qs = qs.filter(created_at__month__gte=m_start, created_at__month__lte=m_end)

        total    = qs.count()
        items    = ContentSerializer(qs, many=True).data
        response = {"total": total, "items": items}

        if request.query_params.get("group_by", "").strip() == "period":
            response["by_period"] = self._period_breakdown(qs, year, quarter)

        return Response(response)

    @staticmethod
    def _period_breakdown(qs, year, quarter):
        from django.db.models.functions import TruncMonth, TruncYear
        if not year:
            rows = (qs.annotate(period=TruncYear("created_at"))
                      .values("period")
                      .annotate(count=Count("content_id"))
                      .order_by("period"))
            return [{"period": r["period"].strftime("%Y"), "count": r["count"]} for r in rows]
        else:
            rows = (qs.annotate(period=TruncMonth("created_at"))
                      .values("period")
                      .annotate(count=Count("content_id"))
                      .order_by("period"))
            return [{"period": r["period"].strftime("%Y-%m"), "count": r["count"]} for r in rows]



class ContentAssignmentDetailView(APIView):
    """
    GET all SME + Executive assignments for a particular content
    """
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read" , "admin"]

    def get(self, request, content_id):
        try:
            content = Content.objects.get(content_id=content_id)

            assignments = ContentAssignment.objects.filter(
                content=content
            ).select_related("sme", "executive", "assigned_by")

            data = []
            for a in assignments:
                data.append({
                    "assignment_id": str(a.assignment_id),

                    "sme": {
                        "user_id": str(a.sme.user_id) if a.sme else None,
                        "full_name": a.sme.full_name if a.sme else None,
                        "email": a.sme.email if a.sme else None,
                    },

                    "executive": {
                        "user_id": str(a.executive.user_id),
                        "full_name": a.executive.full_name,
                        "email": a.executive.email,
                    },

                    "assigned_by": {
                        "user_id": str(a.assigned_by.user_id) if a.assigned_by else None,
                        "full_name": a.assigned_by.full_name if a.assigned_by else None,
                    },

                    "assigned_at": a.assigned_at,
                })

            return Response({
                "content_id": str(content.content_id),
                "title": content.title,
                "assignments": data,
            })

        except Content.DoesNotExist:
            return Response({"error": "Content not found."}, status=404)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

