from django.urls import path
from .views import (
    CampaignListView, CampaignDetailView, CampaignEventsView, CampaignTasksView,
    EventListView, EventDetailView, EventTasksView,
    TaskListView, TaskDetailView, TaskSubtasksView, TaskUpdateView,
    TransferTaskView, TaskFilterSearchView,
    MyTasksView, TasksByUserView,
    DiscussionView, DiscussionDeleteView,
)

urlpatterns = [
    # ── Campaigns ─────────────────────────────────────────────────────────────
    path("campaigns/",CampaignListView.as_view(), name="campaign_list"),
    path("campaigns/<uuid:campaign_id>/", CampaignDetailView.as_view(), name="campaign_detail"),
    path("campaigns/<uuid:campaign_id>/events/", CampaignEventsView.as_view(), name="campaign_events"),
    path("campaigns/<uuid:campaign_id>/tasks/", CampaignTasksView.as_view(),  name="campaign_tasks"),

    # ── Events ────────────────────────────────────────────────────────────────
    path("events/", EventListView.as_view(), name="event_list"),
    path("events/<uuid:event_id>/", EventDetailView.as_view(), name="event_detail"),
    path("events/<uuid:event_id>/tasks/", EventTasksView.as_view(),  name="event_tasks"),

    # ── Tasks ─────────────────────────────────────────────────────────────────
    path("tasks/", TaskListView.as_view(), name="task_list"),
    path("tasks/filter/",   TaskFilterSearchView.as_view(),name="task_filter"),
    path("tasks/mine/", MyTasksView.as_view(), name="my_tasks"),
    path("tasks/user/<uuid:user_id>/", TasksByUserView.as_view(),name="tasks_by_user"),
    path("tasks/<uuid:task_id>/", TaskDetailView.as_view(), name="task_detail"),
    path("tasks/<uuid:task_id>/update/", TaskUpdateView.as_view(), name="task_update"),
    path("tasks/<uuid:task_id>/transfer/", TransferTaskView.as_view(), name="task_transfer"),
    path("tasks/<uuid:task_id>/subtasks/", TaskSubtasksView.as_view(),name="task_subtasks"),
    path("tasks/<uuid:task_id>/discussion/", DiscussionView.as_view(),name="discussion"),
    path("tasks/<uuid:task_id>/discussion/<uuid:comment_id>/delete/",DiscussionDeleteView.as_view(), name="discussion_delete"),
]
