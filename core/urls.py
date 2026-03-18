from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Accounts — shared auth + user management for both Insight and Kanban
    path('api/accounts/', include('accounts.urls')),

    # Insight — content management (articles, versions, approvals, comments)
    path('api/content/', include('content.urls')),

    # Kanban — task board (tasks, transfer, discussion)
    path('api/board/', include('board.urls')),
]
