import os
import smtplib
import threading
from email.mime.text import MIMEText
from datetime import datetime, timezone


def send_fallback_alert(client_name, advisor_email, reason):
    """
    Fires the alert email in a background thread so a slow or blocked
    SMTP connection can NEVER hang or crash the actual recommendation
    request again. The advisor's response is returned immediately;
    the email attempt happens separately.
    """
    thread = threading.Thread(
        target=_send_email,
        args=(client_name, advisor_email, reason),
        daemon=True
    )
    thread.start()


def _send_email(client_name, advisor_email, reason):
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
        # timeout=10 — fail fast instead of hanging if the host blocks SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        print(f"Fallback alert email sent for client: {client_name}")
    except Exception as e:
        print(f"Failed to send fallback alert email: {str(e)}")