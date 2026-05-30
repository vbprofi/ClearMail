"""
imap_sync.py – Effiziente IMAP-Synchronisierung nach dem UID-Bereichs-Prinzip.

Technik (aus dem Artikel):
  SEARCH UID last_uid:*
  → liefert alle UIDs >= last_uid
  → der Server gibt immer mindestens die letzte bekannte UID zurück
  → nur UIDs > last_uid sind wirklich neu

Vorteile gegenüber SEARCH ALL:
  - Kein vollständiger Index-Scan des Ordners
  - Skaliert bei 100.000+ Mails ohne Zeitverlust
  - Exakt das gleiche Verfahren wie Thunderbird/Outlook Express
  - Ordner-Integrität: UIDs sind monoton wachsend (RFC 3501 §2.3.1.1)

Sicherheitsstandards:
  - SSL/TLS (993) oder STARTTLS (143) mit ssl.create_default_context()
  - AUTH=PLAIN mit Base64 oder IMAP LOGIN als Fallback
"""

from __future__ import annotations
import imaplib
from core.protocol_runner import log
import email
import email.policy
import ssl
import re
import base64
from email.header import decode_header as _dh
from email.utils import parsedate_to_datetime
from datetime import datetime
from typing import Generator, Optional, Tuple, List


class IMAPSync:
    """
    Zustandsloser IMAP-Syncer.
    Verbindet sich, synchronisiert, trennt Verbindung.
    """

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

    def connect(self):
        log("info", f"IMAP connect: {self.host}:{self.port} ssl={self.use_ssl} user={self.username}")
        ctx = ssl.create_default_context()
        if not self.verify_cert:
            ctx.check_hostname = False
            ctx.verify_mode    = ssl.CERT_NONE

        if self.use_ssl:
            self._conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx)
        else:
            self._conn = imaplib.IMAP4(self.host, self.port)
            if "STARTTLS" in self._get_caps():
                log("info", "IMAP STARTTLS negotiated")
                self._conn.starttls(ssl_context=ctx)

        self._authenticate()

    def disconnect(self):
        if self._conn:
            log("info", f"IMAP disconnect: {self.host}")
            try: self._conn.logout()
            except Exception: pass
            self._conn = None

    def __enter__(self):
        self.connect(); return self

    def __exit__(self, *_):
        self.disconnect()

    def _get_caps(self) -> str:
        try:
            _, data = self._conn.capability()
            return data[0].decode() if data else ""
        except Exception:
            return ""

    def _authenticate(self):
        caps = self._get_caps()
        log("info", f"IMAP AUTH caps: {caps[:80]}")
        if "AUTH=PLAIN" in caps:
            try:
                cred = base64.b64encode(
                    f"\x00{self.username}\x00{self.password}".encode()
                ).decode()
                self._conn.authenticate("PLAIN", lambda _: cred)
                log("info", "IMAP AUTH=PLAIN OK")
                return
            except imaplib.IMAP4.error:
                pass
        self._conn.login(self.username, self.password)
        log("info", "IMAP LOGIN OK")

    # ------------------------------------------------------------------ #
    #  Ordner-Liste                                                       #
    # ------------------------------------------------------------------ #

    def list_folders(self) -> List[dict]:
        """Listet alle selektierbaren Ordner auf."""
        typ, data = self._conn.list()
        if typ != "OK":
            return []
        folders = []
        for item in data:
            if item is None: continue
            line = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)
            m = re.match(r'\(([^)]*)\)\s+"([^"]+)"\s+"?([^"\r\n]+)"?', line.strip())
            if not m:
                m = re.match(r'\(([^)]*)\)\s+\S+\s+(.+)', line.strip())
                if not m: continue
            flags_str = m.group(1)
            sep       = m.group(2) if m.lastindex >= 2 else "/"
            path      = m.group(3).strip().strip('"') if m.lastindex >= 3 else m.group(2).strip()
            flags     = flags_str.split()
            if "\\Noselect" in flags:
                continue
            folders.append({
                "path":      path,
                "name":      path.split(sep)[-1] if sep in path else path,
                "separator": sep,
                "flags":     flags,
            })
        return folders

    # ------------------------------------------------------------------ #
    #  Kern-Sync: UID last_uid:*                                         #
    # ------------------------------------------------------------------ #

    def select_folder(self, folder_path: str) -> int:
        """Selektiert einen Ordner. Versucht mehrere Schreibweisen."""
        log("debug", f"IMAP SELECT {folder_path!r}")
        for attempt in (f'"{folder_path}"', folder_path,
                        f'"{self._utf7(folder_path)}"', self._utf7(folder_path)):
            try:
                typ, data = self._conn.select(attempt)
                if typ == "OK" and data and data[0]:
                    return int(data[0])
            except Exception:
                pass
        return 0

    def get_max_uid(self, folder_path: str) -> int:
        """
        Gibt die höchste lokal bekannte UID zurück (oder 0).
        Wird extern übergeben (kommt aus der DB).
        """
        return 0  # Platzhalter – wird von _fetch_imap übergeben

    def new_mails_since(self, folder_path: str,
                        last_uid: int) -> Generator[Tuple[str, bytes], None, None]:
        """
        Generator: liefert (uid_str, raw_bytes) für jede Mail mit UID > last_uid.

        Technik: SEARCH UID {last_uid}:*
        Der IMAP-Server gibt immer mindestens die letzte bekannte UID zurück
        (auch wenn keine neuen Mails vorhanden sind). Daher: nur UIDs > last_uid
        sind wirklich neu.

        RFC 3501 §6.4.4: "The UID SEARCH command is identical to the SEARCH
        command with the UID modifier; UIDs correspond to the sequence numbering
        for the virtual mailbox created by the search."
        """
        count = self.select_folder(folder_path)
        if count == 0:
            return

        # UID-Suche: alle Mails ab last_uid (inkl. last_uid selbst)
        search_range = f"{max(1, last_uid)}:*"
        log("info", f"IMAP UID SEARCH {folder_path!r} UID {search_range}")
        typ, data = self._conn.uid("search", None, f"UID {search_range}")
        if typ != "OK" or not data or not data[0]:
            return

        uid_list = data[0].split()
        for uid_bytes in uid_list:
            uid = int(uid_bytes)
            # Immer mindestens last_uid zurückgegeben → nur echte neue laden
            if uid <= last_uid:
                continue
            uid_str = str(uid)
            log("debug", f"IMAP FETCH UID {uid_str} ({folder_path!r})")
            try:
                typ2, raw_data = self._conn.uid("fetch", uid_str, "(FLAGS RFC822)")
                if typ2 != "OK" or not raw_data or raw_data[0] is None:
                    continue
                flags_raw = raw_data[0][0] if isinstance(raw_data[0], tuple) else b""
                raw_body  = raw_data[0][1] if isinstance(raw_data[0], tuple) else raw_data[0]
                if raw_body:
                    yield uid_str, raw_body, flags_raw
            except Exception as _e:
                log("error", f"IMAP FETCH UID error: {_e}")
                continue

    def fetch_flags_update(self, folder_path: str,
                           uid_map: dict[str, int]) -> dict[str, dict]:
        """
        Aktualisiert \\Seen und \\Flagged für bekannte UIDs.
        uid_map: {uid_str: local_mail_id}
        Rückgabe: {uid_str: {"is_read": 0|1, "is_flagged": 0|1}}
        """
        if not uid_map:
            return {}
        self.select_folder(folder_path)
        uid_set = ",".join(uid_map.keys())
        try:
            typ, data = self._conn.uid("fetch", uid_set, "(FLAGS)")
        except Exception:
            return {}
        if typ != "OK" or not data:
            return {}

        result = {}
        for item in data:
            if not isinstance(item, tuple):
                continue
            flags_str = item[0].decode("utf-8", errors="replace") if isinstance(item[0], bytes) else str(item[0])
            uid_m = re.search(r"UID (\d+)", flags_str)
            if not uid_m:
                continue
            uid = uid_m.group(1)
            result[uid] = {
                "is_read":    int("\\Seen"    in flags_str),
                "is_flagged": int("\\Flagged" in flags_str),
            }
        return result

    # ------------------------------------------------------------------ #
    #  Mail-Parsing                                                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def parse_mail(cls, uid: str, raw: bytes, flags_raw: bytes | str) -> dict:
        """Parst eine RFC-2822-Mail zu einem Mail-Dict."""
        flags = flags_raw.decode("utf-8", errors="replace") if isinstance(flags_raw, bytes) else str(flags_raw)
        msg   = email.message_from_bytes(raw, policy=email.policy.compat32)

        subject    = cls._decode_hdr(msg.get("Subject", ""))
        from_raw   = cls._decode_hdr(msg.get("From", ""))
        to_field   = cls._decode_hdr(msg.get("To", ""))
        cc_field   = cls._decode_hdr(msg.get("Cc", ""))
        date_str   = msg.get("Date", "")
        message_id = msg.get("Message-ID", "")

        sender_name, sender_email = cls._split_addr(from_raw)

        try:
            dt        = parsedate_to_datetime(date_str)
            date_norm = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            date_norm = date_str[:19]

        body_text = ""
        body_html = ""
        has_attach = False
        attachments: list[dict] = []

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp  = str(part.get("Content-Disposition", ""))
                if "attachment" in disp or ("inline" in disp and part.get_filename()):
                    has_attach = True
                    fn   = cls._decode_hdr(part.get_filename() or "")
                    data = part.get_payload(decode=True) or b""
                    attachments.append({"filename": fn, "mime_type": ctype,
                                        "size": len(data), "data": data})
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

        return {
            "uid":         uid,
            "subject":     subject,
            "sender":      sender_email,
            "sender_name": sender_name,
            "recipients":  to_field,
            "cc":          cc_field,
            "date":        date_norm,
            "body_text":   body_text,
            "body_html":   body_html,
            "has_attach":  int(has_attach),
            "attachments": attachments,
            "message_id":  message_id,
            "is_read":     int("\\Seen"    in flags),
            "is_flagged":  int("\\Flagged" in flags),
            "size":        len(raw),
        }

    @staticmethod
    def _decode_hdr(value: str) -> str:
        if not value: return ""
        parts = _dh(value)
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)

    @staticmethod
    def _split_addr(raw: str) -> tuple[str, str]:
        raw = raw.strip()
        m = re.match(r'^(.*?)\s*<([^>]+)>\s*$', raw)
        if m: return m.group(1).strip().strip('"'), m.group(2).strip()
        if "@" in raw: return "", raw
        return raw, ""

    @staticmethod
    def _utf7(name: str) -> str:
        try:
            return name.encode("utf-7").decode("ascii").replace("+", "&").replace("&-", "+")
        except Exception:
            return name
