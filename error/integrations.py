import sys
import os
import json
import urllib.request
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional, List

from error.suggestions import SuggestionEngine
from error.formatting import Formatter

# Global configurations for integrations
_slack_webhook: Optional[str] = None
_sentry_dsn: Optional[str] = None
_email_config: Optional[Dict[str, Any]] = None  # host, port, username, password, sender, recipient

def configure_integrations(
    slack_webhook: Optional[str] = None,
    sentry_dsn: Optional[str] = None,
    email_config: Optional[Dict[str, Any]] = None
):
    """Configures global credentials/webhooks for Sentry, Slack, and Email notifications."""
    global _slack_webhook, _sentry_dsn, _email_config
    if slack_webhook is not None:
        _slack_webhook = slack_webhook
    if sentry_dsn is not None:
        _sentry_dsn = sentry_dsn
    if email_config is not None:
        _email_config = email_config

def notify_slack(exc: BaseException, webhook_url: Optional[str] = None) -> bool:
    """
    Sends a beautifully structured notification block payload to a Slack Webhook.
    Uses standard library urllib.request to avoid external library dependencies.
    """
    url = webhook_url or _slack_webhook
    if not url:
        sys.stderr.write("⚠️ error.notify_slack: No webhook URL provided or configured.\n")
        return False
        
    details = SuggestionEngine.get_details(exc)
    severity = getattr(exc, "__severity__", "ERROR").upper()
    
    # Slack Blocks payload
    payload = {
        "text": f"🚨 {details['name']} raised: {details['message']}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 [{severity}] {details['name']}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error Message:*\n`{details['message']}`\n\n*Explanation:*\n{details['translation']}\n\n*Why:*\n{details['why']}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🛠️ Actionable Suggestions:*\n" + "\n".join(f"• {s}" for s in details["suggestions"])
                }
            }
        ]
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        sys.stderr.write(f"⚠️ error.notify_slack: Failed to send Slack alert: {e}\n")
        return False

def notify_sentry(exc: BaseException, dsn: Optional[str] = None) -> bool:
    """
    Integrates with Sentry. If the official sentry_sdk is installed, it forwards 
    the exception to Sentry, otherwise logs a local warning.
    """
    target_dsn = dsn or _sentry_dsn
    try:
        import sentry_sdk
        if target_dsn and not sentry_sdk.Hub.current.client:
            sentry_sdk.init(dsn=target_dsn)
        sentry_sdk.capture_exception(exc)
        return True
    except ImportError:
        # Fallback if SDK not installed: mock send via raw API or print log
        sys.stderr.write("⚠️ error.notify_sentry: sentry_sdk is not installed. Exception details logged locally.\n")
        return False
    except Exception as e:
        sys.stderr.write(f"⚠️ error.notify_sentry: Failed to report to Sentry: {e}\n")
        return False

def send_email(exc: BaseException, config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Sends a premium HTML error report email to the configured recipient
    using standard SMTP mail routing.
    """
    email_cfg = config or _email_config
    if not email_cfg:
        sys.stderr.write("⚠️ error.send_email: No email configuration provided.\n")
        return False
        
    required_keys = ["host", "port", "sender", "recipient"]
    if not all(k in email_cfg for k in required_keys):
        sys.stderr.write(f"⚠️ error.send_email: Missing one of required keys: {required_keys}\n")
        return False
        
    details = SuggestionEngine.get_details(exc)
    subject = f"🚨 [{getattr(exc, '__severity__', 'ERROR').upper()}] {details['name']}: {details['message']}"
    
    # Create HTML body using the beautiful Jupyter panel HTML styling
    html_body = Formatter.format_jupyter_html(exc)
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_cfg["sender"]
    msg["To"] = email_cfg["recipient"]
    msg.attach(MIMEText(str(error.explain(exc) if 'error' in sys.modules else details['translation']), "plain"))
    msg.attach(MIMEText(html_body, "html"))
    
    try:
        with smtplib.SMTP(email_cfg["host"], email_cfg["port"], timeout=10) as server:
            if email_cfg.get("username") and email_cfg.get("password"):
                if email_cfg.get("use_tls", True):
                    server.starttls()
                server.login(email_cfg["username"], email_cfg["password"])
            server.sendmail(email_cfg["sender"], email_cfg["recipient"], msg.as_string())
        return True
    except Exception as e:
        sys.stderr.write(f"⚠️ error.send_email: Failed to send email alert: {e}\n")
        return False
