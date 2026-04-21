"""
Advanced seed data generator v4
Creates realistic workflow data for ALL APIs

Users: admin, executive, writer, reviewer, sme
Content stages: draft, in_review, rejected, published
Campaign → Event → Task hierarchy included

Passwords: Pass123!
"""

import os
import django
import random
from datetime import datetime, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth.models import Group
from accounts.models import User, RBAC
from board.models import Campaign, Event, Task, TaskHistory, Discussion
from content.models import (
    Content,
    ContentVersion,
    ContentHistory,
    ContentAssignment,
    ContentComment,
)

PASSWORD = "Pass123!"


# ============================================================
# USER DEFINITIONS
# ============================================================

USERS_DEF = [
    {
        "email": "admin@platform.com",
        "name": "Admin",
        "group": "admin",
        "role": "admin",
        "staff": True,
    },
    {
        "email": "exec@platform.com",
        "name": "Executive",
        "group": "executive",
        "role": "exec_approver",
        "staff": False,
    },
    {
        "email": "writer@platform.com",
        "name": "Writer",
        "group": "internal",
        "role": "writer",
        "staff": False,
    },
    {
        "email": "reviewer@platform.com",
        "name": "Reviewer",
        "group": "internal",
        "role": "reviewer",
        "staff": False,
    },
    {
        "email": "sme@platform.com",
        "name": "Subject Expert",
        "group": "external",
        "role": "sme",
        "staff": False,
    },
]

# RBAC Rules mapped by group
RBAC_RULES = {
    "admin": {("content", "admin"), ("board", "admin"), ("reports", "admin"), ("settings", "admin"), ("users", "admin")},
    "executive": {("content", "read"), ("content", "approve"), ("board", "read"), ("reports", "read")},
    "internal": {("content", "write"), ("content", "update"), ("content", "approve"), ("board", "write"), ("board", "update"), ("reports", "read")},
    "external": {("content", "update"), ("content", "approve")},
}


# ============================================================
# USER SEEDING
# ============================================================

def seed_users():
    """Create users with groups and RBAC rules"""
    users = {}

    for u in USERS_DEF:
        user = User.objects.create(
            email=u["email"],
            full_name=u["name"],
            group=u["group"],
            role=u["role"],
            is_staff=u.get("staff", False),
            is_superuser=u.get("staff", False),
            is_active=True,
        )

        user.set_password(PASSWORD)
        user.save()

        # Create and assign group
        group, _ = Group.objects.get_or_create(name=u["group"].capitalize())
        user.groups.add(group)

        # Delete existing RBAC rules for this group
        RBAC.objects.filter(application_group=group).delete()

        # Create new RBAC rules
        for area, action in RBAC_RULES.get(u["group"], set()):
            RBAC.objects.create(
                application_group=group,
                application_area=area,
                application_action=action,
            )

        users[u["role"]] = user
        print(f"  ✓ Created user: {u['email']} ({u['role']})")

    return users


# ============================================================
# BOARD DATA SEEDING
# ============================================================

def seed_board(users):
    """Create campaigns with events and tasks"""
    campaigns = []
    admin = users["admin"]
    writer = users["writer"]

    for i in range(3):
        # Create Campaign
        camp = Campaign.objects.create(
            title=f"Campaign {i + 1}",
            description=f"Marketing campaign {i + 1}",
            created_by=admin,
            max_hierarchy_level=3,
        )
        print(f"  ✓ Created campaign: {camp.title}")

        for j in range(2):
            # Create Event under Campaign
            event = Event.objects.create(
                campaign=camp,
                title=f"Event {j + 1} - {camp.title}",
                created_by=admin,
            )
            print(f"    ✓ Created event: {event.title}")

            for k in range(2):
                # FIX 1: Use campaign and event objects (not campaign_id/event_id)
                task = Task.objects.create(
                    campaign=camp,  # Pass the campaign object
                    event=event,    # Pass the event object
                    title=f"Task {k + 1} - {event.title}",
                    assigned_by=admin,
                    assigned_to=writer,
                    status="todo",  # Use "todo" (no underscore)
                    priority="medium",
                )

                # Create task history
                TaskHistory.objects.create(
                    task=task,
                    action="created",
                    performed_by=admin,
                    detail="Seed task created",
                )

                # Create initial discussion
                Discussion.objects.create(
                    task=task,
                    author=admin,
                    message="Initial task discussion",
                )
                print(f"      ✓ Created task: {task.title}")

        campaigns.append(camp)

    return campaigns


# ============================================================
# CONTENT CONSTANTS
# ============================================================

STAGES = ["draft", "in_review", "rejected", "published"]

TITLES = [
    "AI in Marketing",
    "Cloud Security Guide",
    "Future of SaaS",
    "DevOps Best Practices",
    "SEO Strategy 2026",
    "Content Marketing Trends",
    "Python for Data Science",
    "Web Development Essentials",
]

CONTENT_TYPES = ["blog", "whitepaper", "case_study", "guide"]

TAGS = [
    "seo,marketing,ai",
    "cloud,security,devops",
    "saas,technology,trends",
    "content,strategy,digital",
]


def random_date():
    """Generate a random date within the past year"""
    return datetime.now() - timedelta(days=random.randint(1, 365))


# ============================================================
# CONTENT SEEDING
# ============================================================

def seed_content(users, campaigns):
    """Create content items with versions, history, assignments, and comments"""
    writer = users["writer"]
    reviewer = users["reviewer"]
    admin = users["admin"]
    executive = users["exec_approver"]
    sme = users["sme"]

    all_tasks = list(Task.objects.all())

    print("\n  Creating content items...")

    for i in range(40):
        stage = random.choice(STAGES)
        task = random.choice(all_tasks) if all_tasks else None

        content = Content.objects.create(
            title=random.choice(TITLES) + f" #{i + 1}",
            body="Sample generated content body. This is a realistic content piece for testing.",
            author=writer,
            campaign=task.campaign if task else campaigns[0],
            event=task.event if task else None,
            task=task,  # FIX 1: Use 'task' object, not 'task_id'
            status=stage,
            tags=random.choice(TAGS),
            content_type=random.choice(CONTENT_TYPES),
            created_at=random_date(),
        )

        # Create content version
        ContentVersion.objects.create(
            content=content,
            title=content.title,
            body=content.body,
            changed_by=writer,
        )

        # Create content history
        ContentHistory.objects.create(
            content=content,
            action_type="created",
            performed_by=writer,
        )

        # Set approval flags for published content
        if stage == "published":
            content.internal_approval = True
            content.marketing_approval = True
            content.stakeholder_approval = True
            content.save()

        # Lock permanently rejected content
        if stage == "rejected":
            content.locked_permanently = True
            content.save()

        # SME assignment (60% chance)
        if random.random() > 0.4:
            # FIX 2: Include 'executive' field for ContentAssignment
            ContentAssignment.objects.create(
                content=content,
                sme=sme,
                executive=executive,  # Pass the executive user object
            )

        # Add random comments (0-3 per content)
        for _ in range(random.randint(0, 3)):
            # Generate random selected text (excerpt from content body)
            selected_text = None
            if random.random() > 0.5:  # 50% chance to have selected text
                words = content.body.split()
                if len(words) > 2:
                    start_idx = random.randint(0, len(words) - 3)
                    selected_text = " ".join(words[start_idx:start_idx + 3])
            
            comment = ContentComment.objects.create(
                content=content,
                user=random.choice([reviewer, admin, executive]),
                comment_text="Please review this section carefully.",
                selected_text=selected_text,  # NEW FIELD
            )

        if (i + 1) % 10 == 0:
            print(f"    ✓ Created {i + 1}/40 content items")

    print(f"  ✓ Created 40 content items total")


# ============================================================
# CLEANUP/WIPE
# ============================================================

def wipe():
    """Delete all seeded data in correct order (respecting foreign keys)"""
    print("\nWiping database...")

    try:
        # Content related (delete in reverse order of dependencies)
        ContentComment.objects.all().delete()
        print("  ✓ Deleted ContentComment records")
    except Exception as e:
        print(f"  ⚠ ContentComment table issue: {e}")

    try:
        ContentAssignment.objects.all().delete()
        print("  ✓ Deleted ContentAssignment records")
    except Exception as e:
        print(f"  ⚠ ContentAssignment table issue: {e}")

    try:
        ContentHistory.objects.all().delete()
        print("  ✓ Deleted ContentHistory records")
    except Exception as e:
        print(f"  ⚠ ContentHistory table issue: {e}")

    try:
        ContentVersion.objects.all().delete()
        print("  ✓ Deleted ContentVersion records")
    except Exception as e:
        print(f"  ⚠ ContentVersion table issue: {e}")

    try:
        Content.objects.all().delete()
        print("  ✓ Deleted Content records")
    except Exception as e:
        print(f"  ⚠ Content table issue: {e}")

    try:
        # Board related
        Discussion.objects.all().delete()
        print("  ✓ Deleted Discussion records")
    except Exception as e:
        print(f"  ⚠ Discussion table issue: {e}")

    try:
        TaskHistory.objects.all().delete()
        print("  ✓ Deleted TaskHistory records")
    except Exception as e:
        print(f"  ⚠ TaskHistory table issue: {e}")

    try:
        Task.objects.all().delete()
        print("  ✓ Deleted Task records")
    except Exception as e:
        print(f"  ⚠ Task table issue: {e}")

    try:
        Event.objects.all().delete()
        print("  ✓ Deleted Event records")
    except Exception as e:
        print(f"  ⚠ Event table issue: {e}")

    try:
        Campaign.objects.all().delete()
        print("  ✓ Deleted Campaign records")
    except Exception as e:
        print(f"  ⚠ Campaign table issue: {e}")

    try:
        # Users and auth
        RBAC.objects.all().delete()
        print("  ✓ Deleted RBAC records")
    except Exception as e:
        print(f"  ⚠ RBAC table issue: {e}")

    try:
        User.objects.all().delete()
        print("  ✓ Deleted User records")
    except Exception as e:
        print(f"  ⚠ User table issue: {e}")

    try:
        Group.objects.all().delete()
        print("  ✓ Deleted Group records")
    except Exception as e:
        print(f"  ⚠ Group table issue: {e}")

    print("  ✓ Database cleanup complete")


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("SEED DATA GENERATOR v4")
    print("=" * 60)

    print("\n1. Wiping database...")
    wipe()

    print("\n2. Seeding users...")
    users = seed_users()

    print("\n3. Seeding board (campaigns → events → tasks)...")
    campaigns = seed_board(users)

    print("\n4. Generating content...")
    seed_content(users, campaigns)

    print("\n" + "=" * 60)
    print("SEED COMPLETE ✓")
    print("=" * 60)

    print("\nLogin Credentials (Password: Pass123!)")
    print("-" * 60)
    for user_def in USERS_DEF:
        print(f"  {user_def['email']:25} ({user_def['role']})")
    print("-" * 60)
    print("\nTotal Data Created:")
    print(f"  • Users: {len(USERS_DEF)}")
    print(f"  • Campaigns: {Campaign.objects.count()}")
    print(f"  • Events: {Event.objects.count()}")
    print(f"  • Tasks: {Task.objects.count()}")
    print(f"  • Content Items: {Content.objects.count()}")
    print(f"  • Content Comments: {ContentComment.objects.count()}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()