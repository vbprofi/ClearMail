"""
POP3Handler – vollständige POP3-Implementierung (RFC 1939, RFC 2595 STLS).
SMTPHandler  – vollständige SMTP-Implementierung (RFC 5321, STARTTLS, SMTPS).

Sicherheit:
  - POP3S (Port 995): poplib.POP3_SSL mit modernem TLS-Kontext
  - STARTTLS (Port 110): POP3 + stls()
  - SMTPS (Port 465): smtplib.SMTP_SSL
  - STARTTLS (Port 587): smtplib.SMTP + starttls()
  - DKIM/SPF werden durch den Server geprüft, nicht vom Client
"""

import poplib
import smtplib
import ssl
import email
import email.policy
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email.utils import formatdate, make_msgid
from email import encoders
from pathlib import Path
from typing import List, Dict, Optional

from protocols.imap_handler import IMAPHandler   # parse_email_message wiederverwenden

try:
    from core.protocol_runner import log as _proto_log
except ImportError:
    def _proto_log(level, msg): pass

def log(level: str, msg: str):
    _proto_log(level, msg)


# ================================================================== #
#  POP3Handler                                                        #
# ================================================================== #

class POP3Handler:

    def __init__(self, host: str, port: int, username: str, password: str,
                 use_ssl: bool = True, verify_cert: bool = True):
        self.host        = host
        self.port        = port
        self.username    = username
        self.password    = password
        self.use_ssl     = use_ssl
        self.verify_cert = verify_cert
        self._conn       = None

    def connect(self) -> bool:
        log("info", f"POP3 connect: {self.host}:{self.port} ssl={self.use_ssl} user={self.username}")
        try:
            ctx = ssl.create_default_context()
            if not self.verify_cert:
                ctx.check_hostname = False
                ctx.verify_mode    = ssl.CERT_NONE

            if self.use_ssl:
                self._conn = poplib.POP3_SSL(self.host, self.port, context=ctx)
            else:
                self._conn = poplib.POP3(self.host, self.port)
                # STLS (STARTTLS für POP3) anbieten
                caps = self._conn.capa()
                if b"STLS" in caps or "STLS" in str(caps):
                    log("info", "POP3 STLS negotiated")
                self._conn.stls(context=ctx)

            self._conn.user(self.username)
            self._conn.pass_(self.password)
            log("info", "POP3 AUTH OK")
            return True
        except (poplib.error_proto, OSError, ssl.SSLError) as e:
            log("error", f"POP3 connect error: {e}")
            raise ConnectionError(f"POP3-Verbindung fehlgeschlagen ({self.host}:{self.port}): {e}") from e

    def disconnect(self):
        if self._conn:
            log("info", f"POP3 disconnect: {self.host}")
            try: self._conn.quit()
            except Exception: pass
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def get_mail_count(self) -> int:
        if not self._conn:
            raise RuntimeError("Nicht verbunden.")
        count, _ = self._conn.stat()
        return count

    def get_uidl_list(self) -> Dict[int, str]:
        """Gibt {msg_num: unique_id} zurück (UIDL-Kommando)."""
        typ, data, _ = self._conn.uidl()
        result = {}
        for line in data:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            parts = line.strip().split()
            if len(parts) >= 2:
                result[int(parts[0])] = parts[1]
        return result

    def fetch_mail(self, msg_num: int) -> Optional[Dict]:
        """Lädt eine Mail als Dict (parsemail)."""
        log("debug", f"POP3 RETR {msg_num}")
        resp, lines, octets = self._conn.retr(msg_num)
        raw = b"\r\n".join(lines)
        return IMAPHandler.parse_email_message(raw, include_attachments=True)

    def fetch_new_mails(self, known_uids: set = None) -> List[Dict]:
        """Ruft alle unbekannten Mails ab."""
        known_uids = known_uids or set()
        uidl = self.get_uidl_list()
        mails = []
        for msg_num, uid in uidl.items():
            if uid in known_uids:
                continue
            try:
                m = self.fetch_mail(msg_num)
                if m:
                    m["uid"] = uid
                    mails.append(m)
            except Exception:
                pass
        return mails

    def delete_mail(self, msg_num: int):
        """Markiert eine Mail zum Löschen (wird bei quit() gelöscht)."""
        self._conn.dele(msg_num)


# ================================================================== #
#  SMTPHandler                                                        #
# ================================================================== #

class SMTPHandler:

    def __init__(self, host: str, port: int, username: str, password: str,
                 use_ssl: bool = True, verify_cert: bool = True):
        self.host        = host
        self.port        = port
        self.username    = username
        self.password    = password
        self.use_ssl     = use_ssl
        self.verify_cert = verify_cert

    def send(
        self,
        from_addr: str,
        to_addrs:  List[str],
        subject:   str,
        body_text: str,
        body_html: str = "",
        cc:        List[str] = None,
        attachments: List[str] = None,
    ) -> bytes:
        """
        Sendet eine E-Mail.

        Returns:
            Die gesendete Nachricht als bytes (für IMAP APPEND / Gesendet-Ordner).

        Raises:
            RuntimeError bei SMTP-Fehlern.
        """
        msg = self._build_message(
            from_addr, to_addrs, subject,
            body_text, body_html, cc or [], attachments or []
        )
        raw = msg.as_bytes()

        log("info", f"SMTP send: {self.host}:{self.port} ssl={self.use_ssl} from={from_addr} to={to_addrs}")
        ctx = ssl.create_default_context()
        if not self.verify_cert:
            ctx.check_hostname = False
            ctx.verify_mode    = ssl.CERT_NONE

        try:
            all_recipients = to_addrs + (cc or [])

            if self.use_ssl and self.port == 465:
                # SMTPS – implizites SSL
                log("info", f"SMTP SMTPS connect {self.host}:{self.port}")
                with smtplib.SMTP_SSL(self.host, self.port, context=ctx) as server:
                    server.login(self.username, self.password)
                    log("info", "SMTP AUTH OK (SMTPS)")
                    server.sendmail(from_addr, all_recipients, raw)
                    log("info", f"SMTP sent OK to {all_recipients}")
            else:
                # STARTTLS (Port 587 oder 25)
                log("info", f"SMTP STARTTLS connect {self.host}:{self.port}")
                with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                    server.ehlo()
                    if self.use_ssl:
                        server.starttls(context=ctx)
                        server.ehlo()
                        log("info", "SMTP STARTTLS negotiated")
                    if self.username:
                        server.login(self.username, self.password)
                        log("info", "SMTP AUTH OK (STARTTLS)")
                    server.sendmail(from_addr, all_recipients, raw)
                    log("info", f"SMTP sent OK to {all_recipients}")

        except smtplib.SMTPAuthenticationError as e:
            log("error", f"SMTP AUTH error: {e}")
            raise RuntimeError(f"SMTP-Authentifizierung fehlgeschlagen: {e}") from e
        except smtplib.SMTPRecipientsRefused as e:
            log("error", f"SMTP recipients refused: {e}")
            raise RuntimeError(f"Empfänger abgelehnt: {e}") from e
        except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
            log("error", f"SMTP error: {e}")
            raise RuntimeError(f"SMTP-Fehler: {e}") from e

        return raw

    @staticmethod
    def _build_message(
        from_addr:   str,
        to_addrs:    List[str],
        subject:     str,
        body_text:   str,
        body_html:   str,
        cc:          List[str],
        attachments: List[str],
    ) -> MIMEMultipart:
        """Baut eine RFC-2822-kompatible MIME-Nachricht zusammen."""
        msg = MIMEMultipart("mixed")
        msg["From"]       = from_addr
        msg["To"]         = ", ".join(to_addrs)
        msg["Subject"]    = subject
        msg["Date"]       = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        if cc:
            msg["Cc"] = ", ".join(cc)

        # Body
        if body_html:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body_text or "", "plain", "utf-8"))
            alt.attach(MIMEText(body_html,       "html",  "utf-8"))
            msg.attach(alt)
        else:
            msg.attach(MIMEText(body_text or "", "plain", "utf-8"))

        # Anhänge
        for path in attachments:
            p = Path(path)
            if p.exists():
                with open(p, "rb") as f:
                    part = MIMEApplication(f.read(), Name=p.name)
                part["Content-Disposition"] = f'attachment; filename="{p.name}"'
                msg.attach(part)

        return msg
