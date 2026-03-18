import json
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

TASK_LIST_CACHE_KEY = "kanban_all_tasks"
CACHE_TTL = 60 * 5  # 5 minutes


def _bust_task_cache():
    """Invalidate the task list cache whenever data changes."""
    cache.delete(TASK_LIST_CACHE_KEY)



class TaskListView(APIView):

    #GET  — list all tasks (everyone can see everyone's tasks). results are cached in Redis for 5 minutes.
    #POST — create a new task and assign it to any user nyone with board access can do this.

    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = 'board'
    required_roles = ['read', 'write', 'update', 'admin']

    def get(self, request):
        # Try Redis first
        cached = cache.get(TASK_LIST_CACHE_KEY)
        if cached:
            return Response(json.loads(cached))

        tasks= Task.objects.select_related('assigned_by', 'assigned_to', 'last_transferred_by').all()
        serializer = TaskListSerializer(tasks, many=True)
        data= serializer.data

        # Store in Redis
        cache.set(TASK_LIST_CACHE_KEY, json.dumps(data), CACHE_TTL)
        return Response(data)

    def post(self, request):
        title= request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()
        assigned_to_id = request.data.get('assigned_to')

        if not title:
            return Response({"error": "Title is required."}, status=400)
        if not assigned_to_id:
            return Response({"error": "assigned_to (user id) is required."}, status=400)

        try:
            assignee = User.objects.get(id=assigned_to_id)
        except User.DoesNotExist:
            return Response({"error": "Assigned user not found."}, status=404)

        with transaction.atomic():
            task = Task.objects.create(
                title= title,
                description= description,
                assigned_by= request.user,
                assigned_to= assignee,
                stage= 'to_do',
            )
            TaskHistory.objects.create(
                task= task,
                action= 'created',
                performed_by= request.user,
                detail= f"Task created and assigned to {assignee.full_name} ({assignee.email})",
            )

        _bust_task_cache()

        # Email notification
        send_task_assignment_email(
            assignee_email= assignee.email,
            assignee_name= assignee.full_name,
            task_title= task.title,
            assigned_by_name= request.user.full_name,
        )

        return Response(TaskSerializer(task).data, status=201)


class TaskDetailView(APIView):
    """
    GET — full task detail including discussion and history.
    PATCH  — update stage only (to_do / in_progress / completed).
             Only the current assignee can change the stage.
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

    def patch(self, request, task_id):
        """Change the stage. Only the current assignee (or admin) can do this."""
        task = self._get_task(task_id)
        if not task:
            return Response({"error": "Task not found."}, status=404)

        if request.user.role != 'admin' and task.assigned_to != request.user:
            return Response(
                {"error": "Only the current assignee can update the task stage."},
                status=403
            )

        new_stage = request.data.get('stage', '').strip()
        valid_stages = [s[0] for s in Task.STAGE_CHOICES]

        if new_stage not in valid_stages:
            return Response(
                {"error": f"Invalid stage. Choose from: {valid_stages}"},
                status=400
            )

        old_stage= task.stage
        task.stage= new_stage
        task.save()

        TaskHistory.objects.create(
            task= task,
            action= 'stage_changed',
            performed_by= request.user,
            detail= f"Stage changed from '{old_stage}' to '{new_stage}'",
        )

        _bust_task_cache()
        return Response(TaskSerializer(task).data)

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


class TransferTaskView(APIView):
    """
    POST /api/board/tasks/<task_id>/transfer/ 
    Body: { "transfer_to": <user_id> }

    The current assignee (or admin) can transfer the task to any other user.
    Records the transfer in TaskHistory and updates last_transferred_by.
    """
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = 'board'
    required_roles = ['write', 'update', 'admin']

    def post(self, request, task_id):
        try:
            task = Task.objects.select_related('assigned_to', 'assigned_by').get(id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        # Only the current assignee or admin can transfer
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
            task.last_transferred_by= request.user
            task.assigned_to= new_assignee
            task.save()

            TaskHistory.objects.create(
                task= task,
                action= 'transferred',
                performed_by= request.user,
                detail=(
                    f"Transferred from {old_assignee.full_name} ({old_assignee.email}) "
                    f"to {new_assignee.full_name} ({new_assignee.email})"
                ),
            )

        _bust_task_cache()

        # Email new assignee
        send_task_transfer_email(
            new_assignee_email= new_assignee.email,
            new_assignee_name= new_assignee.full_name,
            task_title= task.title,
            transferred_by_name= request.user.full_name,
        )

        return Response({
            "message": f"Task transferred to {new_assignee.full_name}.",
            "task": TaskSerializer(task).data,
        })


# ==============================================================================
# FILTERED VIEWS
# ==============================================================================

class MyTasksView(APIView):
    """GET — returns only tasks currently assigned to the logged-in user."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = 'board'
    required_roles = ['read', 'write', 'update', 'admin']

    def get(self, request):
        tasks = Task.objects.filter(assigned_to=request.user).select_related('assigned_by', 'assigned_to')
        serializer= TaskListSerializer(tasks, many=True)
        return Response(serializer.data)


class TasksByUserView(APIView):
    """
    GET /api/board/tasks/user/<user_id>/
    Returns all tasks currently assigned to any given user.
    Anyone can view anyone else's tasks.
    """
    permission_classes= [permissions.IsAuthenticated, HasRBACPermission]
    required_area = 'board'
    required_roles = ['read', 'write', 'update', 'admin']

    def get(self, request, user_id):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)

        tasks = Task.objects.filter(assigned_to=target_user).select_related('assigned_by', 'assigned_to')
        serializer = TaskListSerializer(tasks, many=True)
        return Response({
            "user":  {"id": target_user.id, "full_name": target_user.full_name, "email": target_user.email},
            "tasks": serializer.data,
        })


class TasksByStageView(APIView):
    """
    GET /api/board/tasks/stage/<stage>/
    stage must be: to_do | in_progress | completed
    """
    permission_classes= [permissions.IsAuthenticated, HasRBACPermission]
    required_area = 'board'
    required_roles = ['read', 'write', 'update', 'admin']

    def get(self, request, stage):
        valid_stages = [s[0] for s in Task.STAGE_CHOICES]
        if stage not in valid_stages:
            return Response({"error": f"Invalid stage. Choose from: {valid_stages}"}, status=400)

        tasks = Task.objects.filter(stage=stage).select_related('assigned_by', 'assigned_to')
        serializer = TaskListSerializer(tasks, many=True)
        return Response(serializer.data)


# DISCUSSION VIEWS

class DiscussionView(APIView):
    """
    GET  — retrieve all comments on a task.
    POST — post a new comment on a task. Anyone can comment.
    """
    permission_classes= [permissions.IsAuthenticated, HasRBACPermission]
    required_area  = 'board'
    required_roles = ['read', 'write', 'update', 'admin']

    def get(self, request, task_id):
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=404)

        comments= Discussion.objects.filter(task=task).select_related('author')
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

        comment = Discussion.objects.create(task=task, author=request.user, message=message)
        serializer = DiscussionSerializer(comment)
        return Response(serializer.data, status=201)


class DiscussionDeleteView(APIView):
    """DELETE — only the comment author or admin can delete a comment."""
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    required_area = 'board'
    required_roles = ['write', 'update', 'admin']

    def delete(self, request, task_id, comment_id):
        try:
            comment = Discussion.objects.get(id=comment_id, task_id=task_id)
        except Discussion.DoesNotExist:
            return Response({"error": "Comment not found."}, status=404)

        if request.user.role != 'admin' and comment.author != request.user:
            return Response({"error": "You can only delete your own comments."}, status=403)

        comment.delete()
        return Response({"message": "Comment deleted."})
