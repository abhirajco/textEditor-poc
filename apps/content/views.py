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
#non published articles
class ActiveArticleListView(APIView):
    """Returns drafts, pending_executive, and pending_admin."""
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "feedback", "admin"]

    def get(self, request):

        cache_key = "active_articles_list"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data)
        
        articles = Article.objects.exclude(status='published').order_by('-updated_at')
        serializer = ArticleSerializer(articles, many=True)

        # Store in Redis for 5 minutes
        cache.set(cache_key, serializer.data, timeout=300)

        return Response(serializer.data)

#2
class PublishedArticleListView(APIView):
   
    permission_classes = [HasRBACPermission]
    required_area = "content"
    required_roles = ["read", "write", "feedback", "admin"]

    def get(self, request):

        cache_key = "published_articles_list"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data)
        
        articles = Article.objects.filter(status='published').order_by('-updated_at')
        serializer = ArticleSerializer(articles, many=True)

        # Store in Redis for 15 minutes (Published changes less often)
        cache.set(cache_key, serializer.data, timeout=900)
        return Response(serializer.data)


# --- 3. WORKFLOW & ACTIONS ---
class WriteComment(APIView):
    #Add feedback, trigger @mention emails, and handle Kick-Backs to Draft
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

                cache.delete(f"article_comments_{pk}")
                
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

                cache.delete("active_articles_list")
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
                    cache.delete("active_articles_list")
                    send_approval_emails('exec_approver', article)
                    return Response({"message": "Technical approval complete. Sent to Executives."})

                # STEP 2: Executive approves
                elif user_role == 'exec_approver' and article.status == 'pending_executive':
                    article.status = 'pending_admin'
                    article.save()
                    cache.delete("active_articles_list")
                    send_approval_emails('admin', article)
                    return Response({"message": "Executive approval complete. Sent to Admins."})

                # STEP 3: Admin approves (Final)
                elif user_role == 'admin' and article.status == 'pending_admin':
                    article.status = 'published'
                    article.save()
                    cache.delete("active_articles_list")
                    cache.delete("published_articles_list")
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
                cache.delete("active_articles_list")
                cache.delete(f"article_comments_{pk}")
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

        cache_key = f"article_comments_{pk}"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data)
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

            response_data = {
                "article_title": article.title,
                "comments": comment_data
            }
            
            # Cache for 10 minutes
            cache.set(cache_key, response_data, timeout=600)
            return Response(response_data)

        except Article.DoesNotExist:
            return Response({"error": "Article not found."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

