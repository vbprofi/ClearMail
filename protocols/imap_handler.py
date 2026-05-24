"""
IMAPHandler – Platzhalter für die IMAP-Implementierung.

Implementierung: imaplib (stdlib) oder imapclient (pip install imapclient)

Zum Aktivieren:
  1. Klasse IMAPHandler vollständig implementieren
  2. In AppController.fetch_new_mails() instanziieren
"""

import imaplib
import email
from email.header import decode_header
from typing import List, Dict, Optional
from datetime import datetime


class IMAPHandler:
    """
    IMAP-Handler (Grundstruktur – noch nicht vollständig implementiert).
    Methoden sind mit raise NotImplementedError markiert.
    """

    def __init__(self, host: str, port: int, username: str, password: str, use_ssl: bool = True):
        self.host      = host
        self.port      = port
        self.username  = username
        self.password  = password
        self.use_ssl   = use_ssl
        self._conn: Optional[imaplib.IMAP4_SSL] = None

    # ------------------------------------------------------------------ #
    #  Verbindung                                                         #
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        """
        Verbindung zum IMAP-Server herstellen und authentifizieren.
        Gibt True bei Erfolg zurück.
        """
        try:
            if self.use_ssl:
                self._conn = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                self._conn = imaplib.IMAP4(self.host, self.port)
            self._conn.login(self.username, self.password)
            return True
        except (imaplib.IMAP4.error, OSError) as e:
            raise ConnectionError(f"IMAP-Verbindung fehlgeschlagen: {e}") from e

    def disconnect(self):
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    # ------------------------------------------------------------------ #
    #  Ordner                                                             #
    # ------------------------------------------------------------------ #

    def list_folders(self) -> List[Dict]:
        """
        Gibt alle IMAP-Ordner zurück.
        Rückgabe: [{"name": str, "path": str, "flags": list}, ...]
        """
        if not self._conn:
            raise RuntimeError("Nicht verbunden.")
        # TODO: implementieren
        raise NotImplementedError("list_folders() noch nicht implementiert.")

    def select_folder(self, folder_path: str) -> int:
        """Wählt einen Ordner aus. Gibt die Anzahl der Nachrichten zurück."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    #  Mails abrufen                                                     #
    # ------------------------------------------------------------------ #

    def fetch_mail_list(self, folder: str = "INBOX", since: datetime = None) -> List[Dict]:
        """
        Ruft die Mail-Liste eines Ordners ab.
        Rückgabe: [{"uid": str, "subject": str, "sender": str, "date": str, ...}, ...]
        """
        raise NotImplementedError("fetch_mail_list() noch nicht implementiert.")

    def fetch_mail(self, uid: str, folder: str = "INBOX") -> Optional[Dict]:
        """
        Ruft den vollständigen Inhalt einer Mail ab.
        Rückgabe: {"subject": str, "sender": str, "body_text": str, "body_html": str, ...}
        """
        raise NotImplementedError("fetch_mail() noch nicht implementiert.")

    # ------------------------------------------------------------------ #
    #  Operationen                                                        #
    # ------------------------------------------------------------------ #

    def mark_read(self, uid: str, folder: str = "INBOX"):
        """Markiert eine Mail als gelesen (\\Seen-Flag setzen)."""
        raise NotImplementedError

    def mark_unread(self, uid: str, folder: str = "INBOX"):
        """Entfernt das \\Seen-Flag."""
        raise NotImplementedError

    def delete_mail(self, uid: str, folder: str = "INBOX"):
        """Löscht eine Mail (\\Deleted-Flag setzen + EXPUNGE)."""
        raise NotImplementedError

    def move_mail(self, uid: str, from_folder: str, to_folder: str):
        """Verschiebt eine Mail in einen anderen Ordner."""
        raise NotImplementedError

    def create_folder(self, folder_path: str) -> bool:
        """Erstellt einen neuen IMAP-Ordner."""
        raise NotImplementedError

    def delete_folder(self, folder_path: str) -> bool:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden (statisch, bereits nutzbar)                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def decode_header_value(value: str) -> str:
        """Dekodiert MIME-enkodierte Header-Werte."""
        if not value:
            return ""
        parts = decode_header(value)
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)

    @staticmethod
    def parse_email_message(raw_bytes: bytes) -> Dict:
        """
        Parst eine rohe E-Mail und gibt ein Dictionary zurück.
        """
        msg = email.message_from_bytes(raw_bytes)
        subject  = IMAPHandler.decode_header_value(msg.get("Subject", ""))
        sender   = IMAPHandler.decode_header_value(msg.get("From", ""))
        to_field = IMAPHandler.decode_header_value(msg.get("To", ""))
        cc_field = IMAPHandler.decode_header_value(msg.get("CC", ""))
        date_str = msg.get("Date", "")

        body_text = ""
        body_html = ""
        has_attach = False

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp  = str(part.get("Content-Disposition", ""))
                if "attachment" in disp:
                    has_attach = True
                    continue
                if ctype == "text/plain" and not body_text:
                    charset  = part.get_content_charset() or "utf-8"
                    body_text = part.get_payload(decode=True).decode(charset, errors="replace")
                elif ctype == "text/html" and not body_html:
                    charset  = part.get_content_charset() or "utf-8"
                    body_html = part.get_payload(decode=True).decode(charset, errors="replace")
        else:
            charset  = msg.get_content_charset() or "utf-8"
            payload  = msg.get_payload(decode=True)
            if payload:
                body_text = payload.decode(charset, errors="replace")

        return {
            "subject":    subject,
            "sender":     sender,
            "recipients": to_field,
            "cc":         cc_field,
            "date":       date_str,
            "body_text":  body_text,
            "body_html":  body_html,
            "has_attach": has_attach,
            "message_id": msg.get("Message-ID", ""),
        }
