"""Email sending service via SMTP."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
from app.config import settings


class EmailSender:
    """Send emails via SMTP."""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL

    def send_report(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str,
        text_content: str = None
    ) -> Dict[str, Any]:
        """Send report email."""
        try:
            # Validate config
            if not self.smtp_host or not self.from_email:
                return {
                    'success': False,
                    'error': 'SMTP configuration not set'
                }

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = ', '.join(to_emails)

            # Attach text version
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))

            # Attach HTML version
            msg.attach(MIMEText(html_content, 'html'))

            # Send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            return {
                'success': True,
                'recipients': len(to_emails),
                'message': f'Email sent to {len(to_emails)} recipients'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def send_alert(
        self,
        to_email: str,
        company_name: str,
        news_title: str,
        risk_score: int
    ) -> Dict[str, Any]:
        """Send urgent alert email."""
        try:
            subject = f"⚠️ URGENT ALERT: {company_name} - {news_title}"

            text_content = f"""
URGENT ALERT

Company: {company_name}
Risk Level: {risk_score}/10
News: {news_title}

This requires immediate attention.
Log in to the dashboard to view details and take action.
"""

            html_content = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <div style="background: #e74c3c; color: white; padding: 20px; border-radius: 4px;">
        <h2>⚠️ URGENT ALERT</h2>
        <p><strong>Company:</strong> {company_name}</p>
        <p><strong>Risk Level:</strong> <span style="font-size: 20px; font-weight: bold;">{risk_score}/10</span></p>
        <p><strong>News:</strong> {news_title}</p>
        <p>This requires immediate attention.</p>
    </div>
</body>
</html>
"""

            return self.send_report([to_email], subject, html_content, text_content)

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def test_connection(self) -> Dict[str, Any]:
        """Test SMTP connection."""
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
            return {
                'success': True,
                'message': 'SMTP connection successful'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
