"""
Advanced seed data generator
Creates realistic workflow data for ALL APIs

Users: admin, executive, writer, reviewer, sme
Content stages: draft, in_review, rejected, published
Campaign hierarchy included

Passwords: Pass123!
"""

import os
import django
import random
from datetime import datetime, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth.models import Group
from accounts.models import *
from board.models import *
from content.models import *

PASSWORD = "Pass123!"


# ============================================================
# USERS
# ============================================================

USERS_DEF = [
    {"email": "admin@platform.com", "name": "Admin", "group": "admin", "role": "admin", "staff": True},
    {"email": "exec@platform.com", "name": "Executive", "group": "executive", "role": "exec_approver"},
    {"email": "writer@platform.com", "name": "Writer", "group": "internal", "role": "writer"},
    {"email": "reviewer@platform.com", "name": "Reviewer", "group": "internal", "role": "reviewer"},
    {"email": "sme@platform.com", "name": "Subject Expert", "group": "external", "role": "sme"},
]

RBAC_RULES = {
    "admin": {("content", "admin"), ("board", "admin")},
    "executive": {("content", "read"), ("content", "promote")},
    "internal": {("content", "write"), ("content", "update"), ("content", "feedback")},
    "external": {("content", "feedback")},
}


def seed_users():
    users = {}

    for u in USERS_DEF:
        user = User.objects.create(
            email=u["email"],
            full_name=u["name"],
            group=u["group"],
            role=u["role"],
            is_staff=u.get("staff", False),
            is_superuser=u.get("staff", False),
        )

        user.set_password(PASSWORD)
        user.save()

        g, _ = Group.objects.get_or_create(name=u["group"].capitalize())
        user.groups.add(g)

        RBAC.objects.filter(application_group=g).delete()

        for area, action in RBAC_RULES.get(u["group"], []):
            RBAC.objects.create(
                application_group=g,
                application_area=area,
                application_action=action,
            )

        users[u["role"]] = user

    return users


# ============================================================
# BOARD DATA
# ============================================================

def seed_board(users):
    campaigns = []
    for i in range(3):
        camp = Campaign.objects.create(
            title=f"Campaign {i+1}",
            description="Marketing campaign",
            created_by=users["admin"],
            max_hierarchy_level=3,
        )

        for j in range(2):
            event = Event.objects.create(
                campaign=camp,
                title=f"Event {j+1} - {camp.title}",
                created_by=users["admin"],
            )

            for k in range(2):
                # FIX 1: Use campaign/event instead of campaign_id/event_id 
                # (Assuming you updated your models.py as discussed)
                task = Task.objects.create(
                    campaign=camp, 
                    event=event,
                    title=f"Task {k+1} - {event.title}",
                    assigned_by=users["admin"],
                    assigned_to=users["writer"],
                    status="todo", # Match your STATUS_CHOICES "todo" (no underscore)
                )

                TaskHistory.objects.create(
                    task=task,
                    action="created",
                    performed_by=users["admin"],
                    detail="Seed task created",
                )

                Discussion.objects.create(
                    task=task,
                    author=users["admin"],
                    message="Initial task discussion",
                )
        campaigns.append(camp)
    return campaigns

# ============================================================
# CONTENT GENERATION CONSTANTS (Make sure these are here!)
# ============================================================
STAGES = ["draft", "in_review", "rejected", "published"]

TITLES = [
    "AI in Marketing",
    "Cloud Security Guide",
    "Future of SaaS",
    "DevOps Best Practices",
    "SEO Strategy 2026",
    "Content Marketing Trends",
]

def random_date():
    return datetime.now() - timedelta(days=random.randint(1, 365))


# ============================================================
# CONTENT GENERATION
# ============================================================

def seed_content(users, campaigns):
    writer = users["writer"]
    reviewer = users["reviewer"]
    admin = users["admin"]
    executive = users["exec_approver"] # This maps to the "exec@platform.com" user
    sme = users["sme"]

    all_tasks = list(Task.objects.all())

    for i in range(40):
        stage = random.choice(STAGES)
        task = random.choice(all_tasks)

        content = Content.objects.create(
            title=random.choice(TITLES) + f" #{i}",
            body="Sample generated content body",
            author=writer,
            campaign=task.campaign,
            event=task.event,
            task_id=task,
            status=stage,
            tags="seo,marketing,ai",
            content_type="blog",
        )

        ContentVersion.objects.create(
            content=content,
            title=content.title,
            body=content.body,
            changed_by=writer,
        )

        ContentHistory.objects.create(
            content=content,
            action_type="created",
            performed_by=writer,
        )

        if stage == "published":
            content.internal_approval = True
            content.marketing_approval = True
            content.stakeholder_approval = True
            content.save()

        if stage == "rejected":
            content.locked_permanently = True
            content.save()

        # SME assignment
        if random.random() > 0.6:
            # FIX 2: Added the missing 'executive' field to satisfy the NOT NULL constraint
            ContentAssignment.objects.create(
                content=content,
                sme=sme,
                executive=executive # Passing the executive user object here
            )

        # comments
        for _ in range(random.randint(0, 3)):
            comment = ContentComment.objects.create(
                content=content,
                user=random.choice([reviewer, admin, executive]),
                comment_text="Please review this section.",
            )

            # FIX 3: Ensure this matches your CommentMention model field (user vs mentioned_user)
            CommentMention.objects.create(
                comment=comment,
                content=content,
                user=writer, 
            )

    print("Created 40 content items")
# ============================================================
# MAIN
# ============================================================

def wipe():

    ContentComment.objects.all().delete()
    CommentMention.objects.all().delete()
    ContentAssignment.objects.all().delete()
    ContentVersion.objects.all().delete()
    ContentHistory.objects.all().delete()
    Content.objects.all().delete()

    Discussion.objects.all().delete()
    TaskHistory.objects.all().delete()
    Task.objects.all().delete()
    Event.objects.all().delete()
    Campaign.objects.all().delete()

    RBAC.objects.all().delete()
    User.objects.all().delete()
    Group.objects.all().delete()


def main():

    print("Wiping DB...")
    wipe()

    print("Seeding users...")
    users = seed_users()

    print("Seeding board...")
    campaigns = seed_board(users)

    print("Generating content...")
    seed_content(users, campaigns)

    print("\nSeed Complete\n")

    print("Login credentials (Pass123!)")
    print("admin@platform.com")
    print("exec@platform.com")
    print("writer@platform.com")
    print("reviewer@platform.com")
    print("sme@platform.com")


if __name__ == "__main__":
    main()



# """
# Fresh seed data for v4 — Article renamed to Content, Campaign/Event/Task hierarchy.
# All passwords: Pass123!
# """
# import os
# import django
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
# django.setup()

# from django.contrib.auth.models import Group
# from accounts.models import User, RBAC
# from content.models import Content, ContentVersion, ContentComment, ContentAssignment, CommentMention
# from board.models import Campaign, Event, Task, TaskHistory, Discussion

# PASSWORD = "Pass123!"

# USERS_DEF = [
#     {"email": "admin@platform.com",    "name": "System Admin",   "group": "admin",     "role": "admin",         "staff": True},
#     {"email": "exec@platform.com",     "name": "Exec Boss",      "group": "executive", "role": "exec_approver", "staff": False},
#     {"email": "writer@platform.com",   "name": "Alice Writer",   "group": "internal",  "role": "writer",        "staff": False},
#     {"email": "reviewer@platform.com", "name": "Bob Reviewer",   "group": "internal",  "role": "reviewer",      "staff": False},
#     {"email": "sme@platform.com",      "name": "Charlie Expert", "group": "external",  "role": "sme",           "staff": False},
# ]

# RBAC_MAP = {
#     "admin":    {("content","admin"),("board","admin"),("users","admin")},
#     "executive":{("content","read"),("content","feedback"),("content","promote"),
#                  ("board","read"),("board","write"),("board","update")},
#     "internal": {("content","write"),("content","update"),("content","feedback"),
#                  ("content","promote"),("board","read"),("board","write"),("board","update")},
#     "external": {("content","update"),("content","feedback"),("content","promote")},
# }

# def wipe():
#     print("Wiping data...")
#     Discussion.objects.all().delete()
#     TaskHistory.objects.all().delete()
#     Task.objects.all().delete()
#     Event.objects.all().delete()
#     Campaign.objects.all().delete()
#     ContentComment.objects.all().delete()
#     ContentAssignment.objects.all().delete()
#     ContentVersion.objects.all().delete()
#     Content.objects.all().delete()
#     RBAC.objects.all().delete()
#     User.objects.all().delete()
#     Group.objects.all().delete()
#     print("Done.")

# def seed_users():
#     users = {}
#     for d in USERS_DEF:
#         user = User.objects.create(
#             email=d["email"], full_name=d["name"],
#             group=d["group"], role=d["role"],
#             is_staff=d["staff"], is_superuser=d["staff"], is_active=True,
#         )
#         user.set_password(PASSWORD)
#         user.save()

#         dg, _ = Group.objects.get_or_create(name=d["group"].capitalize())
#         user.groups.add(dg)

#         RBAC.objects.filter(application_group=dg).delete()
#         for area, action in RBAC_MAP.get(d["group"], set()):
#             RBAC.objects.get_or_create(application_group=dg, application_area=area, application_action=action)

#         print(f"  Created {d['email']} ({d['role']})")
#         users[d["role"]] = user

#     users["admin"] = User.objects.get(email="admin@platform.com")
#     return users

# def seed_content(users):
#     admin, writer, reviewer = users["admin"], users["writer"], users["reviewer"]
#     sme, exec_u = users["sme"], users["exec_approver"]

#     contents = []
#     for title, status, lock in [
#         ("Introduction to Cloud Computing", "draft", False),
#         ("Python Best Practices", "pending_reviewer", False),
#         ("Security Fundamentals", "pending_executive", False),
#         ("Docker Deep Dive", "published", False),
#     ]:
#         c = Content.objects.create(title=title, body=f"Body of {title}.", author=writer, status=status)
#         if lock:
#             c.locked_by = writer
#             c.save()
#         ContentVersion.objects.create(content=c, title=title, body=c.body, changed_by=writer)
#         print(f"  Content [{status}] {title}")
#         contents.append(c)

#     return contents

# def seed_board(users):
#     admin, writer, reviewer = users["admin"], users["writer"], users["reviewer"]
#     exec_u = users["exec_approver"]

#     # Campaign 1 — max 2 levels (root + 1 subtask level)
#     camp1 = Campaign.objects.create(
#         title="Q2 Marketing Campaign", description="All Q2 marketing activities.",
#         created_by=admin, max_hierarchy_level=2,
#     )
#     print(f"  Campaign: {camp1.title} (max_level={camp1.max_hierarchy_level})")

#     # Campaign 2 — max 3 levels
#     camp2 = Campaign.objects.create(
#         title="Product Launch 2026", description="Product launch campaign.",
#         created_by=admin, max_hierarchy_level=3,
#     )
#     print(f"  Campaign: {camp2.title} (max_level={camp2.max_hierarchy_level})")

#     # Events under campaign 1
#     ev1 = Event.objects.create(campaign=camp1, title="Social Media Week", created_by=admin)
#     ev2 = Event.objects.create(campaign=camp1, title="Email Campaign Sprint", created_by=admin)
#     print(f"  Events: {ev1.title}, {ev2.title}")

#     # Root task under campaign 1, event 1
#     t1 = Task.objects.create(
#         campaign=camp1, event=ev1, title="Design social media assets",
#         priority="high", status="in_progress",
#         assigned_by=admin, assigned_to=writer,
#     )
#     TaskHistory.objects.create(task=t1, action="created", performed_by=admin, detail="Created")
#     print(f"  Task (depth=1): {t1.title}")

#     # Subtask of t1 (depth=2, allowed since max=2)
#     t1a = Task.objects.create(
#         campaign=camp1, event=ev1, parent_task=t1,
#         title="Design Instagram stories",
#         priority="medium", status="to_do",
#         assigned_by=admin, assigned_to=writer,
#     )
#     TaskHistory.objects.create(task=t1a, action="created", performed_by=admin, detail="Subtask created")
#     print(f"  Subtask (depth=2): {t1a.title}")

#     # Root task directly under campaign (no event)
#     t2 = Task.objects.create(
#         campaign=camp1, title="Campaign strategy document",
#         priority="high", status="to_do",
#         assigned_by=admin, assigned_to=reviewer,
#     )
#     TaskHistory.objects.create(task=t2, action="created", performed_by=admin, detail="Created")
#     print(f"  Task under campaign directly (no event): {t2.title}")

#     # Campaign 2 — 3-level hierarchy
#     ev3 = Event.objects.create(campaign=camp2, title="Launch Event", created_by=admin)
#     t3 = Task.objects.create(
#         campaign=camp2, event=ev3, title="Prepare launch materials",
#         priority="high", status="to_do", assigned_by=admin, assigned_to=writer,
#     )
#     t3a = Task.objects.create(
#         campaign=camp2, event=ev3, parent_task=t3,
#         title="Write product description", priority="medium", status="to_do",
#         assigned_by=admin, assigned_to=writer,
#     )
#     t3a1 = Task.objects.create(
#         campaign=camp2, event=ev3, parent_task=t3a,
#         title="Draft v1", priority="low", status="to_do",
#         assigned_by=admin, assigned_to=writer,
#     )
#     print(f"  3-level subtasks: {t3.title} → {t3a.title} → {t3a1.title}")

#     # Discussion on t1
#     Discussion.objects.create(task=t1, author=admin, message="Please follow brand guidelines.")
#     Discussion.objects.create(task=t1, author=writer, message="Will have first draft ready by Friday.")

# def main():
#     wipe()
#     users = seed_users()
#     seed_content(users)
#     seed_board(users)
#     print("\n=== SEED COMPLETE ===")
#     print("Credentials (all: Pass123!)")
#     print("  admin@platform.com    — admin")
#     print("  exec@platform.com     — exec_approver")
#     print("  writer@platform.com   — writer")
#     print("  reviewer@platform.com — reviewer")
#     print("  sme@platform.com      — sme")

# if __name__ == "__main__":
#     main()
