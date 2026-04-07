"""
Celery tasks for the content app.
"""
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import logging

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
        c          = Content.objects.get(content_id=content_id)
        users      = User.objects.filter(user_id__in=user_ids)
        email_list = [u.email for u in users if u.is_active]
        if not email_list:
            return
        stage_labels = {
            "in_review":              "is now In Review and awaits internal approval",
            "pending_exec_admin":     "has been approved internally and awaits your review",
        }
        description = stage_labels.get(stage, f"has moved to '{stage}'")
        send_mail(
            subject        = f"Action Required: '{c.title}' needs your review",
            message        = f"The content '{c.title}' {description}.\n\nPlease log in to review it.",
            from_email     = settings.EMAIL_HOST_USER,
            recipient_list = email_list,
            fail_silently  = False,
        )
        logger.info(f"Approval email sent for content {content_id} stage={stage} to {email_list}")
    except Exception as exc:
        raise self.retry(exc=exc)


# ── Rejection email ───────────────────────────────────────────────────────────

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


# ── Auto-publish after 24h ────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def auto_publish_content_task(self, content_id):
    """
    Fires 24 hours after all_approved_at is stamped.
    Publishes the content only if it is still fully approved and not rejected.
    """
    try:
        from content.models import Content, ContentHistory
        from django.utils import timezone

        c = Content.objects.get(content_id=content_id)

        # Safety checks — if anything changed in the 24h window, abort.
        if c.status in ("published", "rejected"):
            logger.info(f"auto_publish: content {content_id} already in final state {c.status}, skipping.")
            return

        if not (c.internal_approval and c.marketing_approval and c.stakeholder_approval):
            logger.info(f"auto_publish: content {content_id} no longer fully approved, skipping.")
            return

        if c.locked_permanently:
            logger.info(f"auto_publish: content {content_id} is locked permanently, skipping.")
            return

        c.status = "published"
        c.save(update_fields=["status"])

        ContentHistory.objects.create(
            content      = c,
            action_type  = "auto_published",
            performed_by = None,
            note         = "Auto-published 24 hours after all three approvals were received.",
        )

        send_mail(
            subject        = f"Published: '{c.title}'",
            message        = (
                f"Hi {c.author.full_name},\n\n"
                f"Your content '{c.title}' has been automatically published after receiving "
                f"all required approvals.\n\nCongratulations!"
            ),
            from_email     = settings.EMAIL_HOST_USER,
            recipient_list = [c.author.email],
            fail_silently  = True,
        )
        logger.info(f"auto_publish: content {content_id} published successfully.")
    except Content.DoesNotExist:
        logger.error(f"auto_publish: content {content_id} not found.")
    except Exception as exc:
        raise self.retry(exc=exc)


# ── Mention email ─────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_mention_email_task(self, mentioned_user_id, sender_name, content_title,
                             content_id, comment_text, comment_id):
    """Sends @mention email notification in background."""
    try:
        from accounts.models import User
        user = User.objects.get(user_id=mentioned_user_id)
        send_mail(
            subject        = f"You were mentioned in '{content_title}'",
            message        = f"Hello {user.full_name},\n\n{sender_name} mentioned you.\n\n{comment_text}",
            from_email     = settings.EMAIL_HOST_USER,
            recipient_list = [user.email],
            fail_silently  = False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


# ── OTP email ─────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_otp_email_task(self, email, otp):
    """Sends OTP email in background."""
    try:
        send_mail(
            subject        = "Your Platform Verification Code",
            message        = f"Your OTP is {otp}. It expires in 10 minutes.",
            from_email     = settings.EMAIL_HOST_USER,
            recipient_list = [email],
            fail_silently  = False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


# ── SME assignment email ──────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_sme_assignment_email_task(self, content_id):
    """Notifies assigned SMEs in background."""
    try:
        from content.models import Content, ContentAssignment
        c           = Content.objects.get(content_id=content_id)
        assignments = ContentAssignment.objects.filter(content=c).select_related("sme")
        email_list  = [a.sme.email for a in assignments if a.sme.is_active]
        if not email_list:
            return
        send_mail(
            subject        = f"Action Required: Assigned to '{c.title}'",
            message        = f"You are the appointed SME for '{c.title}'. Please review it.",
            from_email     = settings.EMAIL_HOST_USER,
            recipient_list = email_list,
            fail_silently  = False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)
