from django.urls import path
from .views import (
    ActiveArticleListView, PublishedArticleListView, ArticleCreate,
    ArticleDetailView, ArticleLock, ArticleEdit, AssignSMEView,
    WriteComment, ApproveArticle, ArticleVersionHistory, ArticleCommentHistoryView
)

urlpatterns = [
    # Lists
    path('articles/active/', ActiveArticleListView.as_view(), name='active-articles'),
    path('articles/published/', PublishedArticleListView.as_view(), name='published-articles'),

    # Creation & Details
    path('articles/create/', ArticleCreate.as_view(), name='article-create'),
    path('articles/<int:pk>/', ArticleDetailView.as_view(), name='article-detail'),

    # Concurrency & Editing
    path('articles/<int:pk>/lock/', ArticleLock.as_view(), name='article-lock'),
    path('articles/<int:pk>/edit/', ArticleEdit.as_view(), name='article-edit'),
    path('articles/<int:pk>/history/', ArticleVersionHistory.as_view(), name='article-history'),

    # Workflow Actions
    path('articles/<int:pk>/assign-sme/', AssignSMEView.as_view(), name='assign-sme'),
    path('articles/<int:pk>/comment/', WriteComment.as_view(), name='article-comment'),
    path('articles/<int:pk>/approve/', ApproveArticle.as_view(), name='article-approve'),

    #cooment
    path('articles/<int:pk>/comments/', ArticleCommentHistoryView.as_view(), name='article-comments'),
]
