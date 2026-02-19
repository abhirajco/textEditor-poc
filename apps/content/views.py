from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
# from accounts.permissions import HasRBACPermission
from .models import ArticleDraft, ArticleVersion, PublishedContent
from .serializers import *
from utils.notifications.services import notify_approvers
from accounts.models import User
from utils.permissions.base import HasRBACPermission
from django.core.cache import cache
from django.db import transaction
from datetime import *
import logging
#old one
# class ArticleEditView(APIView):
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_role = "write"

#     def post(self, request):
#         """Initial Create by Writer"""
#         title = request.data.get('title')
#         content = request.data.get('content')
        
#         draft = ArticleDraft.objects.create(
#             title=title,
#             original_author=request.user,
#             flag_holder=request.user # First writer gets the flag
#         )
        
#         # Create Version 1
#         ArticleVersion.objects.create(
#             article=draft,
#             editor=request.user,
#             content_snapshot=content
#         )
        
#         notify_approvers(title, request.user.full_name , "write")
#         return Response({"message": "Draft created and flag assigned.", "draft_id": draft.id}, status=201)

#     def put(self, request, pk):
#         """Edit existing Draft (Requires Flag)"""
#         draft = get_object_or_404(ArticleDraft, pk=pk)
        
#         if draft.flag_holder != request.user:
#             return Response({"error": "You do not hold the flag!"}, status=403)
        
#         content = request.data.get('content')
        
#         # Create a new audit version
#         ArticleVersion.objects.create(
#             article=draft,
#             editor=request.user,
#             content_snapshot=content
#         )
        
#         # Reset status if it was rejected
#         draft.status = 'draft'
#         draft.save()
        
#         notify_approvers(draft.title, request.user.full_name , "edit")
#         return Response({"message": "New version saved and approvers notified."})

#with atomic transaction
class ArticleEditView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_role = "write"

    def post(self, request):
        title = request.data.get('title')
        content = request.data.get('content')
        
        # Start Transaction
        with transaction.atomic():
            draft = ArticleDraft.objects.create(
                title=title,
                original_author=request.user,
                flag_holder=request.user
            )
            
            ArticleVersion.objects.create(
                article=draft,
                editor=request.user,
                content_snapshot=content
            )
        
        # Notify only after successful DB commit
        cache.delete("active_drafts_list")
        notify_approvers(title, request.user.full_name , "write")
        return Response({"message": "Draft created and flag assigned.", "draft_id": draft.id}, status=201)

    def put(self, request, pk):
        content = request.data.get('content')
        
        with transaction.atomic():
            # Use select_for_update to lock the draft row during the edit
            draft = ArticleDraft.objects.select_for_update().get(pk=pk)
            
            if draft.flag_holder != request.user:
                return Response({"error": "You do not hold the flag!"}, status=403)
            
            ArticleVersion.objects.create(
                article=draft,
                editor=request.user,
                content_snapshot=content
            )
            
            draft.status = 'draft'
            draft.save()
        
        notify_approvers(draft.title, request.user.full_name , "edit")
        return Response({"message": "New version saved and approvers notified."})
    
# --- VIEW: FLAG TRANSFER (WRITER) ---
class TransferFlagView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_role = "write"

    def post(self, request, pk):
        draft = get_object_or_404(ArticleDraft, pk=pk)
        if draft.flag_holder != request.user:
            return Response({"error": "Only the current flag holder can transfer it."}, status=403)
        
        new_holder_id = request.data.get('new_holder_id')

        new_holder = get_object_or_404(User, id=new_holder_id, role='writer')
        
        draft.flag_holder = new_holder
        draft.save()
        return Response({"message": f"Flag transferred to {new_holder.full_name}"})

# --- VIEW: FEEDBACK & VOTE (APPROVER) ---
# class SubmitFeedbackView(APIView):
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_role = "feedback"

#     def post(self, request, pk):
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         latest_version = draft.versions.last() # Feedback always goes to latest edit
        
#         vote = request.data.get('vote') # Boolean
#         comment = request.data.get('comment')
        
#         # Append to JSON list
#         feedback_entry = {
#             "approver": request.user.full_name,
#             "comment": comment,
#             "vote": vote
#         }
#         latest_version.approver_comments.append(feedback_entry)
        
#         if vote: latest_version.total_upvotes += 1
#         else: latest_version.total_downvotes += 1
        
#         latest_version.save()
#         return Response({"message": "Feedback recorded on this version."})

#new one
class SubmitFeedbackView(APIView):
    # ... permissions ...
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["feedback", "admin"]

    def post(self, request, pk):
        draft = get_object_or_404(ArticleDraft, pk=pk)
        latest_version = draft.versions.last()
        
        feedback_data = {
            "approver": request.user.full_name,
            "comment": request.data.get('comment'),
            "vote": request.data.get('vote'),
            "timestamp": str(timezone.now())
        }

        # 1. Store in Redis List (Key: reviews_version_123)
        # We use a list so we can store multiple reviews for one version
        redis_key = f"reviews_version_{latest_version.id}"
        
        # Get existing reviews, append new one, and save back
        reviews = cache.get(redis_key) or []
        reviews.append(feedback_data)
        cache.set(redis_key, reviews, timeout=3600) # Cache for 1 hour

        # 2. Also save to Postgres (The permanent "Cold Storage")
        latest_version.approver_comments.append(feedback_data)
        latest_version.save()

        return Response({"message": "Feedback stored in live cache."})
# --- VIEW: PUBLISH/REJECT (ADMIN) ---

#new - with atmoc transcation
class AdminReviewView(APIView):

    #changing this also
    # permission_classes = [permissions.IsAuthenticated] 
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_role = "admin"

    def post(self, request, pk):
        # if request.user.role != 'admin':
        #     return Response({"error": "Admin only"}, status=403)
            
        try:

            action = request.data.get('action') 
        
            with transaction.atomic():
            # Lock the draft so no writer can 'Transfer' or 'Edit' while we review
                draft = ArticleDraft.objects.select_for_update().get(pk=pk)
                print(draft)
                if action == 'publish':
                    latest = draft.versions.last()
                    PublishedContent.objects.create(
                        draft_reference=draft,
                        title=draft.title,
                        final_content=latest.content_snapshot,
                        original_author=draft.original_author,
                        last_editor=latest.editor
                    )
                    draft.status = 'published'
                    draft.save()
                
                # We set a flag to clear cache AFTER the block
                    should_clear_cache = True
                
                elif action == 'reject':
                    draft.status = 'rejected'
                    draft.save()
                    should_clear_cache = False

        # Cache invalidation happens outside the atomic block
                if action == 'publish' and should_clear_cache:
                    cache.delete("published_articles_list")
                    print("--- DEBUG: Published List Cache Cleared ---")

                return Response({"message": f"Action {action} completed successfully."})

        except Exception as e:
            return Response({"Error": str(e)})

#lit bit old - new 
# class AdminReviewView(APIView):
#     permission_classes = [permissions.IsAuthenticated] 

#     def post(self, request, pk):
#         if request.user.role != 'admin':
#             return Response({"error": "Admin only"}, status=403)
            
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         action = request.data.get('action') 
        
#         if action == 'publish':
#             latest = draft.versions.last()
#             PublishedContent.objects.create(
#                 draft_reference=draft,
#                 title=draft.title,
#                 final_content=latest.content_snapshot,
#                 original_author=draft.original_author,
#                 last_editor=latest.editor
#             )
#             draft.status = 'published'
#             draft.save()

#             # --- THE CACHE CHANGE ---
#             # Delete the cache so the PublishedListView updates immediately
#             cache.delete("published_articles_list")
#             print("--- DEBUG: Published List Cache Cleared ---")
#             # -----------------------

#             return Response({"message": "Content is now public!"})
            
#         elif action == 'reject':
#             draft.status = 'rejected'
#             draft.save()
#             return Response({"message": "Draft rejected. Writer must edit again."})
        


#old
# class AdminReviewView(APIView):
#     permission_classes = [permissions.IsAuthenticated] # We verify Admin role in code

#     def post(self, request, pk):
#         if request.user.role != 'admin':
#             return Response({"error": "Admin only"}, status=403)
            
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         action = request.data.get('action') # 'publish' or 'reject'
        
#         if action == 'publish':
#             latest = draft.versions.last()
#             PublishedContent.objects.create(
#                 draft_reference=draft,
#                 title=draft.title,
#                 final_content=latest.content_snapshot,
#                 original_author=draft.original_author,
#                 last_editor=latest.editor
#             )
#             draft.status = 'published'
#             draft.save()
#             return Response({"message": "Content is now public!"})
            
#         elif action == 'reject':
#             draft.status = 'rejected'
#             draft.save()
#             return Response({"message": "Draft rejected. Writer must edit again."})
        

#using redis for chaching
class PublishedListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "admin"]

    def get(self, request):

        print(request.user.role)
        try:
            cache_key = "published_articles_list"
        
        # 1. Try to fetch from Redis
            cached_data = cache.get(cache_key)
        
            if cached_data:
            # If found, return immediately!
                print("--- DEBUG: Serving Published List from Redis ---")
                return Response(cached_data)

        # 2. If not found, Query Postgres
            print("--- DEBUG: Cache Miss. Querying Postgres ---")
            content = PublishedContent.objects.all().order_by('-published_at')
            serializer = PublishedContentSerializer(content, many=True)
            data = serializer.data

        # 3. Save to Redis for 15 minutes (900 seconds)
            cache.set(cache_key, data, timeout=900)

            return Response(data)
        
        except Exception as e:
            return Response({"error": str(e)})
    

###old one 
# class PublishedListView(APIView):
#     """
#     View for Associates and other staff to read officially published content.
#     """
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_role = "read"

#     def get(self, request):
#         content = PublishedContent.objects.all().order_by('-published_at')
#         serializer = PublishedContentSerializer(content, many=True)
#         return Response(serializer.data)


### remove the below 2
##shows history according to draft id:
# class RollbackPreviewView(APIView):
#     """
#     Admin/Writer view to see the full version history for audit or rollback.
#     """
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_roles = ["read", "admin"]

#     def get(self, request, pk):
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         serializer = ArticleDraftSerializer(draft)
#         return Response(serializer.data)
    

# class ArticleListView(APIView):

#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_roles = ["read", "admin"]
    
#     def get(self, request):
#         user = request.user
        
#         # 1. Admins and Approvers see EVERYTHING (latest state)
#         if user.role in ['admin', 'approver']:
#             drafts = ArticleDraft.objects.all().order_by('-created_at')
        
#         # 2. Writers see drafts they created OR drafts where they hold the flag
#         elif user.role == 'writer':
#             from django.db.models import Q
#             drafts = ArticleDraft.objects.filter(
#                 Q(original_author=user) | Q(flag_holder=user)
#             ).distinct().order_by('-created_at')
        
#         else:
#             return Response({"detail": "Not authorized to view drafts."}, status=403)

#         serializer = ArticleDraftSerializer(drafts, many=True)
#         return Response(serializer.data)
    
#with redis one
class ArticleListView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    # Allow all three roles to access this view
    required_roles = ["feedback", "admin", "write"] 

    def get(self, request):
        # Since everyone sees the same thing, one key for everyone
        cache_key = "active_drafts_list"

        try:
            # 1. Try to fetch from Redis
            cached_data = cache.get(cache_key)
            if cached_data:
                print("--- DEBUG: Serving Shared Draft List from Redis ---")
                return Response(cached_data)

            # 2. Cache Miss - Query Postgres
            print("--- DEBUG: Cache Miss. Querying Postgres for Drafts/Rejected ---")
            
            # Filter: only show 'draft' or 'rejected'. Exclude 'published'.
            # We use __in to catch both statuses in one query
            drafts = ArticleDraft.objects.filter(
                status__in=['draft', 'rejected']
            ).order_by('-created_at')

            serializer = ArticleDraftSerializer(drafts, many=True)
            data = serializer.data
            
            # 3. Save to Redis (900 seconds = 15 minutes)
            cache.set(cache_key, data, timeout=900)

            return Response(data)

        except Exception as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

#leave for now
# class DraftDashboardView(APIView):
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_roles = ["read", "admin"]

#     def get(self, request):
#         try:
#             user = request.user
        
#             if user.role in ['admin', 'approver']:
#             # Admins/Approvers see everything
#                 drafts = ArticleDraft.objects.all().order_by('-created_at')
#             else:
#             # Writers only see where they are the Author OR the Flag Holder
#                 from django.db.models import Q
#                 drafts = ArticleDraft.objects.filter(
#                     Q(original_author=user) | Q(flag_holder=user)
#                 ).distinct().order_by('-created_at')

#                 serializer = DraftDashboardSerializer(drafts, many=True)
#                 return Response(serializer.data)
#         except Exception as e:
#             # return Response({str(e)})
#             # logger.error(f"Error in DraftDashboardView: {str(e)}")
            
#             # Return a clean error message to the user
#             return Response(
#                 {"error": str(e)}, 
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
    

# class ArticleHistoryView(APIView):

#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_role = ["read", "admin"]

#     def get(self, request, version_id):
#         redis_key = f"reviews_version_{version_id}"
        
#         # 1. Try to get reviews from Redis
#         reviews = cache.get(redis_key)
        
#         if reviews:
#             print("--- DEBUG: Serving Reviews from Redis ---")
#             return Response(reviews)

#         # 2. Fallback: If Redis expired, get from Postgres
#         print("--- DEBUG: Cache Miss. Pulling from Postgres ---")
#         version = get_object_or_404(ArticleVersion, id=version_id)
#         reviews = version.approver_comments
        
#         # 3. Re-fill the cache for the next person
#         cache.set(redis_key, reviews, timeout=3600)

#         return Response(reviews)
#     # permission_classes = [HasRBACPermission]
#     # required_area = "content"
#     # required_role = "read"

#     # def get(self, request, pk):
#     #     draft = get_object_or_404(ArticleDraft, pk=pk)
#     #     user = request.user

#     #     # STRICT PERMISSION CHECK
#     #     is_owner = (draft.original_author == user)
#     #     is_flag_holder = (draft.flag_holder == user)
#     #     is_staff = (user.role in ['admin', 'approver'])
#     #     # print(is_owner or is_flag_holder or is_staff)
#     #     print(is_staff)
#     #     if not (is_owner or is_flag_holder or is_staff):
#     #         return Response({"error": "You do not have permission to view this history."}, status=403)

#     #     serializer = ArticleDraftSerializer(draft)
#     #     return Response(serializer.data)
    


class FlagTrackerView(APIView):
    permission_classes = [HasRBACPermission] # Use your new IsAdmin class
    required_area = "content"
    required_roles = ["admin", "feedback"]

    def get(self, request):
        # We only want drafts that are still in progress (not published)
        active_drafts = ArticleDraft.objects.exclude(status='published').select_related('flag_holder', 'original_author')
        
        data = []
        for draft in active_drafts:
            data.append({
                "draft_id": draft.id,
                "title": draft.title,
                "status": draft.status,
                "original_author": draft.original_author.full_name,
                "current_flag_holder": draft.flag_holder.full_name if draft.flag_holder else "None",
                "last_updated": draft.created_at # Or use version timestamp
            })
            
        return Response(data)















# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status
# from django.shortcuts import get_object_or_404
# from django.db.models import Q

# # NEW PERMISSION IMPORTS
# from utils.permissions.rbac import CanRead, CanWrite, CanFeedback, IsAdmin
# from .models import ArticleDraft, ArticleVersion, PublishedContent
# from .serializers import (
#     ArticleDraftSerializer, 
#     DraftDashboardSerializer, 
#     PublishedContentSerializer
# )
# from utils.notifications.services import notify_approvers
# from accounts.models import User

# # --- VIEW: CREATE/EDIT DRAFTS (WRITER) ---
# class ArticleEditView(APIView):
#     permission_classes = [CanWrite]
#     rbac_area = "content"

#     def post(self, request):
#         """Initial Create by Writer"""
#         title = request.data.get('title')
#         content = request.data.get('content')
        
#         draft = ArticleDraft.objects.create(
#             title=title,
#             original_author=request.user,
#             flag_holder=request.user
#         )
        
#         ArticleVersion.objects.create(
#             article=draft,
#             editor=request.user,
#             content_snapshot=content
#         )
        
#         notify_approvers(title, request.user.full_name, "write")
#         return Response({"message": "Draft created and flag assigned.", "draft_id": draft.id}, status=201)

#     def put(self, request, pk):
#         """Edit existing Draft (Requires Flag)"""
#         draft = get_object_or_404(ArticleDraft, pk=pk)
        
#         # Business Logic Check: Only Flag Holder can edit
#         if draft.flag_holder != request.user:
#             return Response({"error": "You do not hold the flag!"}, status=403)
        
#         content = request.data.get('content')
#         ArticleVersion.objects.create(
#             article=draft,
#             editor=request.user,
#             content_snapshot=content
#         )
        
#         draft.status = 'draft'
#         draft.save()
        
#         notify_approvers(draft.title, request.user.full_name, "edit")
#         return Response({"message": "New version saved."})

# # --- VIEW: FLAG TRANSFER (WRITER) ---
# class TransferFlagView(APIView):
#     permission_classes = [CanWrite]
#     rbac_area = "content"

#     def post(self, request, pk):
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         if draft.flag_holder != request.user:
#             return Response({"error": "Only the current flag holder can transfer it."}, status=403)
        
#         new_holder_id = request.data.get('new_holder_id')
#         new_holder = get_object_or_404(User, id=new_holder_id, role='writer')
        
#         draft.flag_holder = new_holder
#         draft.save()
#         return Response({"message": f"Flag transferred to {new_holder.full_name}"})

# # --- VIEW: FEEDBACK & VOTE (APPROVER) ---
# class SubmitFeedbackView(APIView):
#     permission_classes = [CanFeedback]
#     rbac_area = "content"

#     def post(self, request, pk):
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         latest_version = draft.versions.last()
        
#         vote = request.data.get('vote')
#         comment = request.data.get('comment')
        
#         feedback_entry = {
#             "approver": request.user.full_name,
#             "comment": comment,
#             "vote": vote
#         }
#         latest_version.approver_comments.append(feedback_entry)
        
#         if vote: latest_version.total_upvotes += 1
#         else: latest_version.total_downvotes += 1
        
#         latest_version.save()
#         return Response({"message": "Feedback recorded."})

# # --- VIEW: PUBLISH/REJECT (ADMIN) ---
# class AdminReviewView(APIView):
#     permission_classes = [IsAdmin]
#     rbac_area = "content"

#     def post(self, request, pk):
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         action = request.data.get('action') 
        
#         if action == 'publish':
#             latest = draft.versions.last()
#             PublishedContent.objects.create(
#                 draft_reference=draft,
#                 title=draft.title,
#                 final_content=latest.content_snapshot,
#                 original_author=draft.original_author,
#                 last_editor=latest.editor
#             )
#             draft.status = 'published'
#             draft.save()
#             return Response({"message": "Content published!"})
            
#         elif action == 'reject':
#             draft.status = 'rejected'
#             draft.save()
#             return Response({"message": "Draft rejected."})

# # --- VIEW: DASHBOARD (LATEST VERSIONS) ---
# class DraftDashboardView(APIView):
#     permission_classes = [CanRead]
#     rbac_area = "content"

#     def get(self, request):
#         user = request.user
#         if user.role in ['admin', 'approver']:
#             drafts = ArticleDraft.objects.all().order_by('-created_at')
#         else:
#             drafts = ArticleDraft.objects.filter(
#                 Q(original_author=user) | Q(flag_holder=user)
#             ).distinct().order_by('-created_at')

#         serializer = DraftDashboardSerializer(drafts, many=True)
#         return Response(serializer.data)

# # --- VIEW: HISTORY (FULL AUDIT) ---
# class ArticleHistoryView(APIView):
#     permission_classes = [CanRead]
#     rbac_area = "content"

#     def get(self, request, pk):
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         user = request.user

#         is_owner = (draft.original_author == user)
#         is_flag_holder = (draft.flag_holder == user)
#         is_staff = (user.role in ['admin', 'approver'])

#         if not (is_owner or is_flag_holder or is_staff):
#             return Response({"error": "No permission to view history."}, status=403)

#         serializer = ArticleDraftSerializer(draft)
#         return Response(serializer.data)

# # --- VIEW: PUBLISHED LIST (ASSOCIATES) ---
# class PublishedListView(APIView):
#     permission_classes = [CanRead]
#     rbac_area = "content"

#     def get(self, request):
#         content = PublishedContent.objects.all().order_by('-published_at')
#         serializer = PublishedContentSerializer(content, many=True)
#         return Response(serializer.data)