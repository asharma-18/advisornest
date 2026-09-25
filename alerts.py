import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone


def send_fallback_alert(client_name, advisor_email, reason):
    """
    Sends a quiet email to you (the admin) whenever a recommendation
    used rule-based fallback instead of full AI generation — either
    partially (some options) or fully (all 4 options).

    Requires these Railway environment variables to be set:
    - ALERT_SENDER_EMAIL          (a Gmail address you control)
    - ALERT_SENDER_APP_PASSWORD   (a Gmail "App Password", not your normal password)
    - ALERT_RECIPIENT_EMAIL       (optional — where the alert goes; defaults to the sender address)

    If these aren't set, it just logs to the console instead of crashing
    anything — a missing alert should never break a recommendation.
    """
    sender = os.getenv("ALERT_SENDER_EMAIL")
    password = os.getenv("ALERT_SENDER_APP_PASSWORD")
    recipient = os.getenv("ALERT_RECIPIENT_EMAIL", sender)

    if not sender or not password:
        print("Fallback alert email skipped — ALERT_SENDER_EMAIL / ALERT_SENDER_APP_PASSWORD not set")
        return

    subject = f"AdvisorNest: AI fallback used for {client_name}"
    body = (
        f"Time (UTC): {datetime.now(timezone.utc).isoformat()}\n"
        f"Client: {client_name}\n"
        f"Advisor: {advisor_email}\n"
        f"Reason: {reason}\n\n"
        f"A recommendation for this client used rule-based fallback "
        f"instead of full AI generation. Check Railway logs for the "
        f"'Option X attempt N' lines around this time to see the exact cause."
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        print(f"Fallback alert email sent for client: {client_name}")
    except Exception as e:
        # Never let a failed alert email break the actual recommendation flow
        print(f"Failed to send fallback alert email: {str(e)}")

        