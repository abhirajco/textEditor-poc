import json
from datetime import datetime
from django.core.cache import cache
from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from pydantic import ValidationError as PydanticValidationError

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from rest_framework import status
from accounts.models import User
from utils.permissions.base import HasRBACPermission
from utils.notifications.services import send_task_assignment_email, send_task_transfer_email
from .models import Campaign, Event, Task, TaskHistory, Discussion
from .serializers import (
    CampaignSerializer, EventSerializer,
    TaskSerializer, TaskListSerializer, DiscussionSerializer,
)
from .schemas import (
    CampaignCreateSchema, CampaignUpdateSchema,
    EventCreateSchema, EventUpdateSchema,
    TaskCreateSchema, TaskUpdateSchema, TaskTransferSchema,
    TaskFilterSchema, EventFilterSchema, DiscussionCreateSchema,
)
from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer,
    OpenApiResponse, extend_schema_view, OpenApiExample,
)
from rest_framework import serializers as drf_serializers
from django.core.serializers.json import DjangoJSONEncoder

TASK_LIST_CACHE_KEY = "kanban_all_tasks"
CACHE_TTL = 60 * 5


quarter_months = {
                1: [1,2,3],
                2: [4,5,6],
                3: [7,8,9],
                4: [10,11,12],
            }

def _bust_task_cache():
    cache.delete(TASK_LIST_CACHE_KEY)


def _pydantic_errors(exc: PydanticValidationError) -> Response:
    """Convert Pydantic validation errors into a clean 400 response."""
    errors = [
        {"field": " → ".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return Response({"errors": errors}, status=400)


# ==============================================================================
# CAMPAIGN VIEWS
# ==============================================================================


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
        description="Creates a new campaign.",
        responses={
            201: CampaignSerializer,
            400: OpenApiResponse(description="Validation error"),
        },
    )
    def post(self, request):
        try:
            payload = CampaignCreateSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        campaign = Campaign.objects.create(
            title=payload.title,
            description=payload.description,
            start_date=payload.start_date,
            end_date=payload.end_date,
            created_by=request.user,
            max_hierarchy_level=payload.max_hierarchy_level,
            campaign_type=payload.campaign_type,
            priority=payload.priority,
            status=payload.status,
            location=payload.location,
            tags=payload.tags,
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
                "title":               {"type": "string"},
                "description":         {"type": "string"},
                "start_date":          {"type": "string", "format": "date"},
                "end_date":            {"type": "string", "format": "date"},
                "campaign_type":       {"type": "string"},
                "priority":            {"type": "string", "enum": ["low", "medium", "high"]},
                "status":              {"type": "string", "enum": ["planning", "in_progress", "upcoming"]},
                "location":            {"type": "string"},
                "tags":                {"type": "string", "description": "Comma-separated tags e.g. design,ux,launch"},
                "max_hierarchy_level": {"type": "integer"},
                },
            "example": {
                "title":               "Updated Campaign",
                "description":         "New description",
                "start_date":          "2026-01-01",
                "end_date":            "2026-12-31",
                "campaign_type":       "digital",
                "priority":            "high",
                "status":              "in_progress",
                "location":            "Mumbai",
                "tags":                "design,ux,launch",
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
    required_area = "content"
    required_roles = ["write", "update", "admin"]

    def _get(self, campaign_id):
        try:
            return Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return None

    def get(self, request, campaign_id):
        c = self._get(campaign_id)
        if not c:
            return Response({"error": "Campaign not found."}, status=404)
        return Response(CampaignSerializer(c).data)

    def patch(self, request, campaign_id):
        c = self._get(campaign_id)
        if not c:
            return Response({"error": "Campaign not found."}, status=404)
        if request.user.role != "admin" and c.created_by != request.user:
            return Response({"error": "Only creator or admin can edit."}, status=403)

        try:
            payload = CampaignUpdateSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        # Only set fields that were actually sent in the request
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(c, field, value)
        c.save()
        return Response(CampaignSerializer(c).data)

    def delete(self, request, campaign_id):
        c = self._get(campaign_id)
        if not c:
            return Response({"error": "Campaign not found."}, status=404)
        if request.user.role != "admin" and c.created_by != request.user:
            return Response({"error": "Only creator or admin can delete."}, status=403)
        c.delete()
        _bust_task_cache()
        return Response({"message": "Campaign deleted."})


@extend_schema(tags=["Campaign"])
class CampaignEventsView(APIView):
    """GET all events under a campaign."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)
        events = Event.objects.filter(campaign=campaign).select_related("created_by")
        return Response({"campaign": campaign.title, "events": EventSerializer(events, many=True).data})


@extend_schema(tags=["Campaign"])
class CampaignTasksView(APIView):
    """GET all root tasks (no parent_task) directly under a campaign."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)
        tasks = Task.objects.filter(
            campaign=campaign, parent_task__isnull=True
        ).select_related("assigned_by", "assigned_to", "event")
        return Response({"campaign": campaign.title, "tasks": TaskListSerializer(tasks, many=True).data})


@extend_schema(
    tags=["Campaign"],
    parameters=[
        OpenApiParameter("search",    OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, description="Search by title"),
        OpenApiParameter("status",    OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, enum=["planning", "in_progress", "upcoming"]),
        OpenApiParameter("priority",    OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, enum=["low", "medium", "high"]),
        OpenApiParameter("campaign_type",   OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, description="Filter by campaign type"),
        OpenApiParameter("location",  OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, description="Filter by location"),
        OpenApiParameter("tags",    OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, description="Filter by tag (comma-separated, matches any)"),
        OpenApiParameter("created_by",OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by creator user UUID"),
        OpenApiParameter("start_after",  OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Campaigns starting on or after this date"),
        OpenApiParameter("start_before",  OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Campaigns starting on or before this date"),
        OpenApiParameter("end_after", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Campaigns ending on or after this date"),
        OpenApiParameter("end_before", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Campaigns ending on or before this date"),
        OpenApiParameter("max_hierarchy_level", OpenApiTypes.INT,  OpenApiParameter.QUERY, required=False, description="Filter by exact max hierarchy level"),
    ]
)
class CampaignFilterSearchView(APIView):
    """Filterable campaign list."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
        qs = Campaign.objects.select_related("created_by")

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(title__icontains=search)

        status_param = request.query_params.get("status", "").strip()
        if status_param:
            if status_param not in [s[0] for s in Campaign.STATUS_CHOICES]:
                return Response({"error": "Invalid status."}, status=400)
            qs = qs.filter(status=status_param)

        priority_param = request.query_params.get("priority", "").strip()
        if priority_param:
            if priority_param not in [p[0] for p in Campaign.PRIORITY_CHOICES]:
                return Response({"error": "Invalid priority."}, status=400)
            qs = qs.filter(priority=priority_param)

        campaign_type = request.query_params.get("campaign_type", "").strip()
        if campaign_type:
            qs = qs.filter(campaign_type__icontains=campaign_type)

        location = request.query_params.get("location", "").strip()
        if location:
            qs = qs.filter(location__icontains=location)

        tag = request.query_params.get("tags", "").strip()
        if tag:
            qs = qs.filter(tags__icontains=tag)

        created_by = request.query_params.get("created_by", "").strip()
        if created_by:
            qs = qs.filter(created_by__user_id=created_by)

        for param, lookup in [
            ("start_after", "start_date__gte"),
            ("start_before", "start_date__lte"),
            ("end_after", "end_date__gte"),
            ("end_before", "end_date__lte"),
        ]:
            val = request.query_params.get(param, "").strip()
            if val:
                qs = qs.filter(**{lookup: val})

        max_hierarchy_level = request.query_params.get("max_hierarchy_level", "").strip()
        if max_hierarchy_level:
            try:
                qs = qs.filter(max_hierarchy_level=int(max_hierarchy_level))
            except ValueError:
                return Response({"error": "max_hierarchy_level must be an integer."}, status=400)

        return Response({"count": qs.count(), "results": CampaignSerializer(qs, many=True).data})


# ==============================================================================
# EVENT VIEWS
# ==============================================================================

@extend_schema(tags=["Event"])
@extend_schema_view(
    get=extend_schema(
        summary="List all events",
        description="Returns all events across all campaigns.",
        responses={200: EventSerializer(many=True)},
    ),
    post=extend_schema(
        summary="Create an event",
        description="Creates a new event under the specified campaign.",
        request={
            "application/json": {
                "type": "object",
                "required": ["title", "campaign_id"],
                "properties": {
                    "title":       {"type": "string", "example": "Product Launch"},
                    "description": {"type": "string", "example": "Main launch event"},
                    "campaign_id": {"type": "string", "format": "uuid", "example": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
                    "start_date":  {"type": "string", "format": "date", "example": "2026-06-01"},
                    "end_date":    {"type": "string", "format": "date", "example": "2026-06-07"},
                    "event_type":  {"type": "string", "example": "launch"},
                    "priority":    {"type": "string", "enum": ["low", "medium", "high"], "example": "high"},
                    "status":      {"type": "string", "enum": ["planning", "in_progress", "upcoming"], "example": "planning"},
                    "location":    {"type": "string", "example": "Mumbai"},
                    "tags":        {"type": "string", "example": "launch,digital,q2"},
                },
            }
        },
        responses={
            201: EventSerializer,
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Campaign not found"),
        },
        examples=[
            OpenApiExample(
                "Create Event Example",
                value={
                    "title": "Product Launch",
                    "description": "Main launch event",
                    "campaign_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-07",
                    "event_type": "launch",
                    "priority": "high",
                    "status": "planning",
                    "location": "Mumbai",
                    "tags": "launch,digital,q2",
                },
                request_only=True,
            )
        ],
    ),
)
class EventListView(APIView):
    """GET all events / POST create event."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
        events = Event.objects.select_related("campaign", "created_by").all()
        return Response(EventSerializer(events, many=True).data)

    def post(self, request):
        campaign_id = request.data.get("campaign_id")
        if not campaign_id:
            return Response({"error": "campaign_id is required."}, status=400)

        try:
            campaign = Campaign.objects.get(campaign_id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)

        try:
            payload = EventCreateSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        event = Event.objects.create(
            campaign=campaign,
            title=payload.title,
            description=payload.description,
            start_date=payload.start_date,
            end_date=payload.end_date,
            event_type=payload.event_type,
            priority=payload.priority,
            status=payload.status,
            location=payload.location,
            tags=payload.tags,
            created_by=request.user,
        )
        return Response(EventSerializer(event).data, status=201)


@extend_schema(tags=["Event"])
@extend_schema_view(
    get=extend_schema(
        summary="Get event details",
        description="Retrieve a single event by its UUID.",
        parameters=[
            OpenApiParameter(
                name="event_id", type=str, location=OpenApiParameter.PATH,
                description="Unique event UUID",
            )
        ],
        responses={
            200: EventSerializer,
            404: OpenApiResponse(
                response={"type": "object", "properties": {"error": {"type": "string"}}},
                description="Event not found",
                examples=[OpenApiExample("Not Found", value={"error": "Event not found."})],
            ),
        },
    ),
    patch=extend_schema(
        summary="Update event (partial)",
        description="Partially update an event. Only the creator or an admin may edit.",
        parameters=[
            OpenApiParameter(
                name="event_id", type=str, location=OpenApiParameter.PATH,
                description="Unique event UUID",
            )
        ],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "description": {"type": "string"},
                    "start_date":  {"type": "string", "format": "date"},
                    "end_date":    {"type": "string", "format": "date"},
                    "event_type":  {"type": "string"},
                    "priority":    {"type": "string", "enum": ["low", "medium", "high"]},
                    "status":      {"type": "string", "enum": ["planning", "in_progress", "upcoming"]},
                    "location":    {"type": "string"},
                    "tags":        {"type": "string", "description": "Comma-separated tags e.g. design,ux,launch"},
                },
                "example": {
                    "title":      "Updated Event",
                    "description":"New description",
                    "start_date": "2026-06-01",
                    "end_date":   "2026-06-07",
                    "event_type": "webinar",
                    "priority":   "high",
                    "status":     "in_progress",
                    "location":   "Delhi",
                    "tags":       "webinar,digital",
                },
            }
        },
        responses={
            200: EventSerializer,
            403: OpenApiResponse(
                response={"type": "object", "properties": {"error": {"type": "string"}}},
                examples=[OpenApiExample("Forbidden", value={"error": "Only creator or admin can edit."})],
            ),
            404: OpenApiResponse(
                response={"type": "object", "properties": {"error": {"type": "string"}}},
                examples=[OpenApiExample("Not Found", value={"error": "Event not found."})],
            ),
        },
    ),
    delete=extend_schema(
        summary="Delete event",
        description="Delete an event. Only the creator or an admin may delete.",
        parameters=[
            OpenApiParameter(
                name="event_id", type=str, location=OpenApiParameter.PATH,
                description="Unique event UUID",
            )
        ],
        responses={
            200: OpenApiResponse(
                response={"type": "object", "properties": {"message": {"type": "string"}}},
                examples=[OpenApiExample("Deleted", value={"message": "Event deleted."})],
            ),
            403: OpenApiResponse(
                response={"type": "object", "properties": {"error": {"type": "string"}}},
                examples=[OpenApiExample("Forbidden", value={"error": "Only creator or admin can delete."})],
            ),
            404: OpenApiResponse(
                response={"type": "object", "properties": {"error": {"type": "string"}}},
                examples=[OpenApiExample("Not Found", value={"error": "Event not found."})],
            ),
        },
    ),
)
class EventDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def _get(self, event_id):
        try:
            return Event.objects.select_related("campaign", "created_by").get(event_id=event_id)
        except Event.DoesNotExist:
            return None

    def get(self, request, event_id):
        e = self._get(event_id)
        if not e:
            return Response({"error": "Event not found."}, status=404)
        return Response(EventSerializer(e).data)

    def patch(self, request, event_id):
        e = self._get(event_id)
        if not e:
            return Response({"error": "Event not found."}, status=404)
        if request.user.role != "admin" and e.created_by != request.user:
            return Response({"error": "Only creator or admin can edit."}, status=403)

        try:
            payload = EventUpdateSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(e, field, value)
        e.save()
        return Response(EventSerializer(e).data)

    def delete(self, request, event_id):
        e = self._get(event_id)
        if not e:
            return Response({"error": "Event not found."}, status=404)
        if request.user.role != "admin" and e.created_by != request.user:
            return Response({"error": "Only creator or admin can delete."}, status=403)
        e.delete()
        return Response({"message": "Event deleted."})



@extend_schema(tags=["Event"])
class EventTasksView(APIView):
    """GET all root tasks (no parent_task) under a specific event."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, event_id):
        try:
            event = Event.objects.select_related("campaign").get(event_id=event_id)
        except Event.DoesNotExist:
            return Response({"error": "Event not found."}, status=404)

        tasks = Task.objects.filter(
            event=event, parent_task__isnull=True
        ).select_related("assigned_by", "assigned_to")
        return Response({
            "event": event.title,
            "campaign": event.campaign.title,
            "tasks": TaskListSerializer(tasks, many=True).data,
        })


@extend_schema(
    tags=["Event"],
    summary="Filter and search events",
    description=(
        "Filterable event list. Supports full-text search on title and filtering by "
        "status, priority, event_type, location, tags, campaign, creator, and date ranges."
    ),
    parameters=[
        OpenApiParameter("search",       OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, description="Search by title"),
        OpenApiParameter("status",       OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, enum=["planning", "in_progress", "upcoming"]),
        OpenApiParameter("priority",     OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, enum=["low", "medium", "high"]),
        OpenApiParameter("event_type",   OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, description="Filter by event type"),
        OpenApiParameter("location",     OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, description="Filter by location (partial match)"),
        OpenApiParameter("tags",         OpenApiTypes.STR,  OpenApiParameter.QUERY, required=False, description="Filter by tag (partial match)"),
        OpenApiParameter("campaign_id",  OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by campaign UUID"),
        OpenApiParameter("created_by",   OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by creator user UUID"),
        OpenApiParameter("start_after",  OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Events starting on or after this date"),
        OpenApiParameter("start_before", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Events starting on or before this date"),
        OpenApiParameter("end_after",    OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Events ending on or after this date"),
        OpenApiParameter("end_before",   OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Events ending on or before this date"),
    ],
    responses={
        200: inline_serializer(
            name="EventFilterResponse",
            fields={
                "count":   drf_serializers.IntegerField(),
                "results": EventSerializer(many=True),
            },
        ),
        400: OpenApiResponse(description="Invalid filter parameter"),
    },
)
class EventFilterSearchView(APIView):
    """Filterable event list with date range, status, priority, tags, and campaign filters."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
        try:
            filters = EventFilterSchema.model_validate(dict(request.query_params))
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        qs = Event.objects.select_related("campaign", "created_by")

        if filters.search:
            qs = qs.filter(title__icontains=filters.search)
        if filters.status:
            qs = qs.filter(status=filters.status)
        if filters.priority:
            qs = qs.filter(priority=filters.priority)
        if filters.event_type:
            qs = qs.filter(event_type__icontains=filters.event_type)
        if filters.location:
            qs = qs.filter(location__icontains=filters.location)
        if filters.tags:
            qs = qs.filter(tags__icontains=filters.tags)
        if filters.campaign_id:
            qs = qs.filter(campaign__campaign_id=filters.campaign_id)
        if filters.created_by:
            qs = qs.filter(created_by__user_id=filters.created_by)
        if filters.start_after:
            qs = qs.filter(start_date__gte=filters.start_after)
        if filters.start_before:
            qs = qs.filter(start_date__lte=filters.start_before)
        if filters.end_after:
            qs = qs.filter(end_date__gte=filters.end_after)
        if filters.end_before:
            qs = qs.filter(end_date__lte=filters.end_before)

        return Response({"count": qs.count(), "results": EventSerializer(qs, many=True).data})

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
            "assigned_to": drf_serializers.UUIDField(help_text="UUID of user to assign task to"),
            "tags": drf_serializers.CharField(required=False),
            "priority": drf_serializers.ChoiceField(choices=["low", "medium", "high"], required=False),
            "marketing_type": drf_serializers.CharField(required=False),
            "due_date": drf_serializers.DateField(required=False),
            "launch_date": drf_serializers.DateField(required=False),                          # new
            "estimated_hours": drf_serializers.DateTimeField(required=False),                  # new
            "completed_hours": drf_serializers.DateTimeField(required=False),                  # new
        }
    )
)
class TaskListView(APIView):
    """GET all tasks (cached) / POST create a task."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
        cached = cache.get(TASK_LIST_CACHE_KEY)
        if cached:
            return Response(json.loads(cached))

        tasks = Task.objects.select_related(
            "assigned_by", "assigned_to", "last_transferred_by", "campaign", "event", "parent_task"
        ).all()
        data = TaskListSerializer(tasks, many=True).data
        cache.set(TASK_LIST_CACHE_KEY, json.dumps(data, cls=DjangoJSONEncoder), CACHE_TTL)
        return Response(data)

    def post(self, request):
        try:
            payload = TaskCreateSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        try:
            campaign = Campaign.objects.get(campaign_id=payload.campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found."}, status=404)

        event = None
        if payload.event_id:
            try:
                event = Event.objects.get(event_id=payload.event_id, campaign=campaign)
            except Event.DoesNotExist:
                return Response({"error": "Event not found or does not belong to this campaign."}, status=404)

        parent_task = None
        if payload.parent_task_id:
            try:
                parent_task = Task.objects.get(task_id=payload.parent_task_id, campaign=campaign)
            except Task.DoesNotExist:
                return Response({"error": "Parent task not found or does not belong to this campaign."}, status=404)

        assigned_to = None
        if payload.assigned_to:
            try:
                assigned_to = User.objects.get(user_id=payload.assigned_to)
            except User.DoesNotExist:
                return Response({"error": "Assigned user not found."}, status=404)

        try:
            with transaction.atomic():
                task = Task(
                    title=payload.title,
                    description=payload.description,
                    campaign=campaign,
                    event=event,
                    parent_task=parent_task,
                    tags=payload.tags,
                    priority=payload.priority,
                    marketing_type=payload.marketing_type,
                    status=payload.status,
                    due_date=payload.due_date,
                    launch_date=payload.launch_date,
                    estimated_hours=payload.estimated_hours,
                    completed_hours=payload.completed_hours,
                    assigned_by=request.user,
                    assigned_to=assigned_to,
                )
                task.full_clean()  # runs model-level clean() for hierarchy validation
                task.save()

                TaskHistory.objects.create(
                    task=task,
                    action="created",
                    performed_by=request.user,
                    detail=f"Task created and assigned to {assigned_to.full_name if assigned_to else 'nobody'}",
                )
        except ValidationError as ve:
            return Response({"error": str(ve)}, status=400)

        _bust_task_cache()
        if assigned_to:
            send_task_assignment_email(
                assignee_email=assigned_to.email,
                assignee_name=assigned_to.full_name,
                task_title=task.title,
                assigned_by_name=request.user.full_name,
            )
        return Response(TaskSerializer(task).data, status=201)


@extend_schema(tags=["Board"])
class TaskDetailView(APIView):
    """GET a single task / DELETE a task."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def _get_task(self, task_id):
        try:
            return Task.objects.select_related(
                "assigned_by", "assigned_to", "last_transferred_by",
                "campaign", "event", "parent_task",
            ).prefetch_related("discussion__author", "history__performed_by", "subtasks").get(task_id=task_id)
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
    """GET subtasks of a task."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, task_id):
        try:
            task = Task.objects.select_related("campaign").get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)
        subtasks = Task.objects.filter(parent_task=task).select_related("assigned_by", "assigned_to")
        return Response({
            "parent_task": task.title,
            "depth": task.get_depth(),
            "max_allowed_depth": task.campaign.max_hierarchy_level,
            "subtasks": TaskListSerializer(subtasks, many=True).data,
        })



@extend_schema(
    tags=["Board"],
    summary="Update task metadata (partial)",
    description=(
        "Partially update a task's metadata. Only the task creator (`assigned_by`), "
        "the last user who transferred the task, or an admin may edit. "
        "A history entry is recorded for every changed field."
    ),
    parameters=[
        OpenApiParameter(
            name="task_id", type=str, location=OpenApiParameter.PATH,
            description="UUID of the task to update",
        )
    ],
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "title":           {"type": "string", "maxLength": 255, "example": "Updated task title"},
                "description":     {"type": "string", "example": "Revised scope for Q3"},
                "tags":            {"type": "string", "maxLength": 500, "example": "design,revised",
                                    "description": "Comma-separated tags"},
                "priority":        {"type": "string", "enum": ["low", "medium", "high"]},
                "status":          {"type": "string", "enum": ["to_do", "in_progress", "completed", "in_review"]},
                "marketing_type":  {"type": "string", "example": "email"},
                "due_date":        {"type": "string", "format": "date", "example": "2026-08-01"},
                "launch_date":     {"type": "string", "format": "date", "example": "2026-08-10"},
                "estimated_hours": {"type": "string", "example": "10:00:00",
                                    "description": "Duration as HH:MM:SS or seconds integer"},
                "completed_hours": {"type": "string", "example": "05:30:00",
                                    "description": "Duration as HH:MM:SS or seconds integer"},
            },
            "example": {
                "title": "protocol checking",
                "description": "checking ip and smtp protocols",
                "tags": "car",
                "status": "in_progress",
                "priority": "high",
                "due_date": "2026-08-01",
                "estimated_hours": "10:00:00",
                "completed_hours": "05:30:00",
            },
        }
    },
    responses={
        200: TaskSerializer,
        400: OpenApiResponse(
            response={"type": "object", "properties": {"errors": {"type": "array"}}},
            description="Validation error",
            examples=[OpenApiExample("Validation Error", value={"errors": [{"field": "priority", "message": "Input should be 'low', 'medium' or 'high'"}]})],
        ),
        403: OpenApiResponse(
            response={"type": "object", "properties": {"error": {"type": "string"}}},
            description="Permission denied",
            examples=[OpenApiExample("Forbidden", value={"error": "Only the task creator, last transferrer, or admin can edit."})],
        ),
        404: OpenApiResponse(
            response={"type": "object", "properties": {"error": {"type": "string"}}},
            description="Task not found",
            examples=[OpenApiExample("Not Found", value={"error": "Task not found."})],
        ),
        401: OpenApiResponse(description="Unauthorized"),
    },
)
class TaskUpdateView(APIView):
    """PATCH task metadata."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
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

        try:
            payload = TaskUpdateSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        changed = []
        for field, new_val in payload.model_dump(exclude_unset=True).items():
            old_val = getattr(task, field)
            if str(old_val) != str(new_val):
                changed.append(f"{field}: '{old_val}' → '{new_val}'")
            setattr(task, field, new_val)

        if not changed:
            return Response({"message": "No changes.", "task": TaskSerializer(task).data})

        task.save()
        TaskHistory.objects.create(
            task=task, action="updated", performed_by=user, detail=" | ".join(changed)
        )
        _bust_task_cache()
        return Response(TaskSerializer(task).data)




@extend_schema(
    tags=["Board"],
    summary="Transfer task to another user",
    description=(
        "Reassign a task to a different user. Only the current assignee (`assigned_to`) "
        "or an admin may transfer. A history entry is recorded and a transfer notification "
        "email is sent to the new assignee."
    ),
    parameters=[
        OpenApiParameter(
            name="task_id", type=str, location=OpenApiParameter.PATH,
            description="UUID of the task to transfer",
        )
    ],
    request={
        "application/json": {
            "type": "object",
            "required": ["transfer_to"],
            "properties": {
                "transfer_to": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID of the user to transfer the task to",
                    "example": "b2c3d4e5-0000-0000-0000-000000000002",
                },
            },
            "example": {"transfer_to": "b2c3d4e5-0000-0000-0000-000000000002"},
        }
    },
    responses={
        200: inline_serializer(
            name="TransferTaskResponse",
            fields={
                "message": drf_serializers.CharField(),
                "task":    TaskSerializer(),
            },
        ),
        400: OpenApiResponse(
            response={"type": "object", "properties": {"error": {"type": "string"}}},
            description="Task already assigned to target user",
            examples=[OpenApiExample("Already Assigned", value={"error": "Task is already assigned to this user."})],
        ),
        403: OpenApiResponse(
            response={"type": "object", "properties": {"error": {"type": "string"}}},
            description="Permission denied",
            examples=[OpenApiExample("Forbidden", value={"error": "Only the current assignee can transfer."})],
        ),
        404: OpenApiResponse(
            response={"type": "object", "properties": {"error": {"type": "string"}}},
            description="Task or target user not found",
            examples=[
                OpenApiExample("Task Not Found", value={"error": "Task not found."}),
                OpenApiExample("User Not Found", value={"error": "Target user not found."}),
            ],
        ),
        401: OpenApiResponse(description="Unauthorized"),
    },
    examples=[
        OpenApiExample(
            "Transfer Task",
            value={"transfer_to": "b2c3d4e5-0000-0000-0000-000000000002"},
            request_only=True,
        ),
        OpenApiExample(
            "Transfer Success",
            value={
                "message": "Transferred to Jane Doe.",
                "task": {"task_id": "...", "title": "Design homepage banner", "assigned_to": {"full_name": "Jane Doe"}},
            },
            response_only=True,
        ),
    ],
)
class TransferTaskView(APIView):
    """POST transfer task to another user."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["write", "update", "admin"]

    def post(self, request, task_id):
        try:
            task = Task.objects.select_related("assigned_to", "assigned_by").get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        if request.user.role != "admin" and task.assigned_to != request.user:
            return Response({"error": "Only the current assignee can transfer."}, status=403)

        try:
            payload = TaskTransferSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        try:
            new_assignee = User.objects.get(user_id=payload.transfer_to)
        except User.DoesNotExist:
            return Response({"error": "Target user not found."}, status=404)

        if new_assignee == task.assigned_to:
            return Response({"error": "Task is already assigned to this user."}, status=400)

        old_assignee = task.assigned_to
        with transaction.atomic():
            task.last_transferred_by = request.user
            task.assigned_to = new_assignee
            task.save()
            TaskHistory.objects.create(
                task=task,
                action="transferred",
                performed_by=request.user,
                detail=f"Transferred from {old_assignee.full_name} to {new_assignee.full_name}",
            )

        _bust_task_cache()
        send_task_transfer_email(
            new_assignee_email=new_assignee.email,
            new_assignee_name=new_assignee.full_name,
            task_title=task.title,
            transferred_by_name=request.user.full_name,
        )
        return Response({"message": f"Transferred to {new_assignee.full_name}.", "task": TaskSerializer(task).data})


@extend_schema(
    tags=["Board"],
    parameters=[
        OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=["to_do", "in_progress", "completed", "in_review"]),
        OpenApiParameter("priority", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, enum=["low", "medium", "high"]),
        OpenApiParameter("campaign_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by campaign UUID"),
        OpenApiParameter("event_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by event UUID"),
        OpenApiParameter("assigned_to", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by assigned user UUID"),
        OpenApiParameter("marketing_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("tags", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("due_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("due_before", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("due_after", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("launch_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Filter by exact launch date"),         # new
        OpenApiParameter("launch_before", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Filter tasks launching before date"),  # new
        OpenApiParameter("launch_after", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="Filter tasks launching after date"),    # new
        OpenApiParameter("root_only", OpenApiTypes.BOOL, OpenApiParameter.QUERY, required=False, description="If true, return only root tasks (no subtasks)"),
        OpenApiParameter("assigned_by", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False, description="Filter by creator user UUID"),

# ===== Due Date =====
        OpenApiParameter("due_month", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="1-12"),
        OpenApiParameter("due_year", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("due_quarter", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, enum=[1,2,3,4]),

# ===== Launch Date =====
        OpenApiParameter("launch_month", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="1-12"),
        OpenApiParameter("launch_year", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("launch_quarter", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, enum=[1,2,3,4]),

# ===== Created At =====
        OpenApiParameter("created_month", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="1-12"),
        OpenApiParameter("created_year", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("created_quarter", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, enum=[1,2,3,4]),

# ===== Created Date Ranges =====
        OpenApiParameter("created_before", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("created_after", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
    ]
)
class TaskFilterSearchView(APIView):
    """Filterable task list with campaign/event/hierarchy filters."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request):
        try:
            filters = TaskFilterSchema.model_validate(dict(request.query_params))
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        qs = Task.objects.select_related(
            "assigned_by", "assigned_to", "last_transferred_by", "campaign", "event", "parent_task"
        )

        if filters.search:
            qs = qs.filter(title__icontains=filters.search)
        if filters.status:
            qs = qs.filter(status=filters.status)
        if filters.priority:
            qs = qs.filter(priority=filters.priority)
        if filters.campaign_id:
            qs = qs.filter(campaign__campaign_id=filters.campaign_id)
        if filters.event_id:
            qs = qs.filter(event__event_id=filters.event_id)
        if filters.assigned_to:
            qs = qs.filter(assigned_to__user_id=filters.assigned_to)
        if filters.marketing_type:
            qs = qs.filter(marketing_type__icontains=filters.marketing_type)
        if filters.tags:
            qs = qs.filter(tags__icontains=filters.tags)
        if filters.due_date:
            qs = qs.filter(due_date=filters.due_date)
        if filters.due_before:
            qs = qs.filter(due_date__lte=filters.due_before)
        if filters.due_after:
            qs = qs.filter(due_date__gte=filters.due_after)
        if filters.launch_date:
            qs = qs.filter(launch_date=filters.launch_date)
        if filters.launch_before:
            qs = qs.filter(launch_date__lte=filters.launch_before)
        if filters.launch_after:
            qs = qs.filter(launch_date__gte=filters.launch_after)
        if filters.root_only:
            qs = qs.filter(parent_task__isnull=True)
        if filters.assigned_by:
            qs = qs.filter(assigned_by__user_id=filters.assigned_by)
        if filters.due_year:
            qs = qs.filter(due_date__year=filters.due_year)
        if filters.due_quarter:
            qs = qs.filter(
                due_date__month__in=quarter_months[filters.due_quarter]
            )

        #launch date filters

        if filters.launch_month:
            qs = qs.filter(launch_date__month=filters.launch_month)
        if filters.launch_year:
            qs = qs.filter(launch_date__year=filters.launch_year)
        if filters.launch_quarter:
            qs = qs.filter(
            launch_date__month__in=quarter_months[filters.launch_quarter]
            )

        #created at filter 

        if filters.created_month:
            qs = qs.filter(created_at__month=filters.created_month)
        if filters.created_year:
            qs = qs.filter(created_at__year=filters.created_year)

        if filters.created_quarter:
            qs = qs.filter(
            created_at__month__in=quarter_months[filters.created_quarter]
            )
        if filters.created_before:
            qs = qs.filter(created_at__date__lte=filters.created_before)
        if filters.created_after:
            qs = qs.filter(created_at__date__gte=filters.created_after)

        return Response({"count": qs.count(), "results": TaskListSerializer(qs, many=True).data})



# ==============================================================================
# DISCUSSION
# ==============================================================================


@extend_schema(tags=["Board"])
@extend_schema_view(
    get=extend_schema(
        summary="List discussion comments for a task",
        description="Returns all comments on the specified task, ordered by creation time (oldest first).",
        parameters=[
            OpenApiParameter(
                name="task_id", type=str, location=OpenApiParameter.PATH,
                description="UUID of the task whose comments to retrieve",
            )
        ],
        responses={
            200: DiscussionSerializer(many=True),
            404: OpenApiResponse(
                response={"type": "object", "properties": {"error": {"type": "string"}}},
                description="Task not found",
                examples=[OpenApiExample("Not Found", value={"error": "Task not found."})],
            ),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
        },
    ),
    post=extend_schema(
        summary="Add a comment to a task",
        description=(
            "Post a new discussion comment on the specified task. "
            "The authenticated user is automatically set as the author."
        ),
        parameters=[
            OpenApiParameter(
                name="task_id", type=str, location=OpenApiParameter.PATH,
                description="UUID of the task to comment on",
            )
        ],
        request={
            "application/json": {
                "type": "object",
                "required": ["message"],
                "properties": {
                    "message": {
                        "type": "string",
                        "minLength": 1,
                        "example": "This needs a final review before we mark it complete.",
                    },
                },
                "example": {"message": "This needs a final review before we mark it complete."},
            }
        },
        responses={
            201: DiscussionSerializer,
            400: OpenApiResponse(
                response={"type": "object", "properties": {"errors": {"type": "array"}}},
                description="Validation error (e.g. empty message)",
                examples=[OpenApiExample("Empty Message", value={"errors": [{"field": "message", "message": "String should have at least 1 character"}]})],
            ),
            404: OpenApiResponse(
                response={"type": "object", "properties": {"error": {"type": "string"}}},
                description="Task not found",
                examples=[OpenApiExample("Not Found", value={"error": "Task not found."})],
            ),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
        },
        examples=[
            OpenApiExample(
                "Post Comment",
                value={"message": "This needs a final review before we mark it complete."},
                request_only=True,
            ),
        ],
    ),
)
class DiscussionView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "update", "admin"]

    def get(self, request, task_id):
        try:
            task = Task.objects.get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)
        comments = Discussion.objects.filter(task=task).select_related("author")
        return Response(DiscussionSerializer(comments, many=True).data)

    def post(self, request, task_id):
        try:
            task = Task.objects.get(task_id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        try:
            payload = DiscussionCreateSchema.model_validate(request.data)
        except PydanticValidationError as e:
            return _pydantic_errors(e)

        comment = Discussion.objects.create(task=task, author=request.user, message=payload.message)
        return Response(DiscussionSerializer(comment).data, status=201)




@extend_schema(
    tags=["Board"],
    summary="Delete a discussion comment",
    description=(
        "Permanently delete a specific discussion comment from a task. "
        "Only the comment author or an admin may delete."
    ),
    parameters=[
        OpenApiParameter(
            name="task_id", type=str, location=OpenApiParameter.PATH,
            description="UUID of the task the comment belongs to",
        ),
        OpenApiParameter(
            name="comment_id", type=str, location=OpenApiParameter.PATH,
            description="UUID of the comment to delete",
        ),
    ],
    responses={
        200: OpenApiResponse(
            response={"type": "object", "properties": {"message": {"type": "string"}}},
            description="Comment deleted successfully",
            examples=[OpenApiExample("Deleted", value={"message": "Comment deleted."})],
        ),
        403: OpenApiResponse(
            response={"type": "object", "properties": {"error": {"type": "string"}}},
            description="Permission denied",
            examples=[OpenApiExample("Forbidden", value={"error": "You can only delete your own comments."})],
        ),
        404: OpenApiResponse(
            response={"type": "object", "properties": {"error": {"type": "string"}}},
            description="Comment not found (or does not belong to this task)",
            examples=[OpenApiExample("Not Found", value={"error": "Comment not found."})],
        ),
        401: OpenApiResponse(description="Unauthorized"),
    },
)
class DiscussionDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = "content"
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


