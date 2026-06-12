import sys
import os
import json
import urllib.request
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional, List, Tuple

from pyerror.suggestions import SuggestionEngine
from pyerror.formatting import Formatter

# Global configurations for integrations
_slack_webhook: Optional[str] = None
_sentry_dsn: Optional[str] = None
_email_config: Optional[Dict[str, Any]] = None  # host, port, username, password, sender, recipient
_rate_limit_seconds: Optional[int] = None
_alert_history: Dict[str, float] = {}
_alert_suppressed_counts: Dict[str, int] = {}

def _get_exception_signature(exc: BaseException) -> str:
    exc_name = type(exc).__name__
    tb = exc.__traceback__
    filename = "unknown"
    lineno = 0
    if tb:
        while tb.tb_next:
            tb = tb.tb_next
        filename = tb.tb_frame.f_code.co_filename
        lineno = tb.tb_lineno
    return f"{exc_name}@{filename}:{lineno}"

def _should_rate_limit(exc: BaseException) -> Tuple[bool, int]:
    global _rate_limit_seconds, _alert_history, _alert_suppressed_counts
    if _rate_limit_seconds is None:
        return False, 0
        
    sig = _get_exception_signature(exc)
    now = time.time()
    
    if sig not in _alert_history:
        _alert_history[sig] = now
        return False, 0
        
    elapsed = now - _alert_history[sig]
    if elapsed < _rate_limit_seconds:
        _alert_suppressed_counts[sig] = _alert_suppressed_counts.get(sig, 0) + 1
        return True, 0
    else:
        suppressed_count = _alert_suppressed_counts.get(sig, 0)
        _alert_suppressed_counts[sig] = 0
        _alert_history[sig] = now
        return False, suppressed_count

_sentinel = object()

def configure_integrations(
    slack_webhook: Optional[str] = None,
    sentry_dsn: Optional[str] = None,
    email_config: Optional[Dict[str, Any]] = None,
    rate_limit_seconds: Optional[int] = _sentinel
):
    """Configures global credentials/webhooks for Sentry, Slack, and Email notifications."""
    global _slack_webhook, _sentry_dsn, _email_config, _rate_limit_seconds
    if slack_webhook is not None:
        _slack_webhook = slack_webhook
    if sentry_dsn is not None:
        _sentry_dsn = sentry_dsn
    if email_config is not None:
        _email_config = email_config
    if rate_limit_seconds is not _sentinel:
        _rate_limit_seconds = rate_limit_seconds

def notify_slack(exc: BaseException, webhook_url: Optional[str] = None) -> bool:
    """
    Sends a beautifully structured notification block payload to a Slack Webhook.
    Uses standard library urllib.request to avoid external library dependencies.
    """
    url = webhook_url or _slack_webhook
    if not url:
        sys.stderr.write("⚠️ pyerror.notify_slack: No webhook URL provided or configured.\n")
        return False
        
    suppress, count = _should_rate_limit(exc)
    if suppress:
        return False

    details = SuggestionEngine.get_details(exc)
    severity = getattr(exc, "__severity__", "ERROR").upper()
    
    body_text = f"*Error Message:*\n`{details['message']}`\n\n*Explanation:*\n{details['translation']}\n\n*Why:*\n{details['why']}"
    if count > 0:
        body_text += f"\n\n⚠️ *This error was suppressed {count} times during the rate limit window.*"

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
                    "text": body_text
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
        sys.stderr.write(f"⚠️ pyerror.notify_slack: Failed to send Slack alert: {e}\n")
        return False

def notify_sentry(exc: BaseException, dsn: Optional[str] = None) -> bool:
    """
    Integrates with Sentry. If the official sentry_sdk is installed, it forwards 
    the exception to Sentry, otherwise logs a local warning.
    """
    target_dsn = dsn or _sentry_dsn
    suppress, count = _should_rate_limit(exc)
    if suppress:
        return False
        
    try:
        import sentry_sdk
        if target_dsn and not sentry_sdk.Hub.current.client:
            sentry_sdk.init(dsn=target_dsn)
        if count > 0:
            with sentry_sdk.configure_scope() as scope:
                scope.set_extra("suppressed_duplicates", count)
        sentry_sdk.capture_exception(exc)
        return True
    except ImportError:
        sys.stderr.write("⚠️ pyerror.notify_sentry: sentry_sdk is not installed. Exception details logged locally.\n")
        return False
    except Exception as e:
        sys.stderr.write(f"⚠️ pyerror.notify_sentry: Failed to report to Sentry: {e}\n")
        return False

def send_email(exc: BaseException, config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Sends a premium HTML error report email to the configured recipient
    using standard SMTP mail routing.
    """
    email_cfg = config or _email_config
    if not email_cfg:
        sys.stderr.write("⚠️ pyerror.send_email: No email configuration provided.\n")
        return False
        
    required_keys = ["host", "port", "sender", "recipient"]
    if not all(k in email_cfg for k in required_keys):
        sys.stderr.write(f"⚠️ pyerror.send_email: Missing one of required keys: {required_keys}\n")
        return False
        
    suppress, count = _should_rate_limit(exc)
    if suppress:
        return False

    details = SuggestionEngine.get_details(exc)
    subject = f"🚨 [{getattr(exc, '__severity__', 'ERROR').upper()}] {details['name']}: {details['message']}"
    
    # Create HTML body using the beautiful Jupyter panel HTML styling
    html_body = Formatter.format_jupyter_html(exc)
    if count > 0:
        warning_html = f"""
        <div style="background: #fffbeb; border: 1px solid #fef3c7; border-radius: 6px; padding: 14px; margin-bottom: 16px; color: #b45309; font-size: 0.95em;">
            ⚠️ This error was suppressed {count} times during the rate limit window.
        </div>
        """
        html_body = html_body.replace('<!-- Header -->', warning_html + '<!-- Header -->')
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_cfg["sender"]
    msg["To"] = email_cfg["recipient"]
    
    # Resolve helper or use details translation
    if 'pyerror' in sys.modules:
        import pyerror
        plain_body = str(pyerror.explain(exc))
    else:
        plain_body = details['translation']
        
    if count > 0:
        plain_body += f"\n\n[Rate Limit] This error was suppressed {count} times during the rate limit window."
        
    msg.attach(MIMEText(plain_body, "plain"))
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
        sys.stderr.write(f"⚠️ pyerror.send_email: Failed to send email alert: {e}\n")
        return False
