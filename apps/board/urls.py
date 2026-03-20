from django.urls import path
from .views import (
    TaskListView, TaskDetailView, TransferTaskView,
    TaskUpdateView, TaskFilterSearchView,
    MyTasksView, TasksByUserView, TasksByStageView,
    DiscussionView, DiscussionDeleteView,
)

urlpatterns = [
    # ── Core task CRUD ────────────────────────────────────────────────────────
    # GET (all tasks, cached) | POST (create + assign)
    path('tasks/',                     TaskListView.as_view(),   name='task_list'),

    # GET (full detail) | PATCH (change status) | DELETE
    path('tasks/<int:task_id>/',       TaskDetailView.as_view(), name='task_detail'),

    # ── New: edit task metadata (tags, priority, marketing_type, due_date) ────
    path('tasks/<int:task_id>/update/', TaskUpdateView.as_view(), name='task_update'),

    # ── New: filter + search ──────────────────────────────────────────────────
    path('tasks/filter/',              TaskFilterSearchView.as_view(), name='task_filter'),

    # ── Transfer ──────────────────────────────────────────────────────────────
    path('tasks/<int:task_id>/transfer/', TransferTaskView.as_view(), name='task_transfer'),

    # ── Filtered views ────────────────────────────────────────────────────────
    path('tasks/mine/',                    MyTasksView.as_view(),       name='my_tasks'),
    path('tasks/user/<int:user_id>/',      TasksByUserView.as_view(),   name='tasks_by_user'),
    path('tasks/stage/<str:stage>/',       TasksByStageView.as_view(),  name='tasks_by_stage'),

    # ── Discussion ────────────────────────────────────────────────────────────
    path('tasks/<int:task_id>/discussion/',                         DiscussionView.as_view(),       name='discussion'),
    path('tasks/<int:task_id>/discussion/<int:comment_id>/delete/', DiscussionDeleteView.as_view(), name='discussion_delete'),
]