import json
from datetime import datetime
from django.core.cache import cache
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.models import User
from utils.permissions.base import HasRBACPermission
from utils.notifications.services import send_task_assignment_email, send_task_transfer_email
from .models import Task, TaskHistory, Discussion
from .serializers import TaskSerializer, TaskListSerializer, DiscussionSerializer
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers

TASK_LIST_CACHE_KEY = "kanban_all_tasks"
CACHE_TTL = 60 * 5  # 5 minutes


def _bust_task_cache():
    """Invalidate the task list cache whenever data changes."""
    cache.delete(TASK_LIST_CACHE_KEY)


# ==============================================================================
# TASK LIST — GET all / POST create
# ==============================================================================
@extend_schema(
    tags=['Board'],
    request=inline_serializer(
        name='CreateTaskRequest',
        fields={
            'title':          drf_serializers.CharField(),
            'description':    drf_serializers.CharField(required=False),
            'assigned_to':    drf_serializers.IntegerField(help_text='User ID to assign task to'),
            'tags':           drf_serializers.CharField(required=False, help_text='Comma-separated e.g. design,ux,q2'),
            'priority':       drf_serializers.ChoiceField(choices=['low', 'medium', 'high'], required=False),
            'marketing_type': drf_serializers.CharField(required=False, help_text='e.g. Social Media, Blog'),
            'due_date':       drf_serializers.DateField(required=False, help_text='YYYY-MM-DD'),
        }
    )
)
class TaskListView(APIView):
    """
    GET  — list all tasks (cached in Redis 5 min).
    POST — create a new task and assign it to any user.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['read', 'write', 'update', 'admin']

    def get(self, request):
        cached = cache.get(TASK_LIST_CACHE_KEY)
        if cached:
            return Response(json.loads(cached))

        tasks      = Task.objects.select_related('assigned_by', 'assigned_to', 'last_transferred_by').all()
        serializer = TaskListSerializer(tasks, many=True)
        data       = serializer.data

        cache.set(TASK_LIST_CACHE_KEY, json.dumps(data), CACHE_TTL)
        return Response(data)

    def post(self, request):
        title          = request.data.get('title', '').strip()
        description    = request.data.get('description', '').strip()
        assigned_to_id = request.data.get('assigned_to')

        # New optional fields on creation
        tags           = request.data.get('tags', '').strip()
        priority       = request.data.get('priority', 'medium').strip()
        marketing_type = request.data.get('marketing_type', '').strip()
        due_date       = request.data.get('due_date', None)

        if not title:
            return Response({"error": "Title is required."}, status=400)
        if not assigned_to_id:
            return Response({"error": "assigned_to (user id) is required."}, status=400)

        # Validate priority
        valid_priorities = [p[0] for p in Task.PRIORITY_CHOICES]
        if priority not in valid_priorities:
            return Response({"error": f"Invalid priority. Choose from: {valid_priorities}"}, status=400)

        # Validate due_date format if provided
        if due_date:
            try:
                datetime.strptime(due_date, '%Y-%m-%d')
            except ValueError:
                return Response({"error": "due_date must be in YYYY-MM-DD format."}, status=400)

        try:
            assignee = User.objects.get(id=assigned_to_id)
        except User.DoesNotExist:
            return Response({"error": "Assigned user not found."}, status=404)

        with transaction.atomic():
            task = Task.objects.create(
                title          = title,
                description    = description,
                tags           = tags,
                priority       = priority,
                marketing_type = marketing_type,
                due_date       = due_date or None,
                assigned_by    = request.user,
                assigned_to    = assignee,
                status         = 'to_do',
            )
            TaskHistory.objects.create(
                task         = task,
                action       = 'created',
                performed_by = request.user,
                detail       = f"Task created and assigned to {assignee.full_name} ({assignee.email})",
            )

        _bust_task_cache()

        send_task_assignment_email(
            assignee_email   = assignee.email,
            assignee_name    = assignee.full_name,
            task_title       = task.title,
            assigned_by_name = request.user.full_name,
        )

        return Response(TaskSerializer(task).data, status=201)


# ==============================================================================
# TASK DETAIL — GET / DELETE
# ==============================================================================
@extend_schema(
    tags=['Board'],
    request=inline_serializer(
        name='UpdateTaskStatusRequest',
        fields={
            'status': drf_serializers.ChoiceField(
                choices=['to_do', 'in_progress', 'completed', 'blocked', 'approved'],
                help_text='New status for the task — only current assignee or admin can change',
            ),
        }
    )
)
class TaskDetailView(APIView):
    """
    GET    — full task detail including discussion and history.
    PATCH  — update STATUS only (to_do / in_progress / completed / blocked / approved).
             Only the current assignee (or admin) can change the status.
    DELETE — only the original creator (assigned_by) or admin can delete.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['read', 'write', 'update', 'admin']

    def _get_task(self, task_id):
        try:
            return Task.objects.select_related(
                'assigned_by', 'assigned_to', 'last_transferred_by'
            ).prefetch_related('discussion__author', 'history__performed_by').get(id=task_id)
        except Task.DoesNotExist:
            return None

    def get(self, request, task_id):
        task = self._get_task(task_id)
        if not task:
            return Response({"error": "Task not found."}, status=404)
        return Response(TaskSerializer(task).data)

    # def patch(self, request, task_id):
    #     """Change status. Only the current assignee (or admin) can do this."""
    #     task = self._get_task(task_id)
    #     if not task:
    #         return Response({"error": "Task not found."}, status=404)

    #     if request.user.role != 'admin' and task.assigned_to != request.user:
    #         return Response(
    #             {"error": "Only the current assignee can update the task status."},
    #             status=403
    #         )

    #     new_status     = request.data.get('status', '').strip()
    #     valid_statuses = [s[0] for s in Task.STATUS_CHOICES]

    #     if new_status not in valid_statuses:
    #         return Response(
    #             {"error": f"Invalid status. Choose from: {valid_statuses}"},
    #             status=400
    #         )

    #     old_status    = task.status
    #     task.status   = new_status
    #     task.save()

    #     TaskHistory.objects.create(
    #         task         = task,
    #         action       = 'stage_changed',
    #         performed_by = request.user,
    #         detail       = f"Status changed from '{old_status}' to '{new_status}'",
    #     )

    #     _bust_task_cache()
    #     return Response(TaskSerializer(task).data)

    def delete(self, request, task_id):
        """Only the original creator or admin can delete a task."""
        task = self._get_task(task_id)
        if not task:
            return Response({"error": "Task not found."}, status=404)

        if request.user.role != 'admin' and task.assigned_by != request.user:
            return Response(
                {"error": "Only the original task creator or an admin can delete this task."},
                status=403
            )

        task.delete()
        _bust_task_cache()
        return Response({"message": "Task deleted."}, status=200)


# ==============================================================================
# TASK UPDATE — PATCH metadata (tags, priority, marketing_type, due_date, title, description)
# ==============================================================================
@extend_schema(
    tags=['Board'],
    request=inline_serializer(
        name='UpdateTaskMetadataRequest',
        fields={
            'title':          drf_serializers.CharField(required=False),
            'description':    drf_serializers.CharField(required=False),
            'tags':           drf_serializers.CharField(required=False, help_text='Comma-separated e.g. design,ux'),
            'priority':       drf_serializers.ChoiceField(choices=['low', 'medium', 'high'], required=False),
            'marketing_type': drf_serializers.CharField(required=False),
            'due_date':       drf_serializers.DateField(required=False, help_text='YYYY-MM-DD'),
        }
    )
)
class TaskUpdateView(APIView):
    """
    PATCH /api/board/tasks/<task_id>/update/

    Edits task metadata. Only the original creator (assigned_by),
    the person who last transferred it (last_transferred_by), or admin can do this.

    Editable fields:
        title           — task title
        description     — task description
        tags            — comma-separated string e.g. "design,ux,q2"
        priority        — low | medium | high
        marketing_type  — free text e.g. "Social Media", "Blog", "Email Campaign"
        due_date        — YYYY-MM-DD format

    Status changes go through TaskDetailView PATCH — not here.
    Every successful update is logged in TaskHistory.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['write', 'update', 'admin']

    def patch(self, request, task_id):
        try:
            task = Task.objects.select_related('assigned_by', 'last_transferred_by').get(id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        user = request.user

        # Only original creator, last transferrer, or admin can edit metadata
        can_edit = (
            user.role == 'admin' or
            task.assigned_by == user or
            task.last_transferred_by == user
        )
        if not can_edit:
            return Response(
                {"error": "Only the task creator, last transferrer, or admin can edit task details."},
                status=403
            )

        editable_fields = ['title', 'description', 'tags', 'priority', 'marketing_type', 'due_date']
        changed = []

        for field in editable_fields:
            if field not in request.data:
                continue

            new_val = request.data[field]

            # Validate priority
            if field == 'priority':
                valid = [p[0] for p in Task.PRIORITY_CHOICES]
                if new_val not in valid:
                    return Response(
                        {"error": f"Invalid priority. Choose from: {valid}"},
                        status=400
                    )

            # Validate due_date format
            if field == 'due_date' and new_val:
                try:
                    datetime.strptime(new_val, '%Y-%m-%d')
                except ValueError:
                    return Response(
                        {"error": "due_date must be in YYYY-MM-DD format."},
                        status=400
                    )

            # Validate title not empty
            if field == 'title' and not str(new_val).strip():
                return Response({"error": "Title cannot be empty."}, status=400)

            old_val = getattr(task, field)
            if str(old_val) != str(new_val):
                changed.append(f"{field}: '{old_val}' → '{new_val}'")
            setattr(task, field, new_val)

        if not changed:
            return Response({"message": "No changes detected.", "task": TaskSerializer(task).data})

        task.save()

        TaskHistory.objects.create(
            task         = task,
            action       = 'updated',
            performed_by = user,
            detail       = " | ".join(changed),
        )

        _bust_task_cache()
        return Response(TaskSerializer(task).data)


# ==============================================================================
# TRANSFER TASK
# ==============================================================================
@extend_schema(
    tags=['Board'],
    request=inline_serializer(
        name='TransferTaskRequest',
        fields={
            'transfer_to': drf_serializers.IntegerField(help_text='User ID to transfer task to'),
        }
    )
)
class TransferTaskView(APIView):
    """
    POST /api/board/tasks/<task_id>/transfer/
    Body: { "transfer_to": <user_id> }

    The current assignee (or admin) can transfer the task to any other user.
    Records the transfer in TaskHistory and updates last_transferred_by.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['write', 'update', 'admin']

    def post(self, request, task_id):
        try:
            task = Task.objects.select_related('assigned_to', 'assigned_by').get(id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        if request.user.role != 'admin' and task.assigned_to != request.user:
            return Response(
                {"error": "Only the current assignee can transfer this task."},
                status=403
            )

        transfer_to_id = request.data.get('transfer_to')
        if not transfer_to_id:
            return Response({"error": "transfer_to (user id) is required."}, status=400)

        try:
            new_assignee = User.objects.get(id=transfer_to_id)
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
                task         = task,
                action       = 'transferred',
                performed_by = request.user,
                detail       = (
                    f"Transferred from {old_assignee.full_name} ({old_assignee.email}) "
                    f"to {new_assignee.full_name} ({new_assignee.email})"
                ),
            )

        _bust_task_cache()

        send_task_transfer_email(
            new_assignee_email  = new_assignee.email,
            new_assignee_name   = new_assignee.full_name,
            task_title          = task.title,
            transferred_by_name = request.user.full_name,
        )

        return Response({
            "message": f"Task transferred to {new_assignee.full_name}.",
            "task":    TaskSerializer(task).data,
        })


# ==============================================================================
# FILTER & SEARCH
# ==============================================================================
@extend_schema(
    tags=['Board'],
    parameters=[
        OpenApiParameter(
            name='search',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Search tasks by title keyword (case-insensitive)',
            required=False,
        ),
        OpenApiParameter(
            name='status',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter by status: to_do | in_progress | completed | blocked | approved',
            required=False,
            enum=['to_do', 'in_progress', 'completed', 'blocked', 'approved'],
        ),
        OpenApiParameter(
            name='priority',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter by priority: low | medium | high',
            required=False,
            enum=['low', 'medium', 'high'],
        ),
        OpenApiParameter(
            name='marketing_type',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter by marketing type (contains match, e.g. Social Media)',
            required=False,
        ),
        OpenApiParameter(
            name='assigned_to',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Filter by assigned user ID',
            required=False,
        ),
        OpenApiParameter(
            name='tags',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter by tag name (partial match, e.g. design)',
            required=False,
        ),
        OpenApiParameter(
            name='due_date',
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description='Filter by exact due date (YYYY-MM-DD)',
            required=False,
        ),
        OpenApiParameter(
            name='due_before',
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description='Filter tasks due on or before this date (YYYY-MM-DD)',
            required=False,
        ),
        OpenApiParameter(
            name='due_after',
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description='Filter tasks due on or after this date (YYYY-MM-DD)',
            required=False,
        ),
    ]
)
class TaskFilterSearchView(APIView):
    """
    GET /api/board/tasks/filter/

    All query params are optional and fully combinable.

    ?search=<keyword>          searches title (case-insensitive contains)
    ?status=<status>           to_do | in_progress | completed | blocked | approved
    ?priority=<priority>       low | medium | high
    ?marketing_type=<text>     case-insensitive contains match
    ?assigned_to=<user_id>     filter by assigned user ID
    ?tags=<tag>                tasks containing this tag in the comma-separated tags field
    ?due_date=<YYYY-MM-DD>     exact due date match
    ?due_before=<YYYY-MM-DD>   tasks due on or before this date
    ?due_after=<YYYY-MM-DD>    tasks due on or after this date

    Response includes applied filters and a count of matching tasks.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['read', 'write', 'update', 'admin']

    def get(self, request):
        qs = Task.objects.select_related('assigned_by', 'assigned_to', 'last_transferred_by')

        # ── Search by title ───────────────────────────────────────────────────
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(title__icontains=search)

        # ── Filter by status ──────────────────────────────────────────────────
        status_param = request.query_params.get('status', '').strip()
        if status_param:
            valid_statuses = [s[0] for s in Task.STATUS_CHOICES]
            if status_param not in valid_statuses:
                return Response(
                    {"error": f"Invalid status. Choose from: {valid_statuses}"},
                    status=400
                )
            qs = qs.filter(status=status_param)

        # ── Filter by priority ────────────────────────────────────────────────
        priority_param = request.query_params.get('priority', '').strip()
        if priority_param:
            valid_priorities = [p[0] for p in Task.PRIORITY_CHOICES]
            if priority_param not in valid_priorities:
                return Response(
                    {"error": f"Invalid priority. Choose from: {valid_priorities}"},
                    status=400
                )
            qs = qs.filter(priority=priority_param)

        # ── Filter by marketing_type (contains) ───────────────────────────────
        mtype = request.query_params.get('marketing_type', '').strip()
        if mtype:
            qs = qs.filter(marketing_type__icontains=mtype)

        # ── Filter by assigned user ───────────────────────────────────────────
        assigned_to = request.query_params.get('assigned_to', '').strip()
        if assigned_to:
            try:
                qs = qs.filter(assigned_to__id=int(assigned_to))
            except ValueError:
                return Response({"error": "assigned_to must be a user ID (integer)."}, status=400)

        # ── Filter by tag ─────────────────────────────────────────────────────
        tag = request.query_params.get('tags', '').strip()
        if tag:
            qs = qs.filter(tags__icontains=tag)

        # ── Filter by due_date exact ──────────────────────────────────────────
        due_date = request.query_params.get('due_date', '').strip()
        if due_date:
            qs = qs.filter(due_date=due_date)

        # ── Filter by due_before ──────────────────────────────────────────────
        due_before = request.query_params.get('due_before', '').strip()
        if due_before:
            qs = qs.filter(due_date__lte=due_before)

        # ── Filter by due_after ───────────────────────────────────────────────
        due_after = request.query_params.get('due_after', '').strip()
        if due_after:
            qs = qs.filter(due_date__gte=due_after)

        serializer = TaskListSerializer(qs, many=True)
        return Response({
            "count": qs.count(),
            "filters_applied": {
                "search":         search         or None,
                "status":         status_param   or None,
                "priority":       priority_param or None,
                "marketing_type": mtype          or None,
                "assigned_to":    assigned_to    or None,
                "tags":           tag            or None,
                "due_date":       due_date       or None,
                "due_before":     due_before     or None,
                "due_after":      due_after      or None,
            },
            "results": serializer.data,
        })


# ==============================================================================
# FILTERED VIEWS (existing — kept exactly as before)
# ==============================================================================
@extend_schema(tags=['Board'])
class MyTasksView(APIView):
    """GET — returns only tasks currently assigned to the logged-in user."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['read', 'write', 'update', 'admin']

    def get(self, request):
        tasks      = Task.objects.filter(assigned_to=request.user).select_related('assigned_by', 'assigned_to')
        serializer = TaskListSerializer(tasks, many=True)
        return Response(serializer.data)


@extend_schema(tags=['Board'])
class TasksByUserView(APIView):
    """
    GET /api/board/tasks/user/<user_id>/
    Returns all tasks assigned to a specific user. Anyone can view.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['read', 'write', 'update', 'admin']

    def get(self, request, user_id):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)

        tasks      = Task.objects.filter(assigned_to=target_user).select_related('assigned_by', 'assigned_to')
        serializer = TaskListSerializer(tasks, many=True)
        return Response({
            "user":  {"id": target_user.id, "full_name": target_user.full_name, "email": target_user.email},
            "tasks": serializer.data,
        })


@extend_schema(tags=['Board'])
class TasksByStageView(APIView):
    """
    GET /api/board/tasks/stage/<stage>/
    Kept for backwards compatibility.
    Now supports all 5 statuses: to_do | in_progress | completed | blocked | approved
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['read', 'write', 'update', 'admin']

    def get(self, request, stage):
        valid_statuses = [s[0] for s in Task.STATUS_CHOICES]
        if stage not in valid_statuses:
            return Response({"error": f"Invalid status. Choose from: {valid_statuses}"}, status=400)

        tasks      = Task.objects.filter(status=stage).select_related('assigned_by', 'assigned_to')
        serializer = TaskListSerializer(tasks, many=True)
        return Response(serializer.data)


# ==============================================================================
# DISCUSSION
# ==============================================================================
@extend_schema(
    tags=['Board'],
    request=inline_serializer(
        name='PostDiscussionRequest',
        fields={
            'message': drf_serializers.CharField(
                help_text='Comment message. Supports @[Full Name](user_id) mention format.'
            ),
        }
    )
)
class DiscussionView(APIView):
    """
    GET  — retrieve all comments on a task.
    POST — post a new comment. Anyone with board access can comment.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['read', 'write', 'update', 'admin']

    def get(self, request, task_id):
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        comments   = Discussion.objects.filter(task=task).select_related('author')
        serializer = DiscussionSerializer(comments, many=True)
        return Response(serializer.data)

    def post(self, request, task_id):
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        message = request.data.get('message', '').strip()
        if not message:
            return Response({"error": "Message cannot be empty."}, status=400)

        comment    = Discussion.objects.create(task=task, author=request.user, message=message)
        serializer = DiscussionSerializer(comment)
        return Response(serializer.data, status=201)


@extend_schema(tags=['Board'])
class DiscussionDeleteView(APIView):
    """DELETE — only the comment author or admin can delete a comment."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area      = 'board'
    required_roles     = ['write', 'update', 'admin']

    def delete(self, request, task_id, comment_id):
        try:
            comment = Discussion.objects.get(id=comment_id, task_id=task_id)
        except Discussion.DoesNotExist:
            return Response({"error": "Comment not found."}, status=404)

        if request.user.role != 'admin' and comment.author != request.user:
            return Response({"error": "You can only delete your own comments."}, status=403)

        comment.delete()
        return Response({"message": "Comment deleted."})