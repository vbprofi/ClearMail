"""
POP3Handler – Platzhalter für POP3-Implementierung
SMTPHandler – Platzhalter für SMTP-Implementierung
"""

import poplib
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional
from pathlib import Path


# ================================================================== #
#  POP3Handler                                                        #
# ================================================================== #

class POP3Handler:
    """
    POP3-Handler (Grundstruktur – noch nicht vollständig implementiert).
    Nutzt poplib aus der Python-Standardbibliothek.
    """

    def __init__(self, host: str, port: int, username: str, password: str, use_ssl: bool = True):
        self.host     = host
        self.port     = port
        self.username = username
        self.password = password
        self.use_ssl  = use_ssl
        self._conn    = None

    def connect(self) -> bool:
        try:
            if self.use_ssl:
                self._conn = poplib.POP3_SSL(self.host, self.port)
            else:
                self._conn = poplib.POP3(self.host, self.port)
            self._conn.user(self.username)
            self._conn.pass_(self.password)
            return True
        except (poplib.error_proto, OSError) as e:
            raise ConnectionError(f"POP3-Verbindung fehlgeschlagen: {e}") from e

    def disconnect(self):
        if self._conn:
            try:
                self._conn.quit()
            except Exception:
                pass
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def get_mail_count(self) -> int:
        """Gibt die Anzahl der Mails auf dem Server zurück."""
        if not self._conn:
            raise RuntimeError("Nicht verbunden.")
        count, _ = self._conn.stat()
        return count

    def fetch_mail(self, msg_num: int) -> bytes:
        """Lädt eine Mail als raw bytes."""
        raise NotImplementedError("fetch_mail() noch nicht implementiert.")

    def delete_mail(self, msg_num: int):
        """Markiert eine Mail zum Löschen (wird bei quit() gelöscht)."""
        raise NotImplementedError


# ================================================================== #
#  SMTPHandler                                                        #
# ================================================================== #

class SMTPHandler:
    """
    SMTP-Handler.
    Grundstruktur vorhanden – send() ist vorbereitet aber noch zu testen.
    """

    def __init__(self, host: str, port: int, username: str, password: str, use_ssl: bool = True):
        self.host     = host
        self.port     = port
        self.username = username
        self.password = password
        self.use_ssl  = use_ssl

    def send(
        self,
        from_addr: str,
        to_addrs: List[str],
        subject: str,
        body_text: str,
        body_html: str = "",
        cc: List[str] = None,
        attachments: List[str] = None,
    ) -> bool:
        """
        Sendet eine E-Mail über SMTP.

        Args:
            from_addr:    Absender-Adresse
            to_addrs:     Liste der Empfänger-Adressen
            subject:      Betreff
            body_text:    Klartext-Inhalt
            body_html:    HTML-Inhalt (optional)
            cc:           CC-Adressen (optional)
            attachments:  Dateipfade für Anhänge (optional)

        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            msg = self._build_message(
                from_addr, to_addrs, subject, body_text, body_html, cc or [], attachments or []
            )

            if self.use_ssl and self.port == 465:
                # SMTPS (implizites SSL)
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context) as server:
                    server.login(self.username, self.password)
                    server.sendmail(from_addr, to_addrs + (cc or []), msg.as_string())
            else:
                # STARTTLS
                with smtplib.SMTP(self.host, self.port) as server:
                    server.ehlo()
                    if self.use_ssl:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    server.login(self.username, self.password)
                    server.sendmail(from_addr, to_addrs + (cc or []), msg.as_string())

            return True

        except (smtplib.SMTPException, OSError) as e:
            raise RuntimeError(f"SMTP-Fehler: {e}") from e

    @staticmethod
    def _build_message(
        from_addr: str,
        to_addrs: List[str],
        subject: str,
        body_text: str,
        body_html: str,
        cc: List[str],
        attachments: List[str],
    ) -> MIMEMultipart:
        """Baut eine MIME-Nachricht zusammen."""
        msg = MIMEMultipart("mixed")
        msg["From"]    = from_addr
        msg["To"]      = ", ".join(to_addrs)
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)

        # Body
        if body_html:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body_text, "plain", "utf-8"))
            alt.attach(MIMEText(body_html,  "html",  "utf-8"))
            msg.attach(alt)
        else:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Anhänge
        for path in attachments:
            p = Path(path)
            if p.exists():
                with open(p, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=p.name)
                msg.attach(part)

        return msg
