"""
IMAPHandler – vollständige IMAP-Implementierung.
RFC 3501 (IMAP4rev1), RFC 6855 (UTF-8), RFC 4551 (CONDSTORE).

Sicherheit:
  - SSL/TLS (Port 993): imaplib.IMAP4_SSL mit modernem TLS-Kontext
  - STARTTLS (Port 143): IMAP4 + starttls()
  - Passwort-Auth: LOGIN (Fallback) oder PLAIN via AUTHENTICATE
  - Zertifikatsvalidierung aktiviert (kann für self-signed deaktiviert werden)
"""

import imaplib
import email
import email.policy
import ssl
import re
from email.header import decode_header as _decode_header
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class IMAPHandler:

    def __init__(self, host: str, port: int, username: str, password: str,
                 use_ssl: bool = True, verify_cert: bool = True):
        self.host        = host
        self.port        = port
        self.username    = username
        self.password    = password
        self.use_ssl     = use_ssl
        self.verify_cert = verify_cert
        self._conn: Optional[imaplib.IMAP4] = None

    # ------------------------------------------------------------------ #
    #  Verbindung                                                         #
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        try:
            ctx = ssl.create_default_context()
            if not self.verify_cert:
                ctx.check_hostname = False
                ctx.verify_mode    = ssl.CERT_NONE

            if self.use_ssl:
                self._conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx)
            else:
                self._conn = imaplib.IMAP4(self.host, self.port)
                # STARTTLS anbieten wenn möglich
                if "STARTTLS" in self._conn.capabilities:
                    self._conn.starttls(ssl_context=ctx)

            # AUTH: bevorzugt AUTH=PLAIN, Fallback LOGIN
            caps = self._conn.capabilities
            if b"AUTH=PLAIN" in caps or "AUTH=PLAIN" in str(caps):
                try:
                    import base64
                    creds = base64.b64encode(
                        f"\x00{self.username}\x00{self.password}".encode()
                    ).decode()
                    self._conn.authenticate("PLAIN", lambda x: creds)
                except Exception:
                    self._conn.login(self.username, self.password)
            else:
                self._conn.login(self.username, self.password)
            return True
        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as e:
            raise ConnectionError(f"IMAP-Verbindung fehlgeschlagen ({self.host}:{self.port}): {e}") from e

    def disconnect(self):
        if self._conn:
            try: self._conn.logout()
            except Exception: pass
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
        Rückgabe: [{"name": str, "path": str, "flags": list, "separator": str}]
        """
        if not self._conn:
            raise RuntimeError("Nicht verbunden.")
        typ, data = self._conn.list()
        if typ != "OK":
            return []
        folders = []
        for item in data:
            if item is None:
                continue
            line = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else item
            # Format: (\Flags) "separator" "path"
            m = re.match(r'\(([^)]*)\)\s+"([^"]+)"\s+"?([^"]+)"?', line.strip())
            if not m:
                m = re.match(r'\(([^)]*)\)\s+\S+\s+(.*)', line.strip())
                if not m:
                    continue
            flags_str = m.group(1)
            sep       = m.group(2) if m.lastindex >= 2 else "/"
            path      = m.group(3) if m.lastindex >= 3 else m.group(2)
            path      = path.strip().strip('"')
            name      = path.split(sep)[-1] if sep in path else path
            flags     = [f.strip() for f in flags_str.split() if f.strip()]
            folders.append({
                "name": name, "path": path,
                "separator": sep, "flags": flags,
            })
        return folders

    def select_folder(self, folder_path: str) -> int:
        """Wählt einen Ordner aus. Gibt Nachrichtenanzahl zurück."""
        if not self._conn:
            raise RuntimeError("Nicht verbunden.")
        typ, data = self._conn.select(f'"{folder_path}"')
        if typ != "OK":
            typ, data = self._conn.select(folder_path)
        if typ == "OK" and data and data[0]:
            return int(data[0])
        return 0

    # ------------------------------------------------------------------ #
    #  Mails abrufen                                                     #
    # ------------------------------------------------------------------ #

    def fetch_unseen_uids(self, folder: str = "INBOX") -> List[str]:
        """Gibt UIDs aller ungelesenen Mails zurück."""
        self.select_folder(folder)
        typ, data = self._conn.uid("search", None, "UNSEEN")
        if typ != "OK" or not data or not data[0]:
            return []
        return data[0].decode().split()

    def fetch_all_uids(self, folder: str = "INBOX", since: datetime = None) -> List[str]:
        """Gibt alle UIDs (optional seit einem Datum)."""
        self.select_folder(folder)
        if since:
            date_str = since.strftime("%d-%b-%Y")
            typ, data = self._conn.uid("search", None, f'SINCE "{date_str}"')
        else:
            typ, data = self._conn.uid("search", None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return []
        return data[0].decode().split()

    def fetch_mail_headers(self, uid: str, folder: str = "INBOX") -> Optional[Dict]:
        """Lädt nur die Header einer Mail (schnell, ohne Body)."""
        self.select_folder(folder)
        typ, data = self._conn.uid(
            "fetch", uid,
            "(RFC822.SIZE FLAGS BODY.PEEK[HEADER.FIELDS "
            "(Subject From To Cc Date Message-ID)])")
        if typ != "OK" or not data or data[0] is None:
            return None
        raw = data[0][1] if isinstance(data[0], tuple) else data[0]
        if not raw:
            return None
        msg = email.message_from_bytes(raw, policy=email.policy.compat32)
        result = self.parse_email_message(raw)
        # Flags aus dem Response holen
        flags_raw = str(data[0][0]) if isinstance(data[0], tuple) else ""
        result["is_read"]    = int("\\Seen"    in flags_raw)
        result["is_flagged"] = int("\\Flagged" in flags_raw)
        result["uid"]        = uid
        # Größe
        size_m = re.search(r"RFC822\.SIZE (\d+)", flags_raw)
        result["size"] = int(size_m.group(1)) if size_m else 0
        return result

    def fetch_mail(self, uid: str, folder: str = "INBOX") -> Optional[Dict]:
        """Lädt den vollständigen Inhalt einer Mail inkl. Anhänge."""
        self.select_folder(folder)
        typ, data = self._conn.uid("fetch", uid, "(FLAGS RFC822)")
        if typ != "OK" or not data or data[0] is None:
            return None
        raw = data[0][1] if isinstance(data[0], tuple) else data[0]
        if not raw:
            return None
        result = self.parse_email_message(raw, include_attachments=True)
        flags_raw = str(data[0][0]) if isinstance(data[0], tuple) else ""
        result["is_read"]    = int("\\Seen"    in flags_raw)
        result["is_flagged"] = int("\\Flagged" in flags_raw)
        result["uid"]        = uid
        return result

    def fetch_new_mails(self, folder: str = "INBOX",
                        known_uids: set = None) -> List[Dict]:
        """
        Ruft neue (unbekannte) Mails ab.
        known_uids: Set bereits bekannter UIDs → werden übersprungen.
        Gibt Liste von Mail-Dicts zurück.
        """
        known_uids = known_uids or set()
        all_uids   = self.fetch_all_uids(folder)
        new_uids   = [u for u in all_uids if u not in known_uids]
        mails = []
        for uid in new_uids:
            try:
                m = self.fetch_mail(uid, folder)
                if m:
                    mails.append(m)
            except Exception:
                pass
        return mails

    # ------------------------------------------------------------------ #
    #  Operationen                                                        #
    # ------------------------------------------------------------------ #

    def mark_read(self, uid: str, folder: str = "INBOX"):
        self.select_folder(folder)
        self._conn.uid("store", uid, "+FLAGS", "\\Seen")

    def mark_unread(self, uid: str, folder: str = "INBOX"):
        self.select_folder(folder)
        self._conn.uid("store", uid, "-FLAGS", "\\Seen")

    def mark_flagged(self, uid: str, folder: str = "INBOX"):
        self.select_folder(folder)
        self._conn.uid("store", uid, "+FLAGS", "\\Flagged")

    def delete_mail(self, uid: str, folder: str = "INBOX"):
        """Löscht eine Mail: \\Deleted setzen + EXPUNGE."""
        self.select_folder(folder)
        self._conn.uid("store", uid, "+FLAGS", "\\Deleted")
        self._conn.expunge()

    def move_mail(self, uid: str, from_folder: str, to_folder: str):
        """
        Verschiebt eine Mail. Nutzt MOVE (RFC 6851) falls verfügbar,
        sonst COPY + DELETE.
        """
        self.select_folder(from_folder)
        caps = str(self._conn.capabilities)
        if "MOVE" in caps:
            self._conn.uid("move", uid, f'"{to_folder}"')
        else:
            self._conn.uid("copy", uid, f'"{to_folder}"')
            self._conn.uid("store", uid, "+FLAGS", "\\Deleted")
            self._conn.expunge()

    def append_mail(self, folder: str, raw_message: bytes,
                    flags: str = "\\Seen") -> bool:
        """Speichert eine Mail direkt auf dem Server (z.B. Gesendet)."""
        try:
            self._conn.append(
                f'"{folder}"', f"({flags})",
                imaplib.Time2Internaldate(datetime.now()),
                raw_message
            )
            return True
        except Exception:
            return False

    def create_folder(self, folder_path: str) -> bool:
        typ, _ = self._conn.create(f'"{folder_path}"')
        return typ == "OK"

    def delete_folder(self, folder_path: str) -> bool:
        typ, _ = self._conn.delete(f'"{folder_path}"')
        return typ == "OK"

    # ------------------------------------------------------------------ #
    #  Parsing                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def decode_header_value(value: str) -> str:
        if not value:
            return ""
        parts = _decode_header(value)
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)

    @classmethod
    def parse_email_message(cls, raw_bytes: bytes,
                             include_attachments: bool = False) -> Dict:
        """
        Parst eine RFC-2822-Mail vollständig.
        Gibt ein Mail-Dict zurück das direkt in die DB gespeichert werden kann.
        """
        msg = email.message_from_bytes(raw_bytes, policy=email.policy.compat32)

        subject    = cls.decode_header_value(msg.get("Subject", ""))
        from_raw   = cls.decode_header_value(msg.get("From", ""))
        to_field   = cls.decode_header_value(msg.get("To", ""))
        cc_field   = cls.decode_header_value(msg.get("Cc", ""))
        date_str   = msg.get("Date", "")
        message_id = msg.get("Message-ID", "")

        # Absender in Name und E-Mail trennen
        sender_name, sender_email = cls._split_address(from_raw)

        # Datum normalisieren
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            date_norm = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            date_norm = date_str[:19] if date_str else ""

        body_text   = ""
        body_html   = ""
        has_attach  = False
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp  = str(part.get("Content-Disposition", ""))
                if "attachment" in disp or "inline" in disp and part.get_filename():
                    has_attach = True
                    if include_attachments:
                        fn   = cls.decode_header_value(part.get_filename() or "")
                        data = part.get_payload(decode=True) or b""
                        attachments.append({
                            "filename":  fn,
                            "mime_type": ctype,
                            "size":      len(data),
                            "data":      data,
                        })
                    continue
                if ctype == "text/plain" and not body_text:
                    cs = part.get_content_charset() or "utf-8"
                    pl = part.get_payload(decode=True)
                    if pl: body_text = pl.decode(cs, errors="replace")
                elif ctype == "text/html" and not body_html:
                    cs = part.get_content_charset() or "utf-8"
                    pl = part.get_payload(decode=True)
                    if pl: body_html = pl.decode(cs, errors="replace")
        else:
            cs = msg.get_content_charset() or "utf-8"
            pl = msg.get_payload(decode=True)
            if pl:
                if msg.get_content_type() == "text/html":
                    body_html = pl.decode(cs, errors="replace")
                else:
                    body_text = pl.decode(cs, errors="replace")

        result = {
            "subject":     subject,
            "sender":      sender_email,
            "sender_name": sender_name,
            "recipients":  to_field,
            "cc":          cc_field,
            "date":        date_norm,
            "body_text":   body_text,
            "body_html":   body_html,
            "has_attach":  int(has_attach),
            "message_id":  message_id,
            "is_read":     0,
            "is_flagged":  0,
            "size":        len(raw_bytes),
        }
        if include_attachments:
            result["attachments"] = attachments
        return result

    @staticmethod
    def _split_address(raw: str) -> Tuple[str, str]:
        """Trennt "Name <email>" in (Name, email)."""
        raw = raw.strip()
        m = re.match(r'^(.*?)\s*<([^>]+)>\s*$', raw)
        if m:
            return m.group(1).strip().strip('"'), m.group(2).strip()
        if "@" in raw:
            return "", raw
        return raw, ""
