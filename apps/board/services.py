from .models import Task

def create_task_from_initiation(
    title,
    brief,
    content_type,
    campaign_id,
    event_id,
    created_by
):

    task = Task.objects.create(
        title=title,
        description=brief,
        content_type=content_type,
        campaign_id=campaign_id,
        event_id=event_id,
        assigned_by=created_by,
        status="todo"
    )

    return task