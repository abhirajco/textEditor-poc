from django.urls import path
from .views import (
    # Lists
#     ActiveContentListView, PublishedContentListView,
#     ContentByStageView,

    # Detail + lock
    ContentDetailView, ContentLock,

    # Workflow
    NewContentButton,
    SaveContentView, InitiateContentView,
    ReviewerListView, NotifyCandidatesView,
    AssignSMEndExeView, ApproveContent,

    # Versions
    ContentVersionHistory, ContentVersionDetailView, LatestVersionView,

    # Comments
    WriteComment, ResolveComment, ContentCommentHistoryView, CommentEditDelete,

    # Dropdowns
#     CampaignListView, EventListView,

    # Analytics
    ContentStatsView, ContentFilterView,

    #list of role
    SMEListView , ExeListView , WriterListView , OnlyReviewerListView,

    FormListView, StartFromForm, ParticularFormView
)

urlpatterns = [


    #LIST od all the roles
    path("contents/sme" , SMEListView.as_view()),
    path("contents/exe" , ExeListView.as_view()),
    path("contents/writer" , WriterListView.as_view()),
    path("contents/reviewer" , OnlyReviewerListView.as_view()),


    # ── Analytics / Stats ─────────────────────────────────────────────────────
    # GET /api/content/contents/stats/
    #   ?campaign_id=X  &author_id=Y
    #   → { draft, in_review, rejected, published, total }
    path("contents/stats/",  ContentStatsView.as_view(),  name="content-stats"),

    # GET /api/content/contents/filter/
    #   ?content_type=blog &status=draft &author_id=UUID
    #   &campaign_id=X &tags=seo,product
    #   &year=2025 &quarter=2   (or &month=4)
    #   &group_by=period
    path("contents/filter/", ContentFilterView.as_view(), name="content-filter"),

    # ── Initiation form (executive) ───────────────────────────────────────────
    # POST /api/content/contents/initiate/
    path("contents/initiate/", InitiateContentView.as_view(), name="content-initiate"),

    #GET /api/content/initiation-forms/
     # GET /api/content/initiation-forms/?sme_id=uuid
     #GET /api/content/initiation-forms/?campaign_id=1
     #GET /api/content/initiation-forms/?created_by=uuid
    path("contents/form/" , FormListView.as_view() , name="form"),

    path("contents/startFromForm/" , StartFromForm.as_view()),

    path("contents/particularForm/<uuid:form_id>" , ParticularFormView.as_view()),
    # ── Dropdown helpers ──────────────────────────────────────────────────────
#     path("campaigns/active/", CampaignListView.as_view(), name="campaigns-active"),
#     path("events/", EventListView.as_view(),    name="events-list"),

    # ── Reviewer dropdown (internal members) ─────────────────────────────────
    path("contents/reviewers-list/", ReviewerListView.as_view(), name="reviewers-list"),

    # ── Unified save ──────────────────────────────────────────────────────────
    # POST /api/content/contents/save/
    #   submit=false → save draft
    #   submit=true  → submit for internal review (status → in_review)
    path("contents/save/", SaveContentView.as_view(), name="content-save"),
       path("contents/new/", NewContentButton.as_view(), name="new-content-button"),
    # ── Detail + Lock ─────────────────────────────────────────────────────────
    path("contents/<uuid:content_id>/",      ContentDetailView.as_view(), name="content-detail"),
    path("contents/<uuid:content_id>/lock/", ContentLock.as_view(),       name="content-lock"),

    # ── Notify candidates ─────────────────────────────────────────────────────
    path("contents/<uuid:content_id>/notify-candidates/",
         NotifyCandidatesView.as_view(), name="notify-candidates"),

    # ── Workflow ──────────────────────────────────────────────────────────────
    path("contents/<uuid:content_id>/assign-sme/", AssignSMEndExeView.as_view(), name="assign-sme"),

    # POST /api/content/contents/<id>/approve/
    #   body: { "action": "approve" | "reject" | "publish", "reason": "..." }
    path("contents/<uuid:content_id>/approve/", ApproveContent.as_view(), name="content-approve"),

    # ── Versions ──────────────────────────────────────────────────────────────
    path("contents/<uuid:content_id>/history/",
         ContentVersionHistory.as_view(), name="content-history"),
    path("contents/<uuid:content_id>/versions/<uuid:version_id>/",
         ContentVersionDetailView.as_view(), name="content-version-detail"),
    path("contents/<uuid:content_id>/latest-version/",
         LatestVersionView.as_view(), name="content-latest-version"),

    # ── Comments ──────────────────────────────────────────────────────────────
    path("contents/<uuid:content_id>/comment/",
         WriteComment.as_view(), name="content-comment"),
    path("contents/<uuid:content_id>/comments/history/",
         ContentCommentHistoryView.as_view(), name="content-comments"),
    path("comments/resolve/<uuid:comment_id>/",
         ResolveComment.as_view(), name="comment-resolve"),
    path("comments/edit/<uuid:comment_id>/",
         CommentEditDelete.as_view(), name="comment-edit"),
]
