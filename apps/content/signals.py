"""
Django Signals for the content app.
USE CASE 3 — Cache busting on Content save.
USE CASE 6 — Async ContentVersion creation via Celery.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender="content.Content")
def bust_content_cache(sender, instance, **kwargs):
    cache.delete("active_contents_list")
    if instance.status == "published":
        cache.delete("published_contents_list")
    logger.debug(f"Cache busted for content {instance.content_id}")


@receiver(post_save, sender="content.Content")
def trigger_version_creation(sender, instance, created, **kwargs):
    if getattr(instance, "_skip_version", False):
        return
    if not hasattr(instance, "_version_data"):
        return
    data = instance._version_data
    from content.tasks import create_content_version_task
    create_content_version_task.delay(
        content_id    = str(instance.content_id),
        title         = data["title"],
        body          = data["body"],
        image_url     = data.get("image_url"),
        changed_by_id = str(data["changed_by_id"]),
    )
    logger.info(f"Version creation task queued for content {instance.content_id}")
