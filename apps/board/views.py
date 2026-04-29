import json
from datetime import datetime
from django.core.cache import cache
from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from accounts.models import User
from utils.permissions.base import HasRBACPermission
from utils.notifications.services import send_task_assignment_email, send_task_transfer_email
from .models import Campaign, Event, Task, TaskHistory, Discussion
from .serializers import (
    CampaignSerializer, EventSerializer,
    TaskSerializer, TaskListSerializer, DiscussionSerializer,
)
from drf_spectacular.utils import (extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer, OpenApiResponse,extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample,
    OpenApiResponse
    )
from rest_framework import serializers as drf_serializers
from django.core.serializers.json import DjangoJSONEncoder
# from rest_framework.generics import RetrieveUpdateDestroyAPIView

TASK_LIST_CACHE_KEY = "kanban_all_tasks"
CACHE_TTL = 60 * 5


def _bust_task_cache():
    cache.delete(TASK_LIST_CACHE_KEY)


# ==============================================================================
# CAMPAIGN VIEWS
# ==============================================================================

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from rest_framework import status

@extend_schema(
    tags=["Campaign"],
    summary="List and create campaigns",
    description="GET: Retrieve all campaigns. POST: Create a new campaign.",
    responses={
        200: CampaignSerializer(many=True),
        201: CampaignSerializer,
        400: OpenApiResponse(description="Bad request"),
        401: OpenApiResponse(description="Unauthorized"),
        403: OpenApiResponse(description="Forbidden"),
    },
)
class CampaignListView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    @extend_schema(
        summary="Get all campaigns",
        description="Returns a list of all campaigns.",
        responses={200: CampaignSerializer(many=True)},
    )
    def get(self, request):
        campaigns = Campaign.objects.select_related("created_by").all()
        serializer = CampaignSerializer(campaigns, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Create a campaign",
        description="Creates a new campaign with title, optional description, and date range.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "example": "Summer Campaign"},
                    "description": {"type": "string", "example": "Campaign for summer promotions"},
                    "start_date": {"type": "string", "format": "date", "example": "2026-05-01"},
                    "end_date": {"type": "string", "format": "date", "example": "2026-06-01"},
                    "max_hierarchy_level": {"type": "integer", "example": 2},
                },
                "required": ["title"],
            }
        },
        responses={
            201: CampaignSerializer,
            400: OpenApiResponse(description="Validation error"),
        },
        examples=[
            OpenApiExample(
                "Create Campaign Example",
                value={
                    "title": "Summer Campaign",
                    "description": "Campaign for summer promotions",
                    "start_date": "2026-05-01",
                    "end_date": "2026-06-01",
                    "max_hierarchy_level": 2,
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        title = request.data.get("title", "").strip()
        description = request.data.get("description", "").strip()
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        max_hierarchy_level = int(request.data.get("max_hierarchy_level", 2))

        if not title:
            return Response({"error": "title is required."}, status=400)
        if not description:
            return Response({"error": "description is required."}, status=400)
        if max_hierarchy_level < 1:
            return Response({"error": "max_hierarchy_level must be at least 1."}, status=400)

        campaign = Campaign.objects.create(
            title=title,
            description=description,
            start_date=start_date or None,
            end_date=end_date or None,
            created_by=request.user,
            max_hierarchy_level=max_hierarchy_level,
        )
        return Response(CampaignSerializer(campaign).data, status=201)



@extend_schema(tags=["Campaign"])
@extend_schema_view(
    get=extend_schema(
        summary="Get campaign details",
        parameters=[
            OpenApiParameter(
                name="campaign_id",
                type=str,
                location=OpenApiParameter.PATH,
                description="Unique campaign ID"
            )
        ],
        responses={
            200: CampaignSerializer,
            404: OpenApiResponse(
                response={"type": "object", "properties": {
                    "error": {"type": "string"}
                }},
                description="Campaign not found",
                examples=[
                    OpenApiExample(
                        "Not Found",
                        value={"error": "Campaign not found."}
                    )
                ]
            )
        }
    ),

    patch=extend_schema(
        summary="Update campaign (partial)",
        parameters=[
            OpenApiParameter(
                name="campaign_id",
                type=str,
                location=OpenApiParameter.PATH,
                description="Unique campaign ID"
            )
        ],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "start_date": {"type": "string", "format": "date"},
                    "end_date": {"type": "string", "format": "date"},
                    "max_hierarchy_level": {"type": "integer"}
                },
                "example": {
                    "title": "Updated Campaign",
                    "description": "New description",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "max_hierarchy_level": 3
                }
            }
        },
        responses={
            200: CampaignSerializer,
            403: OpenApiResponse(
                response={"type": "object", "properties": {
                    "error": {"type": "string"}
                }},
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={"error": "Only creator or admin can edit."}
                    )
                ]
            ),
            404: OpenApiResponse(
                response={"type": "object", "properties": {
                    "error": {"type": "string"}
                }},
                examples=[
                    OpenApiExample(
                        "Not Found",
                        value={"error": "Campaign not found."}
                    )
                ]
            )
        }
    ),

    delete=extend_schema(
        summary="Delete campaign",
        parameters=[
            OpenApiParameter(
                name="campaign_id",
                type=str,
                location=OpenApiParameter.PATH,
                description="Unique campaign ID"
            )
        ],
        responses={
            200: OpenApiResponse(
                response={"type": "object", "properties": {
                    "message": {"type": "string"}
                }},
                examples=[
                    OpenApiExample(
                        "Success",
                        value={"message": "Campaign deleted."}
                    )
                ]
            ),
            403: OpenApiResponse(
                response={"type": "object", "properties": {
                    "error": {"type": "string"}
                }},
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={"error": "Only creator or admin can delete."}
                    )
                ]
            ),
            404: OpenApiResponse(
                response={"type": "object", "properties": {
                    "error": {"type": "string"}
                }},
                examples=[
                    OpenApiExample(
                        "Not Found",
                        value={"error": "Campaign not found."}
                    )
                ]
            )
        }
    )
)
class CampaignDetailView(APIView):
    """GET / PATCH / DELETE a single campaign."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = [ "write", "update", "admin"]

    def _get(self, campaign_id):
        try:
            return Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return None

    def get(self, request, campaign_id):
        try:
            c = self._get(campaign_id)
            if not c:
                return Response({"error": "Campaign not found."}, status=404)
            return Response(CampaignSerializer(c).data)
        except Exception as e:
            return Response({"error: " , str(e)})

    def patch(self, request, campaign_id):
     try: 
        print("hii")
        c = self._get(campaign_id)
        if not c:
            return Response({"error": "Campaign not found."}, status=404)
        if request.user.role != "admin" and c.created_by != request.user:
            return Response({"error": "Only creator or admin can edit."}, status=403)

        for field in ["title", "description", "start_date", "end_date", "max_hierarchy_level"]:
            if field in request.data:
                setattr(c, field, request.data[field])
        c.save()
        return Response(CampaignSerializer(c).data)
     except Exception as e:
           return Response({"error": str(e)})

    def delete(self, request, campaign_id):
       try: 
        c = self._get(campaign_id)
        if not c:
            return Response({"error": "Campaign not found."}, status=404)
        if request.user.role != "admin" and c.created_by != request.user:
            return Response({"error": "Only creator or admin can delete."}, status=403)
        c.delete()
        _bust_task_cache()
        return Response({"message": "Campaign deleted."})
       except Exception as e:
           return Response({"error": str(e)})


@extend_schema(tags=["Campaign"])
class CampaignEventsView(APIView):
    """GET all events under a campaign."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)
        events = Event.objects.filter(campaign=campaign).select_related("created_by")
        serializer = EventSerializer(events, many=True)
        return Response({"campaign": campaign.title, "events": serializer.data})


@extend_schema(tags=["Campaign"])
class CampaignTasksView(APIView):
    """GET all root tasks (no parent_task) directly under a campaign."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)

        tasks = Task.objects.filter(
            campaign=campaign, parent_task__isnull=True
        ).select_related("assigned_by", "assigned_to", "event")
        serializer = TaskListSerializer(tasks, many=True)
        return Response({"campaign": campaign.title, "tasks": serializer.data})


# ==============================================================================
# EVENT VIEWS
# ==============================================================================

@extend_schema(tags=["Event"])
class EventListView(APIView):
    """GET all events / POST create event."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "board"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
        events = Event.objects.select_related("campaign", "created_by").all()
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data)

    def post(self, request):
        title= request.data.get("title", "").strip()
        description = request.data.get("description", "").strip()
        campaign_id = request.data.get("campaign_id")
        start_date  = request.data.get("start_date")
        end_date = request.data.get("end_date")

        if not title:
            return Response({"error": "title is required."}, status=400)
        if not campaign_id:
            return Response({"error": "campaign_id is required. Events must belong to a campaign."}, status=400)

        try:
            campaign = Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)

        event = Event.objects.create(
            campaign= campaign,
            title = title,
            description = description,
            start_date = start_date or None,
            end_date= end_date   or None,
            created_by = request.user,
        )
        return Response(EventSerializer(event).data, status=201)




@extend_schema(
    tags=["Event"],
)
class EventDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def _get(self, event_id):
        try:
            return Event.objects.select_related("campaign", "created_by").get(event_id=event_id)
        except Event.DoesNotExist:
            return None

    @extend_schema(
        summary="Get event details",
        description="Retrieve a single event by ID",
        responses={
            200: EventSerializer,
            404: OpenApiResponse(description="Event not found"),
        },
    )
    def get(self, request, event_id):
        e = self._get(event_id)
        if not e:
            return Response({"error": "Event not found."}, status=404)
        return Response(EventSerializer(e).data)

    @extend_schema(
        summary="Update event",
        description="Update event fields (only creator or admin allowed)",
        request=EventSerializer,
        responses={
            200: EventSerializer,
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Event not found"),
        },
        examples=[
            OpenApiExample(
                "Update Event Example",
                value={
                    "title": "Updated Event",
                    "description": "New description",
                    "start_date": "2026-04-20",
                    "end_date": "2026-04-25"
                },
                request_only=True,
            )
        ]
    )
    def patch(self, request, event_id):
        e = self._get(event_id)
        if not e:
            return Response({"error": "Event not found."}, status=404)
        if request.user.role != "admin" and e.created_by != request.user:
            return Response({"error": "Only creator or admin can edit."}, status=403)

        for field in ["title", "description", "start_date", "end_date"]:
            if field in request.data:
                setattr(e, field, request.data[field])
        e.save()

        return Response(EventSerializer(e).data)

    @extend_schema(
        summary="Delete event",
        description="Delete an event (only creator or admin allowed)",
        responses={
            200: OpenApiResponse(description="Event deleted"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Event not found"),
        },
    )
    def delete(self, request, event_id):
        e = self._get(event_id)
        if not e:
            return Response({"error": "Event not found."}, status=404)
        if request.user.role != "admin" and e.created_by != request.user:
            return Response({"error": "Only creator or admin can delete."}, status=403)

        e.delete()
        _bust_task_cache()
        return Response({"message": "Event deleted."})



# class EventDetailView(APIView):
#     """GET / PATCH / DELETE a single event."""
#     permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
#     required_area  = "content"
#     required_roles = ["read", "write", "update", "admin"]

#     def _get(self, event_id):
#         try:
#             return Event.objects.select_related("campaign", "created_by").get(event_id=event_id)
#         except Event.DoesNotExist:
#             return None

#     def get(self, request, event_id):
#         e = self._get(event_id)
#         if not e:
#             return Response({"error": "Event not found."}, status=404)
#         return Response(EventSerializer(e).data)

#     def patch(self, request, event_id):
#         e = self._get(event_id)
#         if not e:
#             return Response({"error": "Event not found."}, status=404)
#         if request.user.role != "admin" and e.created_by != request.user:
#             return Response({"error": "Only creator or admin can edit."}, status=403)
#         for field in ["title", "description", "start_date", "end_date"]:
#             if field in request.data:
#                 setattr(e, field, request.data[field])
#         e.save()
#         return Response(EventSerializer(e).data)

#     def delete(self, request, event_id):
#         e = self._get(event_id)
#         if not e:
#             return Response({"error": "Event not found."}, status=404)
#         if request.user.role != "admin" and e.created_by != request.user:
#             return Response({"error": "Only creator or admin can delete."}, status=403)
#         e.delete()
#         _bust_task_cache()
#         return Response({"message": "Event deleted."})


@extend_schema(tags=["Event"])
class EventTasksView(APIView):
    """GET all tasks under a specific event."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, event_id):
        try:
            event = Event.objects.select_related("campaign").get(event_id=event_id)
        except Event.DoesNotExist:
            return Response({"error": "Event not found."}, status=404)

        tasks = Task.objects.filter(
            event=event, parent_task__isnull=True
        ).select_related("assigned_by", "assigned_to")
        serializer = TaskListSerializer(tasks, many=True)
        return Response({
            "event": event.title,
            "campaign": event.campaign.title,
            "tasks": serializer.data,
        })


# ==============================================================================
# TASK VIEWS
# ==============================================================================

@extend_schema(
    tags=["Board"],
    request=inline_serializer(
        name="CreateTaskRequest",
        fields={
            "title": drf_serializers.CharField(),
            "description": drf_serializers.CharField(required=False),
            "campaign_id": drf_serializers.UUIDField(help_text="Required. UUID of the campaign."),
            "event_id": drf_serializers.UUIDField(required=False, help_text="Optional. UUID of the event."),
            "parent_task_id": drf_serializers.UUIDField(required=False, help_text="Optional. UUID of parent task for subtask creation."),
            "assigned_to":drf_serializers.UUIDField(help_text="UUID of user to assign task to"),
            "tags": drf_serializers.CharField(required=False),
            "priority": drf_serializers.ChoiceField(choices=["low","medium","high"], required=False),
            "marketing_type": drf_serializers.CharField(required=False),
            "due_date": drf_serializers.DateField(required=False),
        }
    )
)
class TaskListView(APIView):
    """GET all tasks (cached) / POST create task."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
      try:
        cached = cache.get(TASK_LIST_CACHE_KEY)
        if cached:
            return Response(json.loads(cached))
        tasks = Task.objects.select_related(
            "assigned_by", "assigned_to", "last_transferred_by", "campaign", "event", "parent_task"
        ).all()
        serializer = TaskListSerializer(tasks, many=True)
        data = serializer.data
        cache.set(TASK_LIST_CACHE_KEY, json.dumps(data, cls=DjangoJSONEncoder), CACHE_TTL)
        return Response(data)
      except Exception as e:
          return Response({"error": str(e)} , status=500)

    def post(self, request):
        title = request.data.get("title", "").strip()
        description = request.data.get("description", "").strip()
        campaign_id= request.data.get("campaign_id")
        event_id = request.data.get("event_id")
        parent_task_id = request.data.get("parent_task_id")
        assigned_to_id = request.data.get("assigned_to")
        tags= request.data.get("tags", "").strip()
        priority= request.data.get("priority", "medium").strip()
        marketing_type = request.data.get("marketing_type", "").strip()
        due_date = request.data.get("due_date")

        if not title:
            return Response({"error": "title is required."}, status=400)
        if not campaign_id:
            return Response({"error": "campaign_id is required. Every task must belong to a campaign."}, status=400)
        if not assigned_to_id:
            return Response({"error": "assigned_to (user UUID) is required."}, status=400)

        try:
            campaign = Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)

        event = None
        if event_id:
            try:
                event = Event.objects.get(event_id=event_id, campaign=campaign)
            except Event.DoesNotExist:
                return Response({"error": "Event not found or does not belong to this campaign."}, status=404)

        parent_task = None
        if parent_task_id:
            try:
                parent_task = Task.objects.get(task_id=parent_task_id, campaign=campaign)
            except Task.DoesNotExist:
                return Response({"error": "Parent task not found or does not belong to this campaign."}, status=404)

        try:
            assignee = User.objects.get(user_id=assigned_to_id)
        except User.DoesNotExist:
            return Response({"error": "Assigned user not found."}, status=404)

        try:
            with transaction.atomic():
                task = Task(
                    title  = title,
                    description = description,
                    campaign = campaign,
                    event= event,
                    parent_task = parent_task,
                    tags = tags,
                    priority = priority,
                    marketing_type = marketing_type,
                    due_date = due_date or None,
                    assigned_by = request.user,
                    assigned_to = assignee,
                    status = "to_do",
                )
                task.full_clean()  # runs clean() for hierarchy validation
                task.save()

                TaskHistory.objects.create(
                    task = task,
                    action  = "created",
                    performed_by = request.user,
                    detail = f"Task created and assigned to {assignee.full_name} ({assignee.email})",
                )
        except ValidationError as e:
            return Response({"error": str(e)}, status=400)

        _bust_task_cache()
        send_task_assignment_email(
            assignee_email = assignee.email,
            assignee_name = assignee.full_name,
            task_title = task.title,
            assigned_by_name = request.user.full_name,
        )
        return Response(TaskSerializer(task).data, status=201)


@extend_schema(tags=["Board"])
class TaskDetailView(APIView):
    """GET full task detail / DELETE task."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    #for queery optimisation
    def _get_task(self, task_id):
        try:
            return Task.objects.select_related(
                "assigned_by", "assigned_to", "last_transferred_by",
                "campaign", "event", "parent_task",
            ).prefetch_related("discussion__author", "history__performed_by").get(task_id=task_id)
        except Task.DoesNotExist:
            return None

    def get(self, request, task_id):
        task = self._get_task(task_id)
        if not task:
            return Response({"error": "Task not found."}, status=404)
        return Response(TaskSerializer(task).data)

    def delete(self, request, task_id):
        task = self._get_task(task_id)
        if not task:
            return Response({"error": "Task not found."}, status=404)
        if request.user.role != "admin" and task.assigned_by != request.user:
            return Response({"error": "Only the original creator or admin can delete."}, status=403)
        task.delete()
        _bust_task_cache()
        return Response({"message": "Task deleted."})


@extend_schema(tags=["Board"])
class TaskSubtasksView(APIView):
    """GET all subtasks of a task."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, task_id):
        try:
            task = Task.objects.select_related("campaign").get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        subtasks   = Task.objects.filter(parent_task=task).select_related("assigned_by", "assigned_to")
        serializer = TaskListSerializer(subtasks, many=True)
        return Response({
            "parent_task": task.title,
            "depth": task.get_depth(),
            "max_allowed_depth": task.campaign.max_hierarchy_level,
            "subtasks":    serializer.data,
        })


@extend_schema(tags=["Board"])
class TaskUpdateView(APIView):
    """PATCH task metadata."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "update", "admin"]

    def patch(self, request, task_id):
        try:
            task = Task.objects.select_related("assigned_by", "last_transferred_by").get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        user = request.user
        can_edit = (
            user.role == "admin" or
            task.assigned_by == user or
            task.last_transferred_by == user
        )
        if not can_edit:
            return Response({"error": "Only the task creator, last transferrer, or admin can edit."}, status=403)

        editable = ["title", "description", "tags", "priority", "marketing_type", "due_date", "status"]
        changed  = []

        for field in editable:
            if field not in request.data:
                continue
            new_val = request.data[field]
            if field == "priority" and new_val not in [p[0] for p in Task.PRIORITY_CHOICES]:
                return Response({"error": f"Invalid priority."}, status=400)
            if field == "status" and new_val not in [s[0] for s in Task.STATUS_CHOICES]:
                return Response({"error": f"Invalid status."}, status=400)
            if field == "due_date" and new_val:
                try:
                    datetime.strptime(new_val, "%Y-%m-%d")
                except ValueError:
                    return Response({"error": "due_date must be YYYY-MM-DD."}, status=400)
            if field == "title" and not str(new_val).strip():
                return Response({"error": "Title cannot be empty."}, status=400)

            old_val = getattr(task, field)
            if str(old_val) != str(new_val):
                changed.append(f"{field}: '{old_val}' → '{new_val}'")
            setattr(task, field, new_val)

        if not changed:
            return Response({"message": "No changes.", "task": TaskSerializer(task).data})

        task.save()
        TaskHistory.objects.create(task=task, action="updated", performed_by=user, detail=" | ".join(changed))
        _bust_task_cache()
        return Response(TaskSerializer(task).data)


@extend_schema(tags=["Board"])
class TransferTaskView(APIView):
    """POST transfer task to another user."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "update", "admin"]

    def post(self, request, task_id):
        try:
            task = Task.objects.select_related("assigned_to", "assigned_by").get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        if request.user.role != "admin" and task.assigned_to != request.user:
            return Response({"error": "Only the current assignee can transfer."}, status=403)

        transfer_to_id = request.data.get("transfer_to")
        if not transfer_to_id:
            return Response({"error": "transfer_to (user UUID) is required."}, status=400)

        try:
            new_assignee = User.objects.get(user_id=transfer_to_id)
        except User.DoesNotExist:
            return Response({"error": "Target user not found."}, status=404)

        if new_assignee == task.assigned_to:
            return Response({"error": "Task is already assigned to this user."}, status=400)

        old_assignee = task.assigned_to
        with transaction.atomic():
            task.last_transferred_by = request.user
            task.assigned_to         = new_assignee
            task.save()
            TaskHistory.objects.create(
                task = task,
                action = "transferred",
                performed_by = request.user,
                detail = f"Transferred from {old_assignee.full_name} to {new_assignee.full_name}",
            )

        _bust_task_cache()
        send_task_transfer_email(
            new_assignee_email= new_assignee.email,
            new_assignee_name = new_assignee.full_name,
            task_title= task.title,
            transferred_by_name = request.user.full_name,
        )
        return Response({"message": f"Transferred to {new_assignee.full_name}.", "task": TaskSerializer(task).data})


@extend_schema(
    tags=["Board"],
    parameters=[
        OpenApiParameter("search", OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("status", OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, enum=["to_do","in_progress","completed","blocked"]),
        OpenApiParameter("priority", OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, enum=["low","medium","high"]),
        OpenApiParameter("campaign_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by campaign UUID"),
        OpenApiParameter("event_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by event UUID"),
        OpenApiParameter("assigned_to",OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by assigned user UUID"),
        OpenApiParameter("marketing_type", OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("tags",OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False),
        OpenApiParameter("due_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("due_before", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("due_after", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("root_only",OpenApiTypes.BOOL, OpenApiParameter.QUERY, required=False, description="If true, return only root tasks (no subtasks)"),
    ]
)
class TaskFilterSearchView(APIView):
    """Filterable task list with campaign/event/hierarchy filters."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
        qs = Task.objects.select_related(
            "assigned_by", "assigned_to", "last_transferred_by", "campaign", "event", "parent_task"
        )

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(title__icontains=search)

        status_param = request.query_params.get("status", "").strip()
        if status_param:
            if status_param not in [s[0] for s in Task.STATUS_CHOICES]:
                return Response({"error": "Invalid status."}, status=400)
            qs = qs.filter(status=status_param)

        priority_param = request.query_params.get("priority", "").strip()
        if priority_param:
            if priority_param not in [p[0] for p in Task.PRIORITY_CHOICES]:
                return Response({"error": "Invalid priority."}, status=400)
            qs = qs.filter(priority=priority_param)

        campaign_id = request.query_params.get("campaign_id", "").strip()
        if campaign_id:
            qs = qs.filter(campaign__campaign_id=campaign_id)

        event_id = request.query_params.get("event_id", "").strip()
        if event_id:
            qs = qs.filter(event__event_id=event_id)

        assigned_to = request.query_params.get("assigned_to", "").strip()
        if assigned_to:
            qs = qs.filter(assigned_to__user_id=assigned_to)

        mtype = request.query_params.get("marketing_type", "").strip()
        if mtype:
            qs = qs.filter(marketing_type__icontains=mtype)

        tag = request.query_params.get("tags", "").strip()
        if tag:
            qs = qs.filter(tags__icontains=tag)

        due_date = request.query_params.get("due_date", "").strip()
        if due_date:
            qs = qs.filter(due_date=due_date)

        due_before = request.query_params.get("due_before", "").strip()
        if due_before:
            qs = qs.filter(due_date__lte=due_before)

        due_after = request.query_params.get("due_after", "").strip()
        if due_after:
            qs = qs.filter(due_date__gte=due_after)

        root_only = request.query_params.get("root_only", "").lower()
        if root_only in ("true", "1", "yes"):
            qs = qs.filter(parent_task__isnull=True)

        serializer = TaskListSerializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data})



#2 apis below are not needed, filter thing wil do the work
@extend_schema(tags=["Board"])
class MyTasksView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
        tasks = Task.objects.filter(assigned_to=request.user).select_related(
            "assigned_by", "assigned_to", "campaign", "event"
        )
        return Response(TaskListSerializer(tasks, many=True).data)


@extend_schema(tags=["Board"])
class TasksByUserView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, user_id):
        try:
            target = User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)
        tasks = Task.objects.filter(assigned_to=target).select_related("assigned_by", "assigned_to", "campaign", "event")
        return Response({
            "user":  {"user_id": str(target.user_id), "full_name": target.full_name},
            "tasks": TaskListSerializer(tasks, many=True).data,
        })


# ==============================================================================
# DISCUSSION
# ==============================================================================

@extend_schema(tags=["Board"])
class DiscussionView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, task_id):
        try:
            task = Task.objects.get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)
        comments = Discussion.objects.filter(task=task).select_related("author")
        serializer = DiscussionSerializer(comments, many=True)
        return Response(serializer.data)

    def post(self, request, task_id):
        try:
            task = Task.objects.get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)
        message = request.data.get("message", "").strip()
        if not message:
            return Response({"error": "Message cannot be empty."}, status=400)
        comment = Discussion.objects.create(task=task, author=request.user, message=message)
        serializer= DiscussionSerializer(comment)
        return Response(serializer.data, status=201)


@extend_schema(tags=["Board"])
class DiscussionDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = "content"
    required_roles = ["write", "update", "admin"]

    def delete(self, request, task_id, comment_id):
        try:
            comment = Discussion.objects.get(discussion_id=comment_id, task_id=task_id)
        except Discussion.DoesNotExist:
            return Response({"error": "Comment not found."}, status=404)
        if request.user.role != "admin" and comment.author != request.user:
            return Response({"error": "You can only delete your own comments."}, status=403)
        comment.delete()
        return Response({"message": "Comment deleted."})
