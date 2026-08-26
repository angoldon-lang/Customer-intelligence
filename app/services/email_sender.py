"""Email sending service via SMTP."""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import List, Dict, Any
from app.config import settings


class EmailSender:
    """Send emails via SMTP."""

    def __init__(self, db=None):
        # Settings saved from Impostazioni win over .env; without a session
        # (e.g. background jobs that don't have one) fall back to .env.
        if db is not None:
            from app.services.settings_store import get_setting
            self.smtp_host = get_setting(db, "SMTP_HOST")
            self.smtp_port = get_setting(db, "SMTP_PORT")
            self.smtp_user = get_setting(db, "SMTP_USER")
            self.smtp_password = get_setting(db, "SMTP_PASSWORD")
            self.from_email = get_setting(db, "SMTP_FROM_EMAIL") or self.smtp_user
            self.from_name = get_setting(db, "SMTP_FROM_NAME")
            self.use_ssl = bool(get_setting(db, "SMTP_USE_SSL"))
            from app.services.branding import logo_path
            self.logo_path = logo_path(db)
        else:
            self.smtp_host = settings.SMTP_HOST
            self.smtp_port = settings.SMTP_PORT
            self.smtp_user = settings.SMTP_USER
            self.smtp_password = settings.SMTP_PASSWORD
            self.from_email = settings.SMTP_FROM_EMAIL
            self.from_name = settings.SMTP_FROM_NAME
            self.use_ssl = settings.SMTP_USE_SSL
            self.logo_path = None

        self.timeout = settings.SMTP_TIMEOUT

    def config_problem(self) -> str:
        """What's missing from the configuration, or None if it's complete."""
        if not self.smtp_host:
            return "Server SMTP non configurato (Impostazioni > Configurazione Email)"
        if not self.smtp_user:
            return "Utente SMTP non configurato"
        if not self.smtp_password:
            return "Password SMTP non configurata"
        if not self.from_email:
            return "Email mittente non configurata"
        return None

    def _connect(self):
        """
        Open an SMTP connection, picking the right kind of TLS.

        Port 465 speaks TLS from the first byte (SMTP_SSL); 587 and 25 start
        in clear and upgrade with STARTTLS. Calling starttls() on 465 - what
        this code used to do unconditionally - just hangs until timeout.
        """
        port = int(self.smtp_port or 587)

        if self.use_ssl or port == 465:
            return smtplib.SMTP_SSL(self.smtp_host, port, timeout=self.timeout)

        server = smtplib.SMTP(self.smtp_host, port, timeout=self.timeout)
        server.ehlo()
        if server.has_extn("starttls"):
            server.starttls()
            server.ehlo()
        return server

    def send_report(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str,
        text_content: str = None
    ) -> Dict[str, Any]:
        """Send report email."""
        problem = self.config_problem()
        if problem:
            return {'success': False, 'error': problem}

        try:
            body = MIMEMultipart('alternative')
            # Plain part first: the last attached part is what mail clients
            # prefer, so HTML has to come second.
            if text_content:
                body.attach(MIMEText(text_content, 'plain'))
            body.attach(MIMEText(html_content, 'html'))

            logo = self._logo_part(html_content)
            if logo:
                # "related" wraps the alternative body together with the
                # inline image the HTML refers to by cid:.
                msg = MIMEMultipart('related')
                msg.attach(body)
                msg.attach(logo)
            else:
                msg = body

            msg['Subject'] = subject
            msg['From'] = formataddr((self.from_name, self.from_email)) if self.from_name else self.from_email
            msg['To'] = ', '.join(to_emails)

            with self._connect() as server:
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            return {
                'success': True,
                'recipients': len(to_emails),
                'message': f'Email inviata a {len(to_emails)} destinatari'
            }

        except Exception as e:
            return {'success': False, 'error': self.explain_error(e)}

    def _logo_part(self, html_content: str):
        """
        The branding logo as an inline attachment, if the HTML asks for it.

        Only attached when the body actually references the cid, so a plain
        report never carries a stray image.
        """
        from app.services.branding import LOGO_CID

        if not self.logo_path or f"cid:{LOGO_CID}" not in (html_content or ""):
            return None

        try:
            with open(self.logo_path, "rb") as handle:
                data = handle.read()
        except OSError as e:
            # A missing logo must not stop the report going out.
            print(f"[Email] Logo non leggibile ({e}): invio senza logo")
            return None

        subtype = os.path.splitext(self.logo_path)[1].lstrip(".").lower()
        image = MIMEImage(data, _subtype="jpeg" if subtype in ("jpg", "jpeg") else subtype)
        image.add_header("Content-ID", f"<{LOGO_CID}>")
        image.add_header("Content-Disposition", "inline", filename=os.path.basename(self.logo_path))
        return image

    def explain_error(self, error: Exception) -> str:
        """
        Turn an SMTP failure into something actionable.

        The raw exceptions ("(535, b'5.7.8 Username and Password not
        accepted')") send people to reset a password that was never the
        problem.
        """
        text = str(error)
        lowered = text.lower()
        host = (self.smtp_host or "").lower()

        if isinstance(error, smtplib.SMTPAuthenticationError) or "535" in text or "5.7.8" in text:
            if "gmail" in host or "google" in host:
                return (
                    "Gmail ha rifiutato le credenziali. Con Gmail NON funziona la password "
                    "normale dell'account: serve una password per le app (16 caratteri), che "
                    "richiede la verifica in due passaggi attiva. "
                    "Creala su https://myaccount.google.com/apppasswords e incollala nel campo "
                    f"password. Dettaglio tecnico: {text}"
                )
            if "office365" in host or "outlook" in host:
                return (
                    "Microsoft 365 ha rifiutato le credenziali. Di solito non e' la password: "
                    "Microsoft disattiva 'SMTP AUTH' sulle caselle per impostazione predefinita, "
                    "e con MFA attiva l'accesso SMTP di base non funziona affatto. "
                    "Serve che un amministratore abiliti SMTP AUTH sulla casella "
                    f"(Authenticated SMTP) dall'interfaccia di amministrazione. Dettaglio: {text}"
                )
            return f"Credenziali SMTP rifiutate dal server. Dettaglio: {text}"

        if isinstance(error, smtplib.SMTPSenderRefused) or "5.7.0" in text or "not allowed" in lowered:
            return (
                f"Il server non accetta '{self.from_email}' come mittente. "
                f"Di norma l'email mittente deve coincidere con l'utente SMTP "
                f"('{self.smtp_user}') o essere un alias autorizzato. Dettaglio: {text}"
            )

        if isinstance(error, (TimeoutError, OSError)) and (
            "timed out" in lowered or "timeout" in lowered
        ):
            return (
                f"Nessuna risposta da {self.smtp_host}:{self.smtp_port} entro {self.timeout}s. "
                f"Se hai impostato la porta 465 assicurati che sia SSL, altrimenti usa la 587. "
                f"Puo' anche essere il firewall di rete che blocca la porta. Dettaglio: {text}"
            )

        if "ssl" in lowered or "wrong version number" in lowered:
            return (
                f"Errore TLS con {self.smtp_host}:{self.smtp_port}. Combinazione porta/cifratura "
                f"sbagliata: usa 587 (STARTTLS) oppure 465 (SSL). Dettaglio: {text}"
            )

        if isinstance(error, smtplib.SMTPServerDisconnected) or "connection refused" in lowered:
            return (
                f"Impossibile connettersi a {self.smtp_host}:{self.smtp_port}. "
                f"Verifica nome del server e porta. Dettaglio: {text}"
            )

        if "getaddrinfo" in lowered or "name or service not known" in lowered:
            return f"Server SMTP '{self.smtp_host}' non trovato: controlla il nome. Dettaglio: {text}"

        return text

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
        """Test SMTP connection, reporting what to fix when it fails."""
        problem = self.config_problem()
        if problem:
            return {'success': False, 'error': problem}

        try:
            with self._connect() as server:
                server.login(self.smtp_user, self.smtp_password)

            mode = "SSL" if (self.use_ssl or int(self.smtp_port or 587) == 465) else "STARTTLS"
            return {
                'success': True,
                'message': (
                    f"Connessione riuscita a {self.smtp_host}:{self.smtp_port} ({mode}) "
                    f"come {self.smtp_user}."
                ),
            }
        except Exception as e:
            return {'success': False, 'error': self.explain_error(e)}
