import re
import random
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings


# ==============================================================================
# OTP  (shared by both Insight and Kanban signup flows)
# ==============================================================================

def send_otp_via_email(email: str, pending_data: dict) -> None:
    """
    Generates a 6-digit OTP, caches it in Redis for 10 minutes,
    and emails it to the user.
    """
    otp       = random.randint(100000, 999999)
    cache_key = f"otp_auth_{email}"

    cache.set(cache_key, {
        "otp":       otp,
        "full_name": pending_data["full_name"],
        "password":  pending_data["password"],   # already hashed by the view
    }, timeout=600)

    print(f"\n--- OTP DEBUG: {cache_key} → {otp} ---\n")

    send_mail(
        subject       = "Your Platform Verification Code",
        message       = f"Your OTP is {otp}. It will expire in 10 minutes.",
        from_email    = settings.EMAIL_HOST_USER,
        recipient_list= [email],
    )


# ==============================================================================
# INSIGHT — Article mention notifications
# ==============================================================================

def handle_mentions_and_notifications(text: str, article_obj, sender) -> None:
    """
    Parses @[Full Name](user_id) mentions from a comment, adds users to the
    article's mentions M2M, increments their Redis unread counter, and sends
    them an email notification.

    Format: @[Robin Hood](3)
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    pattern = r'@\[([^\]]+)\]\((\d+)\)'
    matches = re.findall(pattern, text)   # → [("Robin Hood", "3"), ...]

    for full_name, user_id in matches:
        try:
            tagged_user = User.objects.get(id=int(user_id))

            # Add to article mentions M2M
            article_obj.mentions.add(tagged_user)

            # Increment Redis unread badge counter
            redis_key = f"unread_mentions:{tagged_user.id}"
            cache.get_or_set(redis_key, 0)
            cache.incr(redis_key)

            send_mail(
                subject        = f"You were mentioned in '{article_obj.title}'",
                message        = (
                    f"Hello {tagged_user.full_name},\n\n"
                    f"{sender.full_name} mentioned you in a comment on '{article_obj.title}'.\n\n"
                    f"Comment:\n{text}\n\n"
                    f"Log in to view it."
                ),
                from_email     = settings.EMAIL_HOST_USER,
                recipient_list = [tagged_user.email],
                fail_silently  = True,
            )
            print(f"✅ Mention notification sent to {tagged_user.email} (id={user_id})")

        except User.DoesNotExist:
            print(f"⚠️  Mention ignored — no user found with id={user_id}")
        except Exception as e:
            print(f"⚠️  Mention error for id={user_id}: {e}")


def send_approval_emails(target_role: str, article) -> None:
    """
    Sends bulk emails to all users with a specific role when an article
    moves through the approval workflow.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    users      = User.objects.filter(role=target_role)
    email_list = [u.email for u in users]

    if not email_list:
        return

    try:
        send_mail(
            subject        = f"Action Required: '{article.title}' is ready for your review",
            message        = f"The article '{article.title}' has been moved to '{article.status}' and requires your attention.",
            from_email     = settings.EMAIL_HOST_USER,
            recipient_list = email_list,
            fail_silently  = True,
        )
    except Exception as e:
        print(f"send_approval_emails error: {e}")


def send_assigned_sme_emails(article) -> None:
    """
    Sends emails ONLY to the SMEs specifically assigned to this article.
    """
    from apps.content.models import ArticleAssignment
    assignments = ArticleAssignment.objects.filter(article=article).select_related('sme')
    email_list  = [a.sme.email for a in assignments if a.sme.is_active]

    if not email_list:
        return

    send_mail(
        subject        = f"Action Required: You have been assigned to '{article.title}'",
        message        = (
            f"Hello,\n\nYou are the appointed SME for the article '{article.title}'.\n"
            f"Please review it at your earliest convenience."
        ),
        from_email     = settings.EMAIL_HOST_USER,
        recipient_list = email_list,
        fail_silently  = True,
    )


# ==============================================================================
# KANBAN — Task notification emails
# ==============================================================================

def send_task_assignment_email(assignee_email: str, assignee_name: str,
                                task_title: str, assigned_by_name: str) -> None:
    """Notifies a user they have been assigned a new Kanban task."""
    send_mail(
        subject        = f"[Kanban] New Task Assigned: {task_title}",
        message        = (
            f"Hi {assignee_name},\n\n"
            f"{assigned_by_name} has assigned you the task '{task_title}'.\n\n"
            f"Log in to the Kanban Board to view details and start working."
        ),
        from_email     = settings.EMAIL_HOST_USER,
        recipient_list = [assignee_email],
        fail_silently  = True,
    )


def send_task_transfer_email(new_assignee_email: str, new_assignee_name: str,
                              task_title: str, transferred_by_name: str) -> None:
    """Notifies a user that a Kanban task has been transferred to them."""
    send_mail(
        subject        = f"[Kanban] Task Transferred to You: {task_title}",
        message        = (
            f"Hi {new_assignee_name},\n\n"
            f"{transferred_by_name} has transferred the task '{task_title}' to you.\n\n"
            f"Log in to the Kanban Board to view and update it."
        ),
        from_email     = settings.EMAIL_HOST_USER,
        recipient_list = [new_assignee_email],
        fail_silently  = True,
    )
