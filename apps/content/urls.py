from django.urls import path
from .views import *

urlpatterns = [
    # 1. Drafting & Editing (Writers)
    path('articles/', ArticleEditView.as_view(), name='create_article'),
    path('articles/<int:pk>/edit/', ArticleEditView.as_view(), name='edit_article'),
    path('articles/<int:pk>/transfer/', TransferFlagView.as_view(), name='transfer_flag'),
    
    # 2. Discovery (Admins/Approvers/Writers)
    path('articles/list/', ArticleListView.as_view(), name='draft_list'),
    #path('articles/<int:pk>/history/', RollbackPreviewView.as_view(), name='article_version_history'),
    ##remove upper 2
    #path('drafts/dashboard/', DraftDashboardView.as_view(), name='draft_dashboard'),
    # path('drafts/<int:pk>/history/', ArticleHistoryView.as_view(), name='draft_history'),
    
    # 3. Review & Voting (Approvers)
    path('articles/<int:pk>/feedback/', SubmitFeedbackView.as_view(), name='submit_feedback'),
    
    # 4. Final Action (Admins Only)
    path('articles/<int:pk>/admin-review/', AdminReviewView.as_view(), name='admin_decision'),
    
    # 5. Output (Everyone/Associates)
    path('published/', PublishedListView.as_view(), name='published_content_list'),

    # 6.flg view - admin
    path('flag/view/', FlagTrackerView.as_view()),
]