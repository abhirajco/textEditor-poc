from django.urls import path
from .views import (
    CampaignListView, CampaignDetailView, CampaignEventsView, CampaignTasksView,CampaignFilterSearchView,
    EventListView, EventDetailView, EventTasksView, EventFilterSearchView,
    TaskListView, TaskDetailView, TaskSubtasksView, TaskUpdateView,
    TransferTaskView, TaskFilterSearchView,
    # MyTasksView, TasksByUserView,
    DiscussionView, DiscussionDeleteView, 
)

urlpatterns = [
    # ── Campaigns ─────────────────────────────────────────────────────────────
    path("campaigns/",CampaignListView.as_view(), name="campaign_list"),
    path("campaigns/<str:campaign_id>/", CampaignDetailView.as_view(), name="campaign_detail"),
    path("campaigns/<str:campaign_id>/events/", CampaignEventsView.as_view(), name="campaign_events"),
    path("campaigns/<str:campaign_id>/tasks/", CampaignTasksView.as_view(),  name="campaign_tasks"),
    path("campaigns/filter/", CampaignFilterSearchView.as_view(), name="campaign-filter-search"),


    # ── Events ────────────────────────────────────────────────────────────────
    path("events/", EventListView.as_view(), name="event_list"),
    path("events/<str:event_id>/", EventDetailView.as_view(), name="event_detail"),
    path("events/<str:event_id>/tasks/", EventTasksView.as_view(),  name="event_tasks"),
    path("events/filter/", EventFilterSearchView.as_view(),  name="event_filter"),

    # ── Tasks ─────────────────────────────────────────────────────────────────
    path("tasks/", TaskListView.as_view(), name="task_list"),
    path("tasks/filter/",   TaskFilterSearchView.as_view(),name="task_filter"),
    # path("tasks/mine/", MyTasksView.as_view(), name="my_tasks"),
    # path("tasks/user/<str:user_id>/", TasksByUserView.as_view(),name="tasks_by_user"),
    path("tasks/<str:task_id>/", TaskDetailView.as_view(), name="task_detail"),
    path("tasks/<str:task_id>/update/", TaskUpdateView.as_view(), name="task_update"),
    path("tasks/<str:task_id>/transfer/", TransferTaskView.as_view(), name="task_transfer"),
    path("tasks/<str:task_id>/subtasks/", TaskSubtasksView.as_view(),name="task_subtasks"),
    path("tasks/<str:task_id>/discussion/", DiscussionView.as_view(),name="discussion"),
    path("tasks/<str:task_id>/discussion/<str:comment_id>/delete/",DiscussionDeleteView.as_view(), name="discussion_delete"),
]
