"""
seed_data.py  —  Merged Platform (Fresh Seed)
===============================================
Wipes and recreates all test data for accounts, content, and board.

Run:
    python seed_data.py

Users created (all passwords: Pass123!):
    admin@platform.com      → admin / admin
    exec@platform.com       → executive / exec_approver
    writer@platform.com     → internal / writer
    reviewer@platform.com   → internal / reviewer
    sme@platform.com        → external / sme
"""

import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import Group
from accounts.models import User, RBAC
from content.models import (
    Article, ArticleVersion,
    ArticleComment, ArticleAssignment,
)
from board.models import Task, TaskHistory, Discussion

PASSWORD = "Pass123!"


# ==============================================================================
# HELPERS
# ==============================================================================

def wipe():
    print("\n🗑️  Wiping existing data...")
    Discussion.objects.all().delete()
    TaskHistory.objects.all().delete()
    Task.objects.all().delete()
    ArticleComment.objects.all().delete()
    ArticleAssignment.objects.all().delete()
    ArticleVersion.objects.all().delete()
    Article.objects.all().delete()
    RBAC.objects.all().delete()
    User.objects.all().delete()
    Group.objects.all().delete()
    print("   Done.\n")

def seed_rbac(django_group, group, role):
    RBAC.objects.filter(application_group=django_group).delete()

    if group == 'admin':
        for area in ['content', 'board', 'users', 'reports', 'settings']:
            RBAC.objects.get_or_create(
                application_group=django_group,
                application_area=area,
                application_action='admin',
            )

    elif group == 'executive':
        for action in ['read', 'feedback', 'promote']:
            RBAC.objects.get_or_create(
                application_group=django_group,
                application_area='content',
                application_action=action,
            )
        for action in ['read', 'write', 'update']:
            RBAC.objects.get_or_create(
                application_group=django_group,
                application_area='board',
                application_action=action,
            )

    elif group == 'internal':
        if role == 'writer':
            for action in ['write', 'update']:
                RBAC.objects.get_or_create(
                    application_group=django_group,
                    application_area='content',
                    application_action=action,
                )
            for action in ['read', 'write', 'update']:
                RBAC.objects.get_or_create(
                    application_group=django_group,
                    application_area='board',
                    application_action=action,
                )
        elif role == 'reviewer':
            for action in ['update', 'feedback', 'promote']:
                RBAC.objects.get_or_create(
                    application_group=django_group,
                    application_area='content',
                    application_action=action,
                )
            for action in ['read', 'write', 'update']:
                RBAC.objects.get_or_create(
                    application_group=django_group,
                    application_area='board',
                    application_action=action,
                )

    elif group == 'external' and role == 'sme':
        for action in ['update', 'feedback', 'promote']:
            RBAC.objects.get_or_create(
                application_group=django_group,
                application_area='content',
                application_action=action,
            )


# ==============================================================================
# SECTION 1 — USERS + RBAC
# ==============================================================================

USERS_DEF = [
    {
        "email": "admin@platform.com",    "name": "System Admin",
        "group": "admin",     "role": "admin",
        "is_staff": True,  "is_super": True,
    },
    {
        "email": "exec@platform.com",     "name": "Executive Boss",
        "group": "executive", "role": "exec_approver",
        "is_staff": False, "is_super": False,
    },
    {
        "email": "writer@platform.com",   "name": "Alice Writer",
        "group": "internal",  "role": "writer",
        "is_staff": False, "is_super": False,
    },
    {
        "email": "reviewer@platform.com", "name": "Bob Reviewer",
        "group": "internal",  "role": "reviewer",
        "is_staff": False, "is_super": False,
    },
    {
        "email": "sme@platform.com",      "name": "Charlie Expert",
        "group": "external",  "role": "sme",
        "is_staff": False, "is_super": False,
    },
]


def seed_users():
    print("── USERS + RBAC ──────────────────────────────────────")
    users = {}

    for data in USERS_DEF:
        user = User.objects.create(
            email         = data['email'],
            full_name     = data['name'],
            group         = data['group'],
            role          = data['role'],
            is_staff      = data['is_staff'],
            is_superuser  = data['is_super'],
            is_active     = True,
        )
        user.set_password(PASSWORD)
        user.save()

        dg, _ = Group.objects.get_or_create(name=data['group'].capitalize())
        user.groups.add(dg)
        seed_rbac(dg, data['group'], data['role'])

        print(f"  ✅  {data['email']:32s}  ({data['group']} / {data['role']})")
        users[data['role']] = user

    # admin is stored under both keys
    users['admin'] = User.objects.get(email='admin@platform.com')
    return users


# ==============================================================================
# SECTION 2 — CONTENT
# ==============================================================================

def seed_content(users):
    print("\n── CONTENT ───────────────────────────────────────────")

    admin    = users['admin']
    exec_u   = users['exec_approver']
    writer   = users['writer']
    reviewer = users['reviewer']
    sme      = users['sme']
    now      = timezone.now()

    # ── Articles ──────────────────────────────────────────────────────────────

    articles_def = [
        {
            "title":  "Introduction to AI",
            "content": (
                "Artificial Intelligence (AI) refers to the simulation of human intelligence in machines "
                "programmed to think and learn. This article covers foundational concepts including machine "
                "learning, neural networks, and natural language processing. AI systems are increasingly used "
                "across industries — from healthcare diagnostics to autonomous vehicles. Understanding AI "
                "fundamentals is essential for any modern software professional. We cover supervised vs "
                "unsupervised learning, the role of training data, model evaluation metrics, and common "
                "pitfalls like overfitting and data bias."
            ),
            "author": writer,
            "status": "draft",
            "lock":   False,
        },
        {
            "title":  "Cloud Architecture Guide",
            "content": (
                "Cloud architecture defines how technology components combine to build a scalable cloud system. "
                "This guide covers IaaS, PaaS, and SaaS models with practical examples on AWS, Azure, and GCP. "
                "Topics include load balancing strategies, auto-scaling policies, multi-region deployments, "
                "and disaster recovery planning. We compare managed vs self-hosted databases, discuss CDN "
                "integration, and provide cost optimisation frameworks."
            ),
            "author": writer,
            "status": "pending_executive",
            "lock":   False,
        },
        {
            "title":  "Security Best Practices",
            "content": (
                "Security in software systems is foundational, not optional. This article covers the OWASP "
                "Top 10 vulnerabilities with real code examples showing the vulnerability and the fix. We "
                "cover secure coding in Python and Django, authentication mechanisms including JWT, OAuth2, "
                "and API keys, rate limiting, input validation, and SQL injection prevention."
            ),
            "author": writer,
            "status": "pending_admin",
            "lock":   False,
        },
        {
            "title":  "Python Performance Tips",
            "content": (
                "Python is loved for readability but often criticised for performance. This article explores "
                "advanced optimisation techniques: profiling with cProfile and py-spy, using NumPy for "
                "vectorised numerical computation, leveraging multiprocessing and asyncio for concurrency, "
                "compiling hot paths with Cython, and using Redis for caching expensive computations. "
                "Every technique includes before/after benchmarks."
            ),
            "author": writer,
            "status": "published",
            "lock":   False,
        },
        {
            "title":  "Docker for Beginners",
            "content": (
                "Docker revolutionised how we package and ship software. This beginner guide walks through "
                "core Docker concepts: images, containers, volumes, and networks. We build a complete Django "
                "plus Postgres plus Redis application step by step, writing each Dockerfile and explaining "
                "every instruction. Docker Compose is introduced for multi-container orchestration."
            ),
            "author": writer,
            "status": "draft",
            "lock":   True,   # locked by writer — simulates active editing
        },
    ]

    articles = []
    for data in articles_def:
        article = Article.objects.create(
            title   = data['title'],
            content = data['content'],
            author  = data['author'],
            status  = data['status'],
        )
        if data['lock']:
            article.locked_by = writer
            article.locked_at = now
            article.save()

        # Initial version for every article
        ArticleVersion.objects.create(
            article    = article,
            title      = article.title,
            content    = article.content,
            changed_by = writer,
        )
        print(f"  ✅  Article  [{article.status:20s}]  '{article.title}'")
        articles.append(article)

    a1, a2, a3, a4, a5 = articles

    # ── Extra versions ─────────────────────────────────────────────────────────

    ArticleVersion.objects.create(
        article    = a2,
        title      = "Cloud Architecture Guide — Draft 2",
        content    = a2.content + "\n\n[Revision: Added cost comparison table and updated GCP pricing.]",
        changed_by = writer,
    )
    ArticleVersion.objects.create(
        article    = a2,
        title      = "Cloud Architecture Guide — SME Review",
        content    = a2.content + "\n\n[SME: Verified technical accuracy of load balancing section.]",
        changed_by = sme,
    )
    ArticleVersion.objects.create(
        article    = a3,
        title      = "Security Best Practices — Reviewer Edit",
        content    = a3.content + "\n\n[Reviewer: Added zero-trust architecture section.]",
        changed_by = reviewer,
    )
    print("  ✅  Extra versions added for Articles 2 and 3")

    # ── SME Assignments ────────────────────────────────────────────────────────

    for article in [a1, a2, a3]:
        ArticleAssignment.objects.create(
            article     = article,
            sme         = sme,
            assigned_by = reviewer,
        )
    print("  ✅  SME (Charlie Expert) assigned to Articles 1, 2, 3")

    # ── Comments ──────────────────────────────────────────────────────────────

    comments = [
        (a1, reviewer, "The introduction needs a concrete example. @[Alice Writer](3) please add a real-world ML use case in section 1."),
        (a1, sme,      "Technical accuracy is solid. The neural networks section is well explained."),
        (a1, reviewer, "Also add references to the foundational papers (Turing 1950, LeCun 1998)."),
        (a2, exec_u,   "Good structure. The cost comparison section needs updating — AWS prices changed in Q1."),
        (a2, reviewer, "Multi-region architecture section is excellent. Approved from the technical side."),
        (a3, admin,    "Final review done. Minor formatting issue on the OWASP table. @[Alice Writer](3) please fix before publishing."),
        (a4, reviewer, "Outstanding article. The benchmarks are clear and the asyncio section is particularly well written."),
        (a4, exec_u,   "Exactly the kind of deep-dive content we need. Well done."),
        (a5, reviewer, "@[Alice Writer](3) make sure to cover Docker networking in depth — that is where beginners get stuck most."),
    ]

    for article, commenter, text in comments:
        latest_v = ArticleVersion.objects.filter(article=article).order_by('-created_at').first()
        ArticleComment.objects.create(
            article      = article,
            user         = commenter,
            comment_text = text,
            version      = latest_v,
        )
    print(f"  ✅  {len(comments)} comments created across articles")

# ==============================================================================
# SECTION 3 — BOARD
# ==============================================================================

def seed_board(users):
    print("\n── BOARD ─────────────────────────────────────────────")

    admin    = users['admin']
    exec_u   = users['exec_approver']
    writer   = users['writer']
    reviewer = users['reviewer']

    tasks_def = [
        {
            "title":          "Design homepage mockup",
            "description":    "Create wireframes and high-fidelity mockups for the new homepage in Figma. Include desktop and mobile breakpoints. Share the Figma link in discussion when first draft is ready.",
            "status":         "to_do",
            "priority":       "high",
            "tags":           "design,figma,homepage,ui",
            "marketing_type": "Brand",
            "due_date":       "2026-04-30",
            "assigned_by":    admin,
            "assigned_to":    writer,
            "transferred":    False,
        },
        {
            "title":          "Write API documentation",
            "description":    "Document all REST endpoints using OpenAPI/Swagger format. Cover request bodies, response schemas, error codes, and auth headers. Include curl examples for every endpoint.",
            "status":         "in_progress",
            "priority":       "medium",
            "tags":           "docs,api,swagger",
            "marketing_type": "Technical",
            "due_date":       "2026-04-15",
            "assigned_by":    admin,
            "assigned_to":    writer,
            "transferred":    False,
        },
        {
            "title":          "Fix login page OTP bug",
            "description":    "Users report that OTP codes starting with 0 are rejected by the frontend validator. Reproduce the bug, fix the input validation logic, and add a regression test.",
            "status":         "in_progress",
            "priority":       "high",
            "tags":           "bug,auth,otp,frontend",
            "marketing_type": "",
            "due_date":       "2026-04-10",
            "assigned_by":    reviewer,
            "assigned_to":    exec_u,
            "transferred":    True,
            "transferred_by": writer,
        },
        {
            "title":          "Review pull request #42",
            "description":    "PR #42 introduces the ArticleDraft system with auto-save. Review migration safety, verify the upsert logic, test the commit flow end to end.",
            "status":         "completed",
            "priority":       "medium",
            "tags":           "review,pr,content,draft",
            "marketing_type": "Technical",
            "due_date":       "2026-03-28",
            "assigned_by":    admin,
            "assigned_to":    reviewer,
            "transferred":    False,
        },
        {
            "title":          "Set up CI/CD pipeline",
            "description":    "Configure GitHub Actions for automated testing and deployment. Pipeline should run the full test suite on every push to main and deploy to staging on merge.",
            "status":         "to_do",
            "priority":       "medium",
            "tags":           "devops,cicd,github-actions",
            "marketing_type": "Technical",
            "due_date":       "2026-05-15",
            "assigned_by":    admin,
            "assigned_to":    exec_u,
            "transferred":    False,
        },
        {
            "title":          "Database performance audit",
            "description":    "Run EXPLAIN ANALYZE on the 10 slowest queries identified in monitoring. Add missing indexes, resolve N+1 query patterns, and document all findings in a report.",
            "status":         "completed",
            "priority":       "high",
            "tags":           "database,performance,postgres,indexing",
            "marketing_type": "Technical",
            "due_date":       "2026-03-20",
            "assigned_by":    exec_u,
            "assigned_to":    admin,
            "transferred":    False,
        },
        {
            "title":          "Write unit tests for board app",
            "description":    "Achieve minimum 80% test coverage on the board app. Prioritise: task creation, transfer logic, stage validation, and discussion CRUD. Use pytest-django and factory_boy.",
            "status":         "in_progress",
            "priority":       "medium",
            "tags":           "testing,pytest,board,coverage",
            "marketing_type": "Technical",
            "due_date":       "2026-04-25",
            "assigned_by":    admin,
            "assigned_to":    reviewer,
            "transferred":    False,
        },
        {
            "title":          "Q2 Social Media Campaign",
            "description":    "Plan and schedule the Q2 social media campaign across LinkedIn, Twitter, and Instagram. Coordinate with the design team for assets.",
            "status":         "blocked",
            "priority":       "high",
            "tags":           "social,campaign,q2,marketing",
            "marketing_type": "Social Media",
            "due_date":       "2026-04-01",
            "assigned_by":    exec_u,
            "assigned_to":    writer,
            "transferred":    False,
        },
        {
            "title":          "Launch blog post for new feature",
            "description":    "Write and publish the launch blog post announcing the new draft auto-save feature. Include screenshots, benefits, and a call to action.",
            "status":         "approved",
            "priority":       "low",
            "tags":           "blog,content,launch,writing",
            "marketing_type": "Blog",
            "due_date":       "2026-03-25",
            "assigned_by":    admin,
            "assigned_to":    writer,
            "transferred":    False,
        },
    ]

    created_tasks = []

    for data in tasks_def:
        task = Task.objects.create(
            title                = data['title'],
            description          = data['description'],
            status               = data['status'],
            priority             = data['priority'],
            tags                 = data['tags'],
            marketing_type       = data['marketing_type'],
            due_date             = data['due_date'] or None,
            assigned_by          = data['assigned_by'],
            assigned_to          = data['assigned_to'],
            last_transferred_by  = data.get('transferred_by') if data['transferred'] else None,
        )

        # created history entry
        TaskHistory.objects.create(
            task         = task,
            action       = 'created',
            performed_by = data['assigned_by'],
            detail       = f"Task created and assigned to {data['assigned_to'].full_name} ({data['assigned_to'].email})",
        )

        # transfer history entry
        if data['transferred']:
            TaskHistory.objects.create(
                task         = task,
                action       = 'transferred',
                performed_by = data['transferred_by'],
                detail       = (
                    f"Transferred from {data['transferred_by'].full_name} "
                    f"to {data['assigned_to'].full_name} ({data['assigned_to'].email})"
                ),
            )

        # stage change history
        if data['status'] in ('in_progress', 'completed', 'blocked', 'approved'):
            TaskHistory.objects.create(
                task         = task,
                action       = 'stage_changed',
                performed_by = data['assigned_to'],
                detail       = "Status changed from 'to_do' to 'in_progress'",
            )

        if data['status'] in ('completed', 'approved'):
            TaskHistory.objects.create(
                task         = task,
                action       = 'stage_changed',
                performed_by = data['assigned_to'],
                detail       = f"Status changed from 'in_progress' to '{data['status']}'",
            )

        if data['status'] == 'blocked':
            TaskHistory.objects.create(
                task         = task,
                action       = 'stage_changed',
                performed_by = data['assigned_to'],
                detail       = "Status changed to 'blocked' — waiting on design assets",
            )

        print(f"  ✅  Task  [{data['status']:12s}]  [{data['priority']:6s}]  '{data['title']}'")
        created_tasks.append(task)

    t1, t2, t3, t4, t5, t6, t7, t8, t9 = created_tasks

    # ── Discussion comments ────────────────────────────────────────────────────

    discussions = [
        (t1, admin,    "Please check the brand guidelines doc in Notion before starting the mockups."),
        (t1, writer,   "Got it. I will have the first wireframes ready by end of this week."),
        (t1, reviewer, "Make sure mobile version is completed first — higher priority for the launch."),

        (t2, admin,    "Use the request.rest file as the reference for all current endpoints."),
        (t2, writer,   "Started on the auth and accounts sections. Board and content will follow."),
        (t2, exec_u,   "Can you add expected response times to each endpoint? That will help the frontend team."),
        (t2, writer,   "Good idea — will add performance notes in the next pass."),

        (t3, reviewer, "Reproduced on Chrome and Firefox. The validator strips leading zeros from the OTP field."),
        (t3, writer,   "Transferring to you — notes are in the PR. Fix is in the OTP field validator."),
        (t3, exec_u,   "Got it. Will push a fix by EOD."),

        (t4, reviewer, "Migration is safe. Auto-save upsert logic is clean. Add index on author+status for faster draft loading."),
        (t4, admin,    "Good catch — that index was added in migration 0007. Approved and merged."),

        (t5, exec_u,   "Starting with GitHub Actions workflow. Using the official Django action as base template."),
        (t5, admin,    "Store all secrets in GitHub Secrets — never hardcode in the yml file."),

        (t6, admin,    "Found 3 missing indexes. Added and tested. Query time dropped from 800ms to 12ms."),
        (t6, exec_u,   "Excellent result. Please share the full before/after report in the engineering channel."),

        (t7, reviewer, "Starting with transfer logic tests — most complex part with the most edge cases."),
        (t7, admin,    "Use factory_boy for test data — saves a lot of boilerplate."),
        (t7, reviewer, "Currently at 62% coverage. Stage change and discussion CRUD tests are next."),

        (t8, exec_u,   "Blocked because design assets are not ready yet. Waiting on the design team."),
        (t8, writer,   "Will follow up with design today."),

        (t9, admin,    "Blog post approved. Great work — clear and engaging. Published to the site."),
        (t9, writer,   "Thanks! Happy to write more launch posts going forward."),
    ]

    for task, author, message in discussions:
        Discussion.objects.create(task=task, author=author, message=message)

    print(f"  ✅  {len(discussions)} discussion comments created across 9 tasks")


# ==============================================================================
# MAIN
# ==============================================================================

def seed():
    print("\n" + "═" * 60)
    print("  🌱  MERGED PLATFORM — FRESH SEED")
    print("═" * 60)

    wipe()
    users    = seed_users()
    articles = seed_content(users)
    seed_board(users)

    print("\n" + "═" * 60)
    print("  ✅  SEED COMPLETE")
    print("═" * 60)
    print()
    print("  CREDENTIALS  (all passwords: Pass123!)")
    print("  ────────────────────────────────────────────────────")
    print("  admin@platform.com      id=1  admin        full access")
    print("  exec@platform.com       id=2  exec_approver content + board")
    print("  writer@platform.com     id=3  writer        content + board")
    print("  reviewer@platform.com   id=4  reviewer      content + board")
    print("  sme@platform.com        id=5  sme           content only")
    print()
    print("  CONTENT")
    print("  ────────────────────────────────────────────────────")
    print("  Article 1  draft              Introduction to AI")
    print("  Article 2  pending_executive  Cloud Architecture Guide")
    print("  Article 3  pending_admin      Security Best Practices")
    print("  Article 4  published          Python Performance Tips")
    print("  Article 5  draft (locked)     Docker for Beginners")
    print("  Draft 1    writing (no art.)  Kubernetes for Production")
    print("  Draft 2    writing (art.=1)   Editing Intro to AI")
    print("  Draft 3    submitted (art.=2) Cloud Architecture Guide")
    print()
    print("  BOARD  (9 tasks — all new fields populated)")
    print("  ────────────────────────────────────────────────────")
    print("  Task 1  to_do        high    Design homepage mockup")
    print("  Task 2  in_progress  medium  Write API documentation")
    print("  Task 3  in_progress  high    Fix login page OTP bug  [transferred]")
    print("  Task 4  completed    medium  Review pull request #42")
    print("  Task 5  to_do        medium  Set up CI/CD pipeline")
    print("  Task 6  completed    high    Database performance audit")
    print("  Task 7  in_progress  medium  Write unit tests for board app")
    print("  Task 8  blocked      high    Q2 Social Media Campaign")
    print("  Task 9  approved     low     Launch blog post for new feature")
    print("═" * 60)
    print()


if __name__ == "__main__":
    seed()