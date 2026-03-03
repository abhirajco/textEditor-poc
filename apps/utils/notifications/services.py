import random
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.settings import EMAIL_HOST_USER
from rest_framework.response import Response
import re
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from accounts.models import User
from content.models import ArticleAssignment


def send_otp_via_email(email, pending_data):
    # 1. Generate 6 digit code
    otp = random.randint(100000, 999999)

    # 2. Store EVERYTHING in Redis (OTP + Name + Hashed Password)
    # We use the email as the key so we can find it in the Verify step
    cache_key = f"otp_auth_{email}"
    
    # Bundle the data
    data_to_cache = {
        "otp": otp,
        "full_name": pending_data["full_name"],
        "password": pending_data["password"], # This is already hashed from the view
    }

    # Set in Redis with 10-minute expiry (600 seconds)
    cache.set(cache_key, data_to_cache, timeout=600)

    # 3. Debugging/Logging
    print(f"\n--- REDIS DEBUG: Key {cache_key} saved with OTP {otp} ---")

    # 4. Send the Email
    subject = "Your InSight Verification Code"
    message = f"Your OTP is {otp}. It will expire in 10 minutes."
    email_from = EMAIL_HOST_USER
    send_mail(subject, message, email_from, [email])


def handle_mentions_and_notifications(text, article_obj, sender):
    """
    Finds @user@company.com in text, increments Redis, and sends an email.
    """
    mention_pattern = r'@([\w\.-]+@[\w\.-]+\.\w+)'
    emails = re.findall(mention_pattern, text)

    print(emails)
    
    for email in emails:
        try:
            tagged_user = User.objects.get(email=email)
            article_obj.mentions.add(tagged_user)
            
            # 1. Update Redis (Unread UI badge)
            redis_key = f"unread_mentions:{tagged_user.id}"
            cache.get_or_set(redis_key, 0)
            cache.incr(redis_key)
            
            # 2. Send Actual Email
            subject = f"You were tagged in {article_obj.title}"
            body = f"Hello {tagged_user.full_name},\n\nYou were tagged by {sender.full_name} in a comment on '{article_obj.title}'.\n\nComment: {text}"
            email_from = EMAIL_HOST_USER

            send_mail(subject, body, email_from, [email] , fail_silently=True)
            
        # except User.DoesNotExist:
        #     continue

        except Exception as e:
            print(e)


def send_approval_emails(target_role, article):
    """Sends bulk emails when article status changes."""
    users = User.objects.filter(role=target_role)
    email_list = [user.email for user in users]
    
    subject=f"Action Required: {article.title} is ready for your review",
    body=f"The article '{article.title}' has been moved to {article.status}.",
    email_from = EMAIL_HOST_USER
    # print("ok")
    try:
        send_mail(
            subject,
            body,
            email_from,
            recipient_list=email_list,
            fail_silently=True
        )
    except Exception as e:
        print(str(e))
        return Response({"error": str(e)})


def send_assigned_sme_emails(article):
    """Sends emails ONLY to SMEs specifically assigned to this article."""
    
    
    # Get all assignments for this article
    assignments = ArticleAssignment.objects.filter(article=article).select_related('sme')
    
    # Extract emails of the assigned SMEs
    email_list = [asgn.sme.email for asgn in assignments if asgn.sme.is_active]
    
    if email_list:
        send_mail(
            subject=f"Action Required: You have been assigned to '{article.title}'",
            message=f"Hello, you are the appointed SME for the article '{article.title}'. Please review it at your earliest convenience.",
            from_email=EMAIL_HOST_USER,
            recipient_list=email_list,
            fail_silently=True
        )