from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Article, ArticleAssignment, ArticleComment, ArticleVersion
from accounts.models import User
from utils.notifications.services import handle_mentions_and_notifications, send_approval_emails, send_assigned_sme_emails
from .serializers import ArticleSerializer
# Custom RBAC Import
from utils.permissions.base import HasRBACPermission 
from django.db.models import OuterRef, Subquery

# --- 1. LIST VIEWS ---

class ActiveArticleListView(APIView):
    """Returns drafts, pending_executive, and pending_admin."""
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "feedback", "admin"]

    def get(self, request):
        articles = Article.objects.exclude(status='published').order_by('-updated_at')
        serializer = ArticleSerializer(articles, many=True)
        return Response(serializer.data)

#2
class PublishedArticleListView(APIView):
    """Returns ONLY published articles."""
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "feedback", "admin"]

    def get(self, request):
        articles = Article.objects.filter(status='published').order_by('-updated_at')
        serializer = ArticleSerializer(articles, many=True)
        return Response(serializer.data)


# --- 3. WORKFLOW & ACTIONS ---
class WriteComment(APIView):
    """Add feedback, trigger @mention emails, and handle Kick-Backs to Draft."""
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["feedback", "admin"]

    def post(self, request, pk):
        text = request.data.get('comment_text')
        
        try:
            with transaction.atomic():
                article = Article.objects.select_for_update().get(pk=pk)
                
                if request.user.role == 'sme':
                    if not ArticleAssignment.objects.filter(article=article, sme=request.user).exists():
                        return Response({"error": "Not assigned to this article."}, status=403)

                # EXPLICIT BUSINESS LOGIC: If Exec or Admin comments, it kicks back to Draft
                # if request.user.role in ['executive', 'admin']:
                article.status = 'draft'
                article.locked_by = None # Unlock it so writers can fix it
                article.save()

                # Create the actual comment
                latest_version = ArticleVersion.objects.filter(article=article).order_by('-created_at').first()

                ArticleComment.objects.create(
                    article=article,
                    user=request.user,
                    comment_text=text,
                    version=latest_version # Link it here
                )
                
                # Process Mentions (Now sends emails)
                handle_mentions_and_notifications(text, article, sender=request.user)
                
                return Response({
                    "message": "Feedback recorded.", 
                    "new_article_status": article.status
                })
                
        except Article.DoesNotExist:
            return Response({"error": "Article not found."}, status=404)

#4
class ArticleCreate(APIView):
    # ... permissions and area same as before ...

    def post(self, request):
        title = request.data.get('title')
        content = request.data.get('content')

        try:
            with transaction.atomic():
                article = Article.objects.create(
                    title=title,
                    content=content,
                    author=request.user,
                    status='draft'
                )

                # Notify ALL Reviewers that a new draft needs an SME assigned
                send_approval_emails('reviewer', article)

                return Response({"id": article.id, "message": "Draft created. Reviewers notified for assignment."}, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


#5 - when a version is clicked then all the details will be shown
class ArticleDetailView(APIView):
    """Anyone with content access can view an article."""
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "feedback", "admin"] 

    def get(self, request, pk):
        try:
            article = Article.objects.get(pk=pk)
            is_locked = article.locked_by is not None and article.locked_by != request.user
            
            return Response({
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "status": article.status,
                "author": article.author.full_name,
                "locked_by": article.locked_by.full_name if article.locked_by else None,
                "is_locked": is_locked
            })
        except Article.DoesNotExist:
            return Response({"error": "Article not found"}, status=404)

#6
class ArticleLock(APIView):
   
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["write", "feedback"] # Writers and Reviewers/SMEs can lock

    def post(self, request, pk):
        with transaction.atomic():
           try:
                article = Article.objects.select_for_update().get(pk=pk)

                if request.user.role == 'sme':
                    if not ArticleAssignment.objects.filter(article=article, sme=request.user).exists():
                        return Response({"error": "You are not assigned to this article."}, status=403)
            
                if article.locked_by and article.locked_by != request.user:
                    return Response({"error": f"Currently locked by {article.locked_by.full_name}"}, status=423)
            
                article.locked_by = request.user
                article.locked_at = timezone.now()
                article.save()
                return Response({"message": "Lock acquired. You can now edit."})
           
           except Exception as e:
               return Response({"error": str(e)}, status=400)

    def delete(self, request, pk):
        try:
            article = Article.objects.get(pk=pk)
            if article.locked_by == request.user:
                article.locked_by = None
                article.locked_at = None
                article.save()
                return Response({"message": "Lock released."})
            return Response({"error": "You do not hold the lock."}, status=403)
        except Exception as e:
            return Response({"error": str(e)} , status=400)


#7
class AssignSMEView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["feedback"] 

    def post(self, request, pk):
        sme_id = request.data.get('sme_id')
        try:
            with transaction.atomic():
                article = Article.objects.select_for_update().get(pk=pk)
                sme = User.objects.get(id=sme_id, role='sme')
                
                assignment, created = ArticleAssignment.objects.get_or_create(
                    article=article,
                    sme=sme,
                    defaults={'assigned_by': request.user}
                )
                
                if created:
                    # Notify ONLY this specific SME now that they are assigned
                    send_assigned_sme_emails(article) 
                    return Response({"message": f"Successfully assigned {sme.full_name} to {article.title}."})
                
                return Response({"error": "SME is already assigned."}, status=400)
                
        # except User.DoesNotExist:
        #     return Response({"error": "Invalid SME ID."}, status=404)
        
        except Exception as e:
            return Response({"error": str(e)}, status=400)

#8
class ApproveArticle(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["feedback", "admin" , "promote"]

    def post(self, request, pk):
        try:
            with transaction.atomic():
                article = Article.objects.select_for_update().get(pk=pk)
                user = request.user
                user_role = user.role


                # STEP 1: Technical Approval (Reviewer or APPOINTED SME)
                if article.status == 'draft':
                    if user_role == 'reviewer':
                        pass # Reviewers can approve any draft
                    elif user_role == 'sme':
                        # CHECK: Is this specific SME assigned?
                        is_assigned = ArticleAssignment.objects.filter(
                            article=article, 
                            sme=user
                        ).exists()
                        
                        if not is_assigned:
                            return Response({
                                "error": "Approval denied. You are not the appointed SME for this article."
                            }, status=403)
                    else:
                        return Response({"error": "Only Reviewers or assigned SMEs can perform technical approval."}, status=403)

                    # If checks pass, proceed to move status
                    article.status = 'pending_executive'
                    article.save()
                    send_approval_emails('exec_approver', article)
                    return Response({"message": "Technical approval complete. Sent to Executives."})

                # STEP 2: Executive approves
                elif user_role == 'exec_approver' and article.status == 'pending_executive':
                    article.status = 'pending_admin'
                    article.save()
                    send_approval_emails('admin', article)
                    return Response({"message": "Executive approval complete. Sent to Admins."})

                # STEP 3: Admin approves (Final)
                elif user_role == 'admin' and article.status == 'pending_admin':
                    article.status = 'published'
                    article.save()
                    return Response({"message": "Article has been Published!"})

                return Response({"error": "Invalid approval stage or insufficient permissions."}, status=403)

        # except Article.DoesNotExist:
        #     return Response({"error": "Article not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=400)
#9
class ArticleEdit(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["update", "write"] 

    def put(self, request, pk):
        content = request.data.get('content')
        if not content:
            return Response({"error": "Content is required."}, status=400)

        try:
            with transaction.atomic():
                # Lock the article for the duration of the save
                article = Article.objects.select_for_update().get(pk=pk)
                user = request.user

                #print(article , user)

                # 1. DEFINE AUTHORIZED USERS
                #can remove 2 if , just chekc is locked....bypass securtity but faster resposne
                is_author = (article.author == user)
                is_reviewer = (user.role == 'reviewer')
                is_assigned_sme = (
                    user.role == 'sme' and 
                    ArticleAssignment.objects.filter(article=article, sme=user).exists()
                )

                # 2. CHECK AUTHORIZATION (Admin is intentionally excluded here)
                if not (is_author or is_reviewer or is_assigned_sme):
                    return Response({
                        "error": "Access Denied. Only the Author, Reviewer, or Assigned SME can edit content."
                    }, status=403)

                # 3. CHECK LOCK STATUS
                #yaha code fata hh, frontend se manage ho skta hh
                #agar article lock ni hh, to full_name kabhi access ni hone payega error throw hoga
                #frontend me edit button pe hi locking system lga skte hh
                #ya hm hi thk kr dete hh

                #print(type(article.locked_by))

                if article.locked_by is None:
                    return Response ({"error": "Article is not locked. You must acquire the lock before editing."}, status=423)

    #             if not article.locked_by:
    # return Response({
    #     "error": "Article is not locked. You must acquire the lock before editing."
    # }, status=423)
                if article.locked_by != user:
                    return Response({
                        "error": f"Article is locked by {article.locked_by.full_name}. You must hold the lock to edit."
                    }, status=423)

                # 4. SAVE AUDIT VERSION
                ArticleVersion.objects.create(
                    article=article,
                    content=content,
                    changed_by=user
                )

                # 5. COMMIT CHANGES
                article.locked_by = None
                article.locked_at = None
                article.content = content
                article.updated_at = timezone.now()
                article.save()

                return Response({"message": "Content updated successfully."})

        # except Article.DoesNotExist:
        #     return Response({"error": "Article not found."}, status=404)

        except Exception as e:
            return Response({"error": str(e)} ,status=500)


#10
class ArticleVersionHistory(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read" , "feedback" , "admin" , "promote"]

    def get(self, request, pk):
        try:
            article = Article.objects.get(pk=pk)
            user = request.user

            # Authorization Check: Author, Reviewer, Admin, or Assigned SME
            is_assigned_sme = (
                user.role == 'sme' and 
                ArticleAssignment.objects.filter(article=article, sme=user).exists()
            )
            
            # if not (article.author == user or user.role in ['reviewer', 'admin'] or is_assigned_sme):
            #     return Response({"error": "You do not have permission to view this history."}, status=403)

            if not (article.author == user or user.role in ['reviewer', 'admin', "exec_approver"] or is_assigned_sme):
                return Response({"error": "You do not have permission to view this history."}, status=403)


            # Fetch versions (Ordering is handled by the Model Meta)
            versions = ArticleVersion.objects.filter(article=article).select_related('changed_by')
            
            data = []
            for v in versions:
                data.append({
                    "version_id": v.id,
                    "changed_by": v.changed_by.full_name if v.changed_by else "Unknown",
                    "role": v.changed_by.role if v.changed_by else "N/A",
                    "timestamp": v.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "content_preview": v.content[:100] + "..." # Snippet for the list
                })

            return Response({
                "article_title": article.title,
                "current_status": article.status,
                "history": data
            })

        except Article.DoesNotExist:
            return Response({"error": "Article not found."}, status=404)

#11
class ArticleCommentHistoryView(APIView):
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read" , "feedback" , "admin" , "promote"]

    def get(self, request, pk):
        try:
            article = Article.objects.get(pk=pk)
            
            # Use a subquery to find the version ID that was created 
            # just before or at the same time as the comment
            version_subquery = ArticleVersion.objects.filter(
                article=article,
                created_at__lte=OuterRef('created_at')
            ).order_by('-created_at').values('id')[:1]

            comments = ArticleComment.objects.filter(article=article).select_related('user').annotate(
                detected_version_id=Subquery(version_subquery)
            ).order_by('created_at')

            comment_data = []
            for comment in comments:
                comment_data.append({
                    "comment_id": comment.id,
                    "user": comment.user.full_name,
                    "role": comment.user.role,
                    "text": comment.comment_text,
                    "timestamp": comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "version_at_time": f"{comment.detected_version_id}" if comment.detected_version_id else "Initial Draft"
                })

            return Response({
                "article_title": article.title,
                "comments": comment_data
            })

        except Article.DoesNotExist:
            return Response({"error": "Article not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)



# class ArticleHistoryView(APIView):
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_roles = ["read"]

#     def get(self, request, pk):
#         versions = ArticleVersion.objects.filter(article_id=pk).values(
#             'created_at', 'changed_by__full_name', 'content'
#         )
#         return Response(versions)
    


# class WriteComment(APIView):
#     """Execs/Admins add feedback. Triggers DB status revert via the Model."""
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_roles = ["feedback", "admin"]

#     def post(self, request, pk):
#         text = request.data.get('comment_text')
        
#         try:
#             with transaction.atomic():
#                 article = Article.objects.get(pk=pk)
                
#                 # Check if user is an SME, and if so, verify assignment
#                 if request.user.role == 'sme':
#                     is_assigned = ArticleAssignment.objects.filter(article=article, sme=request.user).exists()
#                     if not is_assigned:
#                         return Response({"error": "You are not assigned to this article."}, status=403)

#                 # Create comment (Status revert logic handles itself in models.py save())
#                 Comment = ArticleComment.objects.create(
#                     article=article,
#                     user=request.user,
#                     comment_text=text
#                 )
                
#                 handle_mentions_and_notifications(text, article)
                
#                 # Refresh from DB to get the newly reverted status
#                 article.refresh_from_db()
                
#                 return Response({
#                     "message": "Feedback recorded.", 
#                     "new_article_status": article.status
#                 })
                
#         except Article.DoesNotExist:
#             return Response({"error": "Article not found."}, status=404)
        


# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status, permissions
# from django.shortcuts import get_object_or_404
# # from accounts.permissions import HasRBACPermission
# from .models import ArticleDraft, ArticleVersion, PublishedContent
# from .serializers import *
# from utils.notifications.services import notify_approvers
# from accounts.models import User
# from utils.permissions.base import HasRBACPermission
# from django.core.cache import cache
# from django.db import transaction
# from datetime import *
# import logging
# #with atomic transaction
# class ArticleEditView(APIView):
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_role = "write"

#     def post(self, request):
#         title = request.data.get('title')
#         content = request.data.get('content')
        
#         # Start Transaction
#         with transaction.atomic():
#             draft = ArticleDraft.objects.create(
#                 title=title,
#                 original_author=request.user,
#                 flag_holder=request.user
#             )
            
#             ArticleVersion.objects.create(
#                 article=draft,
#                 editor=request.user,
#                 content_snapshot=content
#             )
        
#         # Notify only after successful DB commit
#         cache.delete("active_drafts_list")
#         notify_approvers(title, request.user.full_name , "write")
#         return Response({"message": "Draft created and flag assigned.", "draft_id": draft.id}, status=201)

#     def put(self, request, pk):
#         content = request.data.get('content')
        
#         with transaction.atomic():
#             # Use select_for_update to lock the draft row during the edit
#             draft = ArticleDraft.objects.select_for_update().get(pk=pk)
            
#             if draft.flag_holder != request.user:
#                 return Response({"error": "You do not hold the flag!"}, status=403)
            
#             ArticleVersion.objects.create(
#                 article=draft,
#                 editor=request.user,
#                 content_snapshot=content
#             )
            
#             draft.status = 'draft'
#             draft.save()
        
#         notify_approvers(draft.title, request.user.full_name , "edit")
#         return Response({"message": "New version saved and approvers notified."})
    
# # --- VIEW: FLAG TRANSFER (WRITER) ---
# class TransferFlagView(APIView):
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_role = "write"

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
# # class SubmitFeedbackView(APIView):
# #     permission_classes = [HasRBACPermission]
# #     required_area = "content"
# #     required_role = "feedback"

# #     def post(self, request, pk):
# #         draft = get_object_or_404(ArticleDraft, pk=pk)
# #         latest_version = draft.versions.last() # Feedback always goes to latest edit
        
# #         vote = request.data.get('vote') # Boolean
# #         comment = request.data.get('comment')
        
# #         # Append to JSON list
# #         feedback_entry = {
# #             "approver": request.user.full_name,
# #             "comment": comment,
# #             "vote": vote
# #         }
# #         latest_version.approver_comments.append(feedback_entry)
        
# #         if vote: latest_version.total_upvotes += 1
# #         else: latest_version.total_downvotes += 1
        
# #         latest_version.save()
# #         return Response({"message": "Feedback recorded on this version."})

# #new one
# class SubmitFeedbackView(APIView):
#     # ... permissions ...
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_roles = ["feedback", "admin"]

#     def post(self, request, pk):
#         draft = get_object_or_404(ArticleDraft, pk=pk)
#         latest_version = draft.versions.last()
        
#         feedback_data = {
#             "approver": request.user.full_name,
#             "comment": request.data.get('comment'),
#             "vote": request.data.get('vote'),
#             "timestamp": str(timezone.now())
#         }

#         # 1. Store in Redis List (Key: reviews_version_123)
#         # We use a list so we can store multiple reviews for one version
#         redis_key = f"reviews_version_{latest_version.id}"
        
#         # Get existing reviews, append new one, and save back
#         reviews = cache.get(redis_key) or []
#         reviews.append(feedback_data)
#         cache.set(redis_key, reviews, timeout=3600) # Cache for 1 hour

#         # 2. Also save to Postgres (The permanent "Cold Storage")
#         latest_version.approver_comments.append(feedback_data)
#         latest_version.save()

#         return Response({"message": "Feedback stored in live cache."})
# # --- VIEW: PUBLISH/REJECT (ADMIN) ---

# #new - with atmoc transcation
# class AdminReviewView(APIView):

#     #changing this also
#     # permission_classes = [permissions.IsAuthenticated] 
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_role = "admin"

#     def post(self, request, pk):
#         # if request.user.role != 'admin':
#         #     return Response({"error": "Admin only"}, status=403)
            
#         try:

#             action = request.data.get('action') 
        
#             with transaction.atomic():
#             # Lock the draft so no writer can 'Transfer' or 'Edit' while we review
#                 draft = ArticleDraft.objects.select_for_update().get(pk=pk)
#                 print(draft)
#                 if action == 'publish':
#                     latest = draft.versions.last()
#                     PublishedContent.objects.create(
#                         draft_reference=draft,
#                         title=draft.title,
#                         final_content=latest.content_snapshot,
#                         original_author=draft.original_author,
#                         last_editor=latest.editor
#                     )
#                     draft.status = 'published'
#                     draft.save()
                
#                 # We set a flag to clear cache AFTER the block
#                     should_clear_cache = True
                
#                 elif action == 'reject':
#                     draft.status = 'rejected'
#                     draft.save()
#                     should_clear_cache = False

#         # Cache invalidation happens outside the atomic block
#                 if action == 'publish' and should_clear_cache:
#                     cache.delete("published_articles_list")
#                     print("--- DEBUG: Published List Cache Cleared ---")

#                 return Response({"message": f"Action {action} completed successfully."})

#         except Exception as e:
#             return Response({"Error": str(e)})

# #lit bit old - new 
# # class AdminReviewView(APIView):
# #     permission_classes = [permissions.IsAuthenticated] 

# #     def post(self, request, pk):
# #         if request.user.role != 'admin':
# #             return Response({"error": "Admin only"}, status=403)
            
# #         draft = get_object_or_404(ArticleDraft, pk=pk)
# #         action = request.data.get('action') 
        
# #         if action == 'publish':
# #             latest = draft.versions.last()
# #             PublishedContent.objects.create(
# #                 draft_reference=draft,
# #                 title=draft.title,
# #                 final_content=latest.content_snapshot,
# #                 original_author=draft.original_author,
# #                 last_editor=latest.editor
# #             )
# #             draft.status = 'published'
# #             draft.save()

# #             # --- THE CACHE CHANGE ---
# #             # Delete the cache so the PublishedListView updates immediately
# #             cache.delete("published_articles_list")
# #             print("--- DEBUG: Published List Cache Cleared ---")
# #             # -----------------------

# #             return Response({"message": "Content is now public!"})
            
# #         elif action == 'reject':
# #             draft.status = 'rejected'
# #             draft.save()
# #             return Response({"message": "Draft rejected. Writer must edit again."})
        


# #old
# # class AdminReviewView(APIView):
# #     permission_classes = [permissions.IsAuthenticated] # We verify Admin role in code

# #     def post(self, request, pk):
# #         if request.user.role != 'admin':
# #             return Response({"error": "Admin only"}, status=403)
            
# #         draft = get_object_or_404(ArticleDraft, pk=pk)
# #         action = request.data.get('action') # 'publish' or 'reject'
        
# #         if action == 'publish':
# #             latest = draft.versions.last()
# #             PublishedContent.objects.create(
# #                 draft_reference=draft,
# #                 title=draft.title,
# #                 final_content=latest.content_snapshot,
# #                 original_author=draft.original_author,
# #                 last_editor=latest.editor
# #             )
# #             draft.status = 'published'
# #             draft.save()
# #             return Response({"message": "Content is now public!"})
            
# #         elif action == 'reject':
# #             draft.status = 'rejected'
# #             draft.save()
# #             return Response({"message": "Draft rejected. Writer must edit again."})
        

# #using redis for chaching
# class PublishedListView(APIView):
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     required_roles = ["read", "admin"]

#     def get(self, request):

#         print(request.user.role)
#         try:
#             cache_key = "published_articles_list"
        
#         # 1. Try to fetch from Redis
#             cached_data = cache.get(cache_key)
        
#             if cached_data:
#             # If found, return immediately!
#                 print("--- DEBUG: Serving Published List from Redis ---")
#                 return Response(cached_data)

#         # 2. If not found, Query Postgres
#             print("--- DEBUG: Cache Miss. Querying Postgres ---")
#             content = PublishedContent.objects.all().order_by('-published_at')
#             serializer = PublishedContentSerializer(content, many=True)
#             data = serializer.data

#         # 3. Save to Redis for 15 minutes (900 seconds)
#             cache.set(cache_key, data, timeout=900)

#             return Response(data)
        
#         except Exception as e:
#             return Response({"error": str(e)})
    

# ###old one 
# # class PublishedListView(APIView):
# #     """
# #     View for Associates and other staff to read officially published content.
# #     """
# #     permission_classes = [HasRBACPermission]
# #     required_area = "content"
# #     required_role = "read"

# #     def get(self, request):
# #         content = PublishedContent.objects.all().order_by('-published_at')
# #         serializer = PublishedContentSerializer(content, many=True)
# #         return Response(serializer.data)


# ### remove the below 2
# ##shows history according to draft id:
# # class RollbackPreviewView(APIView):
# #     """
# #     Admin/Writer view to see the full version history for audit or rollback.
# #     """
# #     permission_classes = [HasRBACPermission]
# #     required_area = "content"
# #     required_roles = ["read", "admin"]

# #     def get(self, request, pk):
# #         draft = get_object_or_404(ArticleDraft, pk=pk)
# #         serializer = ArticleDraftSerializer(draft)
# #         return Response(serializer.data)
    

# # class ArticleListView(APIView):

# #     permission_classes = [HasRBACPermission]
# #     required_area = "content"
# #     required_roles = ["read", "admin"]
    
# #     def get(self, request):
# #         user = request.user
        
# #         # 1. Admins and Approvers see EVERYTHING (latest state)
# #         if user.role in ['admin', 'approver']:
# #             drafts = ArticleDraft.objects.all().order_by('-created_at')
        
# #         # 2. Writers see drafts they created OR drafts where they hold the flag
# #         elif user.role == 'writer':
# #             from django.db.models import Q
# #             drafts = ArticleDraft.objects.filter(
# #                 Q(original_author=user) | Q(flag_holder=user)
# #             ).distinct().order_by('-created_at')
        
# #         else:
# #             return Response({"detail": "Not authorized to view drafts."}, status=403)

# #         serializer = ArticleDraftSerializer(drafts, many=True)
# #         return Response(serializer.data)
    
# #with redis one
# class ArticleListView(APIView):
#     permission_classes = [HasRBACPermission]
#     required_area = "content"
#     # Allow all three roles to access this view
#     required_roles = ["feedback", "admin", "write"] 

#     def get(self, request):
#         # Since everyone sees the same thing, one key for everyone
#         cache_key = "active_drafts_list"

#         try:
#             # 1. Try to fetch from Redis
#             cached_data = cache.get(cache_key)
#             if cached_data:
#                 print("--- DEBUG: Serving Shared Draft List from Redis ---")
#                 return Response(cached_data)

#             # 2. Cache Miss - Query Postgres
#             print("--- DEBUG: Cache Miss. Querying Postgres for Drafts/Rejected ---")
            
#             # Filter: only show 'draft' or 'rejected'. Exclude 'published'.
#             # We use __in to catch both statuses in one query
#             drafts = ArticleDraft.objects.filter(
#                 status__in=['draft', 'rejected']
#             ).order_by('-created_at')

#             serializer = ArticleDraftSerializer(drafts, many=True)
#             data = serializer.data
            
#             # 3. Save to Redis (900 seconds = 15 minutes)
#             cache.set(cache_key, data, timeout=900)

#             return Response(data)

#         except Exception as e:
#             return Response(
#                 {"error": str(e)}, 
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        

# #leave for now
# # class DraftDashboardView(APIView):
# #     permission_classes = [HasRBACPermission]
# #     required_area = "content"
# #     required_roles = ["read", "admin"]

# #     def get(self, request):
# #         try:
# #             user = request.user
        
# #             if user.role in ['admin', 'approver']:
# #             # Admins/Approvers see everything
# #                 drafts = ArticleDraft.objects.all().order_by('-created_at')
# #             else:
# #             # Writers only see where they are the Author OR the Flag Holder
# #                 from django.db.models import Q
# #                 drafts = ArticleDraft.objects.filter(
# #                     Q(original_author=user) | Q(flag_holder=user)
# #                 ).distinct().order_by('-created_at')

# #                 serializer = DraftDashboardSerializer(drafts, many=True)
# #                 return Response(serializer.data)
# #         except Exception as e:
# #             # return Response({str(e)})
# #             # logger.error(f"Error in DraftDashboardView: {str(e)}")
            
# #             # Return a clean error message to the user
# #             return Response(
# #                 {"error": str(e)}, 
# #                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
# #             )
    

# # class ArticleHistoryView(APIView):

# #     permission_classes = [HasRBACPermission]
# #     required_area = "content"
# #     required_role = ["read", "admin"]

# #     def get(self, request, version_id):
# #         redis_key = f"reviews_version_{version_id}"
        
# #         # 1. Try to get reviews from Redis
# #         reviews = cache.get(redis_key)
        
# #         if reviews:
# #             print("--- DEBUG: Serving Reviews from Redis ---")
# #             return Response(reviews)

# #         # 2. Fallback: If Redis expired, get from Postgres
# #         print("--- DEBUG: Cache Miss. Pulling from Postgres ---")
# #         version = get_object_or_404(ArticleVersion, id=version_id)
# #         reviews = version.approver_comments
        
# #         # 3. Re-fill the cache for the next person
# #         cache.set(redis_key, reviews, timeout=3600)

# #         return Response(reviews)
# #     # permission_classes = [HasRBACPermission]
# #     # required_area = "content"
# #     # required_role = "read"

# #     # def get(self, request, pk):
# #     #     draft = get_object_or_404(ArticleDraft, pk=pk)
# #     #     user = request.user

# #     #     # STRICT PERMISSION CHECK
# #     #     is_owner = (draft.original_author == user)
# #     #     is_flag_holder = (draft.flag_holder == user)
# #     #     is_staff = (user.role in ['admin', 'approver'])
# #     #     # print(is_owner or is_flag_holder or is_staff)
# #     #     print(is_staff)
# #     #     if not (is_owner or is_flag_holder or is_staff):
# #     #         return Response({"error": "You do not have permission to view this history."}, status=403)

# #     #     serializer = ArticleDraftSerializer(draft)
# #     #     return Response(serializer.data)
    


# class FlagTrackerView(APIView):
#     permission_classes = [HasRBACPermission] # Use your new IsAdmin class
#     required_area = "content"
#     required_roles = ["admin", "feedback"]

#     def get(self, request):
#         # We only want drafts that are still in progress (not published)
#         active_drafts = ArticleDraft.objects.exclude(status='published').select_related('flag_holder', 'original_author')
        
#         data = []
#         for draft in active_drafts:
#             data.append({
#                 "draft_id": draft.id,
#                 "title": draft.title,
#                 "status": draft.status,
#                 "original_author": draft.original_author.full_name,
#                 "current_flag_holder": draft.flag_holder.full_name if draft.flag_holder else "None",
#                 "last_updated": draft.created_at # Or use version timestamp
#             })
            
#         return Response(data)















# # from rest_framework.views import APIView
# # from rest_framework.response import Response
# # from rest_framework import status
# # from django.shortcuts import get_object_or_404
# # from django.db.models import Q

# # # NEW PERMISSION IMPORTS
# # from utils.permissions.rbac import CanRead, CanWrite, CanFeedback, IsAdmin
# # from .models import ArticleDraft, ArticleVersion, PublishedContent
# # from .serializers import (
# #     ArticleDraftSerializer, 
# #     DraftDashboardSerializer, 
# #     PublishedContentSerializer
# # )
# # from utils.notifications.services import notify_approvers
# # from accounts.models import User

# # # --- VIEW: CREATE/EDIT DRAFTS (WRITER) ---
# # class ArticleEditView(APIView):
# #     permission_classes = [CanWrite]
# #     rbac_area = "content"

# #     def post(self, request):
# #         """Initial Create by Writer"""
# #         title = request.data.get('title')
# #         content = request.data.get('content')
        
# #         draft = ArticleDraft.objects.create(
# #             title=title,
# #             original_author=request.user,
# #             flag_holder=request.user
# #         )
        
# #         ArticleVersion.objects.create(
# #             article=draft,
# #             editor=request.user,
# #             content_snapshot=content
# #         )
        
# #         notify_approvers(title, request.user.full_name, "write")
# #         return Response({"message": "Draft created and flag assigned.", "draft_id": draft.id}, status=201)

# #     def put(self, request, pk):
# #         """Edit existing Draft (Requires Flag)"""
# #         draft = get_object_or_404(ArticleDraft, pk=pk)
        
# #         # Business Logic Check: Only Flag Holder can edit
# #         if draft.flag_holder != request.user:
# #             return Response({"error": "You do not hold the flag!"}, status=403)
        
# #         content = request.data.get('content')
# #         ArticleVersion.objects.create(
# #             article=draft,
# #             editor=request.user,
# #             content_snapshot=content
# #         )
        
# #         draft.status = 'draft'
# #         draft.save()
        
# #         notify_approvers(draft.title, request.user.full_name, "edit")
# #         return Response({"message": "New version saved."})

# # # --- VIEW: FLAG TRANSFER (WRITER) ---
# # class TransferFlagView(APIView):
# #     permission_classes = [CanWrite]
# #     rbac_area = "content"

# #     def post(self, request, pk):
# #         draft = get_object_or_404(ArticleDraft, pk=pk)
# #         if draft.flag_holder != request.user:
# #             return Response({"error": "Only the current flag holder can transfer it."}, status=403)
        
# #         new_holder_id = request.data.get('new_holder_id')
# #         new_holder = get_object_or_404(User, id=new_holder_id, role='writer')
        
# #         draft.flag_holder = new_holder
# #         draft.save()
# #         return Response({"message": f"Flag transferred to {new_holder.full_name}"})

# # # --- VIEW: FEEDBACK & VOTE (APPROVER) ---
# # class SubmitFeedbackView(APIView):
# #     permission_classes = [CanFeedback]
# #     rbac_area = "content"

# #     def post(self, request, pk):
# #         draft = get_object_or_404(ArticleDraft, pk=pk)
# #         latest_version = draft.versions.last()
        
# #         vote = request.data.get('vote')
# #         comment = request.data.get('comment')
        
# #         feedback_entry = {
# #             "approver": request.user.full_name,
# #             "comment": comment,
# #             "vote": vote
# #         }
# #         latest_version.approver_comments.append(feedback_entry)
        
# #         if vote: latest_version.total_upvotes += 1
# #         else: latest_version.total_downvotes += 1
        
# #         latest_version.save()
# #         return Response({"message": "Feedback recorded."})

