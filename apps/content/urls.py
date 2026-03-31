from django.urls import path
from .views import (
    ActiveContentListView, PublishedContentListView,
    ContentDetailView, ContentLock,
    SaveContentView, ReviewerListView, NotifyCandidatesView,
    AssignSMEView, ApproveContent,
    ContentVersionHistory, ContentVersionDetailView, LatestVersionView,
    WriteComment, ContentCommentHistoryView, CommentEditDelete,
)

urlpatterns = [
    # Lists
    path("contents/active/", ActiveContentListView.as_view(),   name="active-contents"),
    path("contents/published/", PublishedContentListView.as_view(), name="published-contents"),

    # Reviewer dropdown
    path("contents/reviewers-list/", ReviewerListView.as_view(), name="reviewers-list"),

    # Unified save
    path("contents/save/", SaveContentView.as_view(), name="content-save"),

    # Detail + Lock
    path("contents/<uuid:content_id>/", ContentDetailView.as_view(), name="content-detail"),
    path("contents/<uuid:content_id>/lock/", ContentLock.as_view(),       name="content-lock"),

    # Notify candidates
    path("contents/<uuid:content_id>/notify-candidates/",
         NotifyCandidatesView.as_view(), name="notify-candidates"),

    # Workflow
    path("contents/<uuid:content_id>/assign-sme/", AssignSMEView.as_view(),  name="assign-sme"),
    path("contents/<uuid:content_id>/approve/", ApproveContent.as_view(), name="content-approve"),

    # Versions
    path("contents/<uuid:content_id>/history/",
         ContentVersionHistory.as_view(), name="content-history"),
    path("contents/<uuid:content_id>/versions/<uuid:version_id>/",
         ContentVersionDetailView.as_view(), name="content-version-detail"),
    path("contents/<uuid:content_id>/latest-version/",
         LatestVersionView.as_view(), name="content-latest-version"),

    # Comments
    path("contents/<uuid:content_id>/comment/",
         WriteComment.as_view(),name="content-comment"),
    path("contents/<uuid:content_id>/comments/history/",
         ContentCommentHistoryView.as_view(), name="content-comments"),
    path("comments/edit/<uuid:comment_id>/",
         CommentEditDelete.as_view(), name="comment-edit"),
]
