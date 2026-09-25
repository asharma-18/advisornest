import os
import threading
import requests
from datetime import datetime, timezone


def send_fallback_alert(client_name, advisor_email, reason):
    """
    Fires the alert email in a background thread so it can never
    hold up or crash the actual recommendation request.
    """
    thread = threading.Thread(
        target=_send_email,
        args=(client_name, advisor_email, reason),
        daemon=True
    )
    thread.start()


def _send_email(client_name, advisor_email, reason):
    api_key = os.getenv("RESEND_API_KEY")
    recipient = os.getenv("ALERT_RECIPIENT_EMAIL")

    if not api_key or not recipient:
        print("Fallback alert email skipped — RESEND_API_KEY / ALERT_RECIPIENT_EMAIL not set")
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

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": "AdvisorNest Alerts <onboarding@resend.dev>",
                "to": [recipient],
                "subject": subject,
                "text": body,
            },
            timeout=10
        )
        if response.status_code == 200:
            print(f"Fallback alert email sent for client: {client_name}")
        else:
            print(f"Failed to send fallback alert email: {response.status_code} {response.text}")
    except Exception as e:
        print(f"Failed to send fallback alert email: {str(e)}")