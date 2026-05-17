"""
Celery tasks for the content app.
"""
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import logging
import re
import uuid as _uuid
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


# ── Version snapshot ──────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def create_content_version_task(self, content_id, title, body, image_url, changed_by_id):
    """Creates a ContentVersion row in background after content is saved."""
    try:
        from content.models import Content, ContentVersion
        from accounts.models import User
        c          = Content.objects.get(content_id=content_id)
        changed_by = User.objects.filter(user_id=changed_by_id).first()
        ContentVersion.objects.create(
            content    = c,
            title      = title,
            body       = body,
            image_url  = image_url,
            changed_by = changed_by,
        )
        logger.info(f"ContentVersion created for {content_id}")
    except Exception as exc:
        raise self.retry(exc=exc)


# ── Approval email ────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def send_approval_email_task(self, user_ids, content_id, stage):
    """Sends approval notification emails to selected users."""
    try:
        from content.models import Content
        from accounts.models import User
        c  = Content.objects.get(content_id=content_id)
        users      = User.objects.filter(user_id__in=user_ids)
        email_list = [u.email for u in users if u.is_active]
        if not email_list:
            return
        stage_labels = {
            "in_review": "is now In Review and awaits internal approval",
            "pending_exec_admin": "has been approved internally and awaits your review",
        }
        description = stage_labels.get(stage, f"has moved to '{stage}'")
    

        for user in users:
            if not user.is_active:
                continue
            # Use EmailMessage so To: only shows this recipient.
            # A unique Message-ID per recipient prevents Outlook from
            # threading all approval emails together and exposing the full list.
            
            
            msg = EmailMessage(
                subject   = " AMS | Action Required",
                body      = f"Hi {user.full_name},\n\nThe content '{c.title}' {description}.",
                from_email= settings.DEFAULT_FROM_EMAIL,
                to        = [user.email],   # only this recipient — To: shows only them
                headers   = {
                    # Unique Message-ID stops Outlook grouping them into one thread
                    "Message-ID": f"<{_uuid.uuid4()}@ams-platform>",
                },
            )
            msg.send(fail_silently=False)
        logger.info(f"Approval email sent for content {content_id} stage={stage} to {email_list}")
    except Exception as exc:
        raise self.retry(exc=exc)


# ── Rejection email ───────────────────────────────────────────────────────────
#not using it for now
@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def send_rejection_email_task(self, content_id, rejected_by_name, reason):
    """Notifies the author (and all stakeholders) that content was rejected."""
    try:
        from content.models import Content
        c     = Content.objects.get(content_id=content_id)
        recipients = [c.author.email]
        send_mail(
            subject        = f"Content Rejected: '{c.title}'",
            message        = (
                f"Hi {c.author.full_name},\n\n"
                f"Your content '{c.title}' was rejected by {rejected_by_name}.\n\n"
                f"Reason: {reason or 'No reason provided.'}\n\n"
                f"The content is now locked and cannot be edited."
            ),
            from_email     = settings.EMAIL_HOST_USER,
            recipient_list = recipients,
            fail_silently  = False,
        )
        logger.info(f"Rejection email sent for content {content_id}")
    except Exception as exc:
        raise self.retry(exc=exc)



# ── Mention email ─────────────────────────────────────────────────────────────




@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_mention_email_task(self, mentioned_user_id, sender_name, content_title,
                           content_id, comment_text, comment_id):
    try:
        from accounts.models import User

        user = User.objects.get(user_id=mentioned_user_id)

        cleaned_text = re.sub(
            r"@\[(.*?)\]\(([0-9a-fA-F-]+)\)",
            r"@\1",
            comment_text
        )

        msg = EmailMessage(
            subject=f"AMS | You were mentioned in '{content_title}'",
            body=(
                f"Hello {user.full_name},\n\n"
                f"{sender_name} mentioned you in a comment.\n\n"
                f"{cleaned_text}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
            headers={
                "Message-ID": f"<{_uuid.uuid4()}@ams-platform>",
            },
        )
        msg.send(fail_silently=False)

    except Exception as exc:
        raise self.retry(exc=exc)
# ── OTP email ─────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_otp_email_task(self, email, otp):
    try:
        msg = EmailMessage(
            subject="AMS | Your Platform Verification Code",
            body=f"Your OTP is {otp}. It expires in 10 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
            headers={
                "Message-ID": f"<{_uuid.uuid4()}@ams-platform>",
            },
        )
        msg.send(fail_silently=False)

    except Exception as exc:
        raise self.retry(exc=exc)

# ── SME assignment email ──────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_sme_assignment_email_task(self, content_id):
    try:
        from content.models import Content, ContentAssignment

        c = Content.objects.get(content_id=content_id)
        assignments = ContentAssignment.objects.filter(content=c).select_related("sme")

        for assignment in assignments:
            sme = assignment.sme
            if not sme.is_active:
                continue

            msg = EmailMessage(
                subject=f"AMS | Action Required: Assigned to '{c.title}'",
                body=f"You are the appointed SME for '{c.title}'. Please review it.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[sme.email],
                headers={
                    "Message-ID": f"<{_uuid.uuid4()}@ams-platform>",
                },
            )
            msg.send(fail_silently=False)

    except Exception as exc:
        raise self.retry(exc=exc)

