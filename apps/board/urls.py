from django.urls import path
from .views import (
    TaskListView, TaskDetailView, TransferTaskView,
    MyTasksView, TasksByUserView, TasksByStageView,
    DiscussionView, DiscussionDeleteView,
)

urlpatterns = [
   
    # GET  (all tasks, Redis-cached) | POST (create + assign)
    path('tasks/', TaskListView.as_view(), name='task_list'),

    # GET (full detail) | PATCH (change stage) | DELETE
    path('tasks/<int:task_id>/', TaskDetailView.as_view(), name='task_detail'),

    # POST { "transfer_to": <user_id> }  — current assignee transfers task
    path('tasks/<int:task_id>/transfer/', TransferTaskView.as_view(), name='task_transfer'),

    # GET — tasks assigned to the logged-in user
    path('tasks/mine/', MyTasksView.as_view(), name='my_tasks'),

    # GET — tasks assigned to any specific user
    path('tasks/user/<int:user_id>/', TasksByUserView.as_view(),name='tasks_by_user'),

    # GET — tasks filtered by stage (to_do | in_progress | completed)
    path('tasks/stage/<str:stage>/', TasksByStageView.as_view(), name='tasks_by_stage'),

    # GET (all comments) | POST (add comment)
    path('tasks/<int:task_id>/discussion/',                         DiscussionView.as_view(),       name='discussion'),

    # DELETE a specific comment
    path('tasks/<int:task_id>/discussion/<int:comment_id>/delete/', DiscussionDeleteView.as_view(), name='discussion_delete'),
]
