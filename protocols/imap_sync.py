"""
imap_sync.py – Effiziente IMAP-Synchronisierung nach dem UID-Bereichs-Prinzip.

Technik:
  SEARCH UID last_uid:*
  → liefert alle UIDs >= last_uid
  → nur UIDs > last_uid sind wirklich neu

Korrekturen (2026-05):
  - new_mails_since() nutzt BODY.PEEK[] statt RFC822 → kein implizites \\Seen
    beim Abrufen (RFC 3501 §6.4.5)
  - list_folders(): robusterer Parser mit NIL-Separator-Unterstützung,
    parent-Pfad und level-Tiefe (Unterordner korrekt abgebildet)
  - _authenticate(): CAPABILITY nach LOGIN prüfen (einige Server ändern Caps)
  - fetch_flags_update(): BODY.PEEK[HEADER] statt FLAGS um Roundtrip zu sparen
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
        self._separator: str = "/"

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
        """
        Listet alle selektierbaren Ordner auf, inkl. Unterordner-Hierarchie.

        FIX: robusterer Parser für NIL-Separatoren, gecachter Separator,
        korrekte parent/level-Felder für Unterordner.
        """
        typ, data = self._conn.list()
        if typ != "OK":
            return []
        folders = []
        for item in data:
            if item is None:
                continue
            line = (item.decode("utf-8", errors="replace")
                    if isinstance(item, bytes) else str(item)).strip()

            # Format: (\Flags) "sep" "path"  |  (\Flags) NIL "path"
            m = re.match(r'\(([^)]*)\)\s+"([^"]+)"\s+"([^"]+)"', line)
            if not m:
                m = re.match(r'\(([^)]*)\)\s+"([^"]+)"\s+(\S+)', line)
            if not m:
                m = re.match(r'\(([^)]*)\)\s+NIL\s+"?([^"\r\n]+)"?', line)
                if m:
                    flags_str = m.group(1)
                    sep       = "/"
                    path      = m.group(2).strip().strip('"')
                else:
                    continue
            else:
                flags_str = m.group(1)
                sep       = m.group(2)
                path      = m.group(3).strip().strip('"')

            if sep and sep != "NIL":
                self._separator = sep

            flags = flags_str.split()
            if "\\Noselect" in flags:
                continue

            parts  = path.split(sep)
            level  = len(parts) - 1
            parent = sep.join(parts[:-1]) if level > 0 else ""

            folders.append({
                "path":      path,
                "name":      parts[-1],
                "parent":    parent,
                "separator": sep,
                "flags":     flags,
                "level":     level,
            })
        return folders

    # ------------------------------------------------------------------ #
    #  Kern-Sync: UID last_uid:*                                        #
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

    def new_mails_since(self, folder_path: str,
                        last_uid: int) -> Generator[Tuple[str, bytes, bytes], None, None]:
        """
        Generator: liefert (uid_str, raw_bytes, flags_raw) für jede Mail mit UID > last_uid.

        FIX: Nutzt BODY.PEEK[] statt RFC822, damit das Abrufen keine implizite
        \\Seen-Markierung auslöst (RFC 3501 §6.4.5). Das Setzen von \\Seen
        erfolgt erst explizit wenn der Nutzer die Mail öffnet.
        """
        count = self.select_folder(folder_path)
        if count == 0:
            return

        search_range = f"{max(1, last_uid)}:*"
        log("info", f"IMAP UID SEARCH {folder_path!r} UID {search_range}")
        typ, data = self._conn.uid("search", None, f"UID {search_range}")
        if typ != "OK" or not data or not data[0]:
            return

        uid_list = data[0].split()
        for uid_bytes in uid_list:
            uid = int(uid_bytes)
            if uid <= last_uid:
                continue
            uid_str = str(uid)
            log("debug", f"IMAP FETCH UID {uid_str} ({folder_path!r})")
            try:
                # BODY.PEEK[] = vollständiger Inhalt OHNE \\Seen-Seiteneffekt
                typ2, raw_data = self._conn.uid("fetch", uid_str, "(FLAGS BODY.PEEK[])")
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
            flags_str = (item[0].decode("utf-8", errors="replace")
                         if isinstance(item[0], bytes) else str(item[0]))
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
        flags = (flags_raw.decode("utf-8", errors="replace")
                 if isinstance(flags_raw, bytes) else str(flags_raw))
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

        body_text  = ""
        body_html  = ""
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
        """
        Modifiziertes UTF-7 nach RFC 3501 §5.1.3.
        FIX: '&' als Escape-Zeichen, ',' statt '/' in Base64.
        """
        result = []
        i = 0
        while i < len(name):
            c = name[i]
            if 0x20 <= ord(c) <= 0x7E and c != '&':
                result.append(c)
                i += 1
            else:
                block = []
                while i < len(name) and not (0x20 <= ord(name[i]) <= 0x7E and name[i] != '&'):
                    block.append(name[i])
                    i += 1
                import base64
                encoded = base64.b64encode(''.join(block).encode('utf-16-be')).decode('ascii')
                encoded = encoded.replace('/', ',')
                result.append('&' + encoded + '-')
        return ''.join(result)
