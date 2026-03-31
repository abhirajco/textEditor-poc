"""
Notification services. All email sends use Celery tasks.
"""
import re
import random
from django.core.cache import cache
from django.conf import settings


def send_otp_via_email(email: str, pending_data: dict) -> None:
    otp       = random.randint(100000, 999999)
    cache_key = f"otp_auth_{email}"
    cache.set(cache_key, {
        "otp":       otp,
        "full_name": pending_data["full_name"],
        "password":  pending_data["password"],
    }, timeout=600)
    print(f"\n--- OTP DEBUG: {cache_key} → {otp} ---\n")
    try:
        from content.tasks import send_otp_email_task
        send_otp_email_task.delay(email, otp)
    except Exception:
        from django.core.mail import send_mail
        send_mail(
            subject        = "Your Platform Verification Code",
            message        = f"Your OTP is {otp}. It expires in 10 minutes.",
            from_email     = settings.EMAIL_HOST_USER,
            recipient_list = [email],
        )


def handle_mentions_and_notifications(text: str, content_obj, comment_obj, sender) -> None:
    """
    Parses @[Full Name](user_id) mentions from a comment.
    Creates CommentMention, increments Redis badge, fires Celery email task.
    """
    from django.contrib.auth import get_user_model
    from content.models import CommentMention
    User = get_user_model()

    pattern = r"@\[([^\]]+)\]\((\d+)\)"
    matches = re.findall(pattern, text)

    for full_name, user_id in matches:
        try:
            tagged_user = User.objects.get(user_id=user_id)
            CommentMention.objects.get_or_create(
                user=tagged_user, content=content_obj, comment=comment_obj
            )
            redis_key = f"unread_mentions:{tagged_user.user_id}"
            cache.get_or_set(redis_key, 0)
            cache.incr(redis_key)

            from content.tasks import send_mention_email_task
            send_mention_email_task.delay(
                mentioned_user_id = str(tagged_user.user_id),
                sender_name       = sender.full_name,
                content_title     = content_obj.title,
                content_id        = str(content_obj.content_id),
                comment_text      = text,
                comment_id        = str(comment_obj.comment_id),
            )
        except User.DoesNotExist:
            print(f"Mention ignored — user id={user_id} not found")
        except Exception as e:
            print(f"Mention error: {e}")


def send_task_assignment_email(assignee_email, assignee_name, task_title, assigned_by_name):
    from django.core.mail import send_mail
    send_mail(
        subject        = f"[Kanban] New Task Assigned: {task_title}",
        message        = f"Hi {assignee_name},\n\n{assigned_by_name} assigned you '{task_title}'.",
        from_email     = settings.EMAIL_HOST_USER,
        recipient_list = [assignee_email],
        fail_silently  = True,
    )


def send_task_transfer_email(new_assignee_email, new_assignee_name, task_title, transferred_by_name):
    from django.core.mail import send_mail
    send_mail(
        subject        = f"[Kanban] Task Transferred: {task_title}",
        message        = f"Hi {new_assignee_name},\n\n{transferred_by_name} transferred '{task_title}' to you.",
        from_email     = settings.EMAIL_HOST_USER,
        recipient_list = [new_assignee_email],
        fail_silently  = True,
    )
