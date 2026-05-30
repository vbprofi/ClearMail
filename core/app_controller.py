"""
AppController – MVC-Controller-Schicht
"""

from __future__ import annotations
import os, json
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from database.db_manager import DatabaseManager
    from core.addon_manager import AddonManager


class AppController:

    def __init__(self, db: "DatabaseManager", addon_mgr: "AddonManager"):
        self.db        = db
        self.addon_mgr = addon_mgr
        self.view      = None

    # ------------------------------------------------------------------ #
    #  Struktur                                                           #
    # ------------------------------------------------------------------ #

    def get_mailboxes(self): return self.db.get_mailboxes()
    def get_folders(self, mailbox_id: int): return self.db.get_folders(mailbox_id)

    def get_trash_folder_id(self, mailbox_id: int) -> Optional[int]:
        for f in self.db.get_folders(mailbox_id):
            if f["folder_type"] == "trash":
                return f["id"]
        return None

    # ------------------------------------------------------------------ #
    #  Mails                                                              #
    # ------------------------------------------------------------------ #

    def get_mails(self, folder_id: int) -> list:
        return self.db.get_mails(folder_id)

    def get_mail(self, mail_id: int, folder_id: int = None):
        mail = self.db.get_mail(mail_id, folder_id)
        if mail and not int(mail["is_read"] or 0):
            fid = int(mail["folder_id"] or folder_id or 0)
            self.db.mark_mail_read(mail_id, True, folder_id=fid)
            if fid:
                self.db.update_folder_unread(fid)
            self.addon_mgr.fire("mail_read", {"mail_id": mail_id})
        return mail

    def delete_mail(self, mail_id: int, folder_id: int,
                    mailbox_id: int = None, use_trash: bool = None) -> str:
        if use_trash is None:
            use_trash = self.db.get_setting("delete_to_trash", "1") == "1"
        if use_trash and mailbox_id:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id and folder_id == trash_id:
                use_trash = False
        if use_trash and mailbox_id:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id:
                self.db.move_mail(mail_id, trash_id, source_folder_id=folder_id)
                self.db.update_folder_unread(folder_id)
                self.db.update_folder_unread(trash_id)
                self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": trash_id})
                return "moved_to_trash"
        self.db.delete_mail(mail_id, folder_id)
        self.db.update_folder_unread(folder_id)
        self.addon_mgr.fire("mail_deleted", {"mail_id": mail_id})
        return "deleted"

    def move_mail(self, mail_id: int, target_folder_id: int, source_folder_id: int = None):
        self.db.move_mail(mail_id, target_folder_id, source_folder_id)
        self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": target_folder_id})

    def mark_mail_flagged(self, mail_id: int, flagged: bool, folder_id: int = None):
        self.db.mark_mail_flagged(mail_id, flagged, folder_id=folder_id)

    def mark_mail_read(self, mail_id: int, is_read: bool, folder_id: int = None):
        self.db.mark_mail_read(mail_id, is_read, folder_id=folder_id)

    def delete_folder(self, folder_id: int, mailbox_id: int, use_trash: bool = None) -> str:
        if use_trash is None:
            use_trash = self.db.get_setting("delete_to_trash", "1") == "1"
        mode = self.db.get_setting("mail_storage", "sqlite_one")
        sc   = self.db._get_structure_conn()
        if use_trash:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id and trash_id != folder_id:
                if mode == "sqlite_one":
                    sc.execute("UPDATE mails SET folder_id=? WHERE folder_id=?",
                               (trash_id, folder_id))
                    sc.commit()
                elif mode == "sqlite_per_account":
                    conn = self.db._mail_conn_for_folder(folder_id)
                    conn.execute("UPDATE mails SET folder_id=? WHERE folder_id=?",
                                 (trash_id, folder_id))
                    conn.commit()
                self.db.update_folder_unread(trash_id)
        if mode == "sqlite_one":
            sc.execute("DELETE FROM mails WHERE folder_id IN "
                       "(SELECT id FROM folders WHERE id=? OR parent_id=?)",
                       (folder_id, folder_id))
        elif mode == "sqlite_per_account":
            conn = self.db._mail_conn_for_folder(folder_id)
            conn.execute("DELETE FROM mails WHERE folder_id=?", (folder_id,))
            conn.commit()
        elif mode == "files":
            import shutil
            d = os.path.join(self.db.data_dir, "mailstore", str(folder_id))
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
        sc.execute("DELETE FROM folders WHERE parent_id=?", (folder_id,))
        sc.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        sc.commit()
        return "deleted"

    # ------------------------------------------------------------------ #
    #  Datei-Export/Import                                               #
    # ------------------------------------------------------------------ #

    def save_mail_as_email(self, mail_id: int, path: str,
                           folder_id: int = None) -> bool:
        mail = self.db.get_mail(mail_id, folder_id)
        if not mail: return False
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dict(mail), f, ensure_ascii=False, indent=2, default=str)
            return True
        except OSError: return False

    def save_mail_as_eml(self, mail_id: int, path: str,
                         folder_id: int = None) -> bool:
        """Speichert als RFC-2822-.eml-Datei."""
        mail = self.db.get_mail(mail_id, folder_id)
        if not mail: return False
        try:
            def h(n, v): return f"{n}: {str(v or '').replace(chr(10),' ')}\n"
            sn = str(mail["sender_name"] or "")
            se = str(mail["sender"] or "")
            from_f = f"{sn} <{se}>" if sn else se
            hdr  = h("From", from_f)
            hdr += h("To",      mail["recipients"])
            if mail["cc"]:  hdr += h("Cc", mail["cc"])
            hdr += h("Subject", mail["subject"])
            hdr += h("Date",    mail["date"])
            if mail["message_id"]: hdr += h("Message-ID", mail["message_id"])
            hdr += "MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n\n"
            with open(path, "w", encoding="utf-8") as f:
                f.write(hdr + str(mail["body_text"] or mail["body_html"] or ""))
            return True
        except OSError: return False

    def save_mail_as_txt(self, mail_id: int, path: str,
                         folder_id: int = None) -> bool:
        mail = self.db.get_mail(mail_id, folder_id)
        if not mail: return False
        try:
            lines = [
                f"Von:     {mail['sender_name']} <{mail['sender']}>",
                f"An:      {mail['recipients']}",
                f"Betreff: {mail['subject']}",
                f"Datum:   {mail['date']}", "",
                str(mail["body_text"] or ""),
            ]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
        except OSError: return False

    def open_mail_file(self, path: str) -> Optional[dict]:
        """Öffnet .email (JSON), .eml oder .txt und gibt Mail-Dict zurück."""
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".email":
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            elif ext == ".eml":
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return self._parse_eml_string(content, path)
            elif ext == ".txt":
                with open(path, encoding="utf-8", errors="replace") as f:
                    return {"subject": os.path.basename(path),
                            "body_text": f.read(), "sender": "", "recipients": ""}
        except (OSError, Exception):
            pass
        return None

    @staticmethod
    def _parse_eml_string(content: str, path: str = "") -> dict:
        """Parst RFC-2822-EML-Inhalt in ein Mail-Dict."""
        sep  = content.find("\n\n")
        header_txt = content[:sep] if sep != -1 else ""
        body       = content[sep+2:] if sep != -1 else content
        headers: dict = {}
        for line in header_txt.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()
        return {
            "subject":    headers.get("subject", os.path.basename(path)),
            "sender":     headers.get("from", ""),
            "sender_name":"",
            "recipients": headers.get("to", ""),
            "cc":         headers.get("cc", ""),
            "date":       headers.get("date", ""),
            "message_id": headers.get("message-id", ""),
            "body_text":  body,
            "body_html":  "",
            "is_read":    1,
            "is_flagged": 0,
            "has_attach": 0,
        }

    # ------------------------------------------------------------------ #
    #  Konten + Einstellungen                                            #
    # ------------------------------------------------------------------ #

    def get_accounts(self): return self.db.get_accounts()
    def get_account(self, aid): return self.db.get_account(aid)
    def save_account(self, data): return self.db.save_account(data)
    def delete_account(self, aid): self.db.delete_account(aid)
    def get_setting(self, key, default=""): return self.db.get_setting(key, default)
    def set_setting(self, key, value): self.db.set_setting(key, value)

    def fetch_new_mails(self, account_id: int):
        raise NotImplementedError("IMAP/POP3 noch nicht implementiert.")
    def send_mail(self, account_id: int, mail_data: dict):
        raise NotImplementedError("SMTP noch nicht implementiert.")

    def is_first_run(self) -> bool:
        return self.db.is_first_run()

    def search_mails(self, query: str, field: str = "all",
                     folder_id: int = None,
                     date_from: str = None, date_to: str = None) -> list:
        return self.db.search_mails(query, field, folder_id, date_from, date_to)

    def copy_mail(self, mail_id: int, target_folder_id: int,
                  source_folder_id: int = None) -> int:
        result = self.db.copy_mail(mail_id, target_folder_id, source_folder_id)
        self.db.update_folder_unread(target_folder_id)
        return result
