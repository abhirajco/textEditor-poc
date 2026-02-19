import random
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from accounts.models import EmailOTP
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.settings import EMAIL_HOST_USER
from rest_framework.response import Response
from django.core.cache import cache


#uses redis to save otp
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
    email_from = settings.EMAIL_HOST_USER
    send_mail(subject, message, email_from, [email])
#uses database to save otp
# def send_otp_via_email(email , pending_data):
#     # Generate 6 digit code
#     otp = random.randint(100000, 999999)

#     full_name = pending_data["full_name"]
#     password = pending_data["password"]
    
#     #save this emailotp table
#     EmailOTP.objects.update_or_create(
#             email=email,
#             defaults={
#                 'otp': otp, 
#                 'full_name': full_name, 
#                 'password': password,
#                 'created_at': timezone.now()
#             }
#         )
#     print(f"\n--- DEBUG: OTP for {email} is {otp} ---\n")

#     print(email , password , full_name , otp)
#     # Send to console (since we set EMAIL_BACKEND to console in settings)
#     subject = "Your Verification Code"
#     message = f"Your OTP is {otp}"
#     email_from = settings.EMAIL_HOST_USER
#     send_mail(subject, message, email_from, [email])


def notify_approvers(article_title, writer_name , action):

    User = get_user_model()

    approver_emails = list(
        User.objects.filter(role='approver').values_list('email', flat=True)
    )

    if(action=="write"):
        s = f"New Draft: {article_title}",
        b = f"Writer {writer_name} has created a draft. Please review and vote.",
    
    else:
        s=f"New Edit: {article_title}",
        b=f"Writer {writer_name} has updated the draft. Please review and vote.",
        
    try:
        print(EMAIL_HOST_USER)
        send_mail(
        subject=s,
        message=b,
        from_email= EMAIL_HOST_USER,
        recipient_list=approver_emails,
        fail_silently=True,
    )
    except Exception as e:
        return Response({str(e)})
