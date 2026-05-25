"""
AppController – MVC-Controller-Schicht
"""

from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from database.db_manager import DatabaseManager
    from core.addon_manager import AddonManager


class AppController:

    def __init__(self, db: "DatabaseManager", addon_mgr: "AddonManager"):
        self.db        = db
        self.addon_mgr = addon_mgr
        self._imap_handler = None
        self._pop3_handler = None
        self._smtp_handler = None
        self.view = None

    # ------------------------------------------------------------------ #
    #  Postfächer & Ordner                                                #
    # ------------------------------------------------------------------ #

    def get_mailboxes(self) -> list:
        return self.db.get_mailboxes()

    def get_folders(self, mailbox_id: int) -> list:
        return self.db.get_folders(mailbox_id)

    def get_folder_tree(self, mailbox_id: int) -> list:
        folders  = self.db.get_folders(mailbox_id)
        by_parent = {}
        for f in folders:
            by_parent.setdefault(f["parent_id"], []).append(dict(f))
        def build(pid):
            r = []
            for f in by_parent.get(pid, []):
                f["children"] = build(f["id"])
                r.append(f)
            return r
        return build(None)

    def get_trash_folder_id(self, mailbox_id: int) -> Optional[int]:
        """Gibt die ID des Papierkorb-Ordners für ein Postfach zurück."""
        for f in self.db.get_folders(mailbox_id):
            if f["folder_type"] == "trash":
                return f["id"]
        return None

    # ------------------------------------------------------------------ #
    #  Mails                                                              #
    # ------------------------------------------------------------------ #

    def get_mails(self, folder_id: int) -> list:
        return self.db.get_mails(folder_id)

    def get_mail(self, mail_id: int):
        mail = self.db.get_mail(mail_id)
        if mail and not mail["is_read"]:
            self.db.mark_mail_read(mail_id, True)
            self.db.update_folder_unread(mail["folder_id"])
            self.addon_mgr.fire("mail_read", {"mail_id": mail_id})
        return mail

    def delete_mail(self, mail_id: int, folder_id: int,
                    mailbox_id: int = None, use_trash: bool = None):
        """
        Löscht eine Mail direkt oder verschiebt sie in den Papierkorb.

        use_trash=None → Einstellung aus DB lesen
        use_trash=True → in Papierkorb verschieben
        use_trash=False → direkt löschen
        """
        if use_trash is None:
            use_trash = self.db.get_setting("delete_to_trash", "1") == "1"

        # Schon im Papierkorb? → immer direkt löschen
        if use_trash and mailbox_id:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id and folder_id == trash_id:
                use_trash = False

        if use_trash and mailbox_id:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id:
                self.db.move_mail(mail_id, trash_id)
                self.db.update_folder_unread(folder_id)
                self.db.update_folder_unread(trash_id)
                self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": trash_id})
                return "moved_to_trash"

        self.db.delete_mail(mail_id)
        self.db.update_folder_unread(folder_id)
        self.addon_mgr.fire("mail_deleted", {"mail_id": mail_id})
        return "deleted"

    def move_mail(self, mail_id: int, target_folder_id: int):
        self.db.move_mail(mail_id, target_folder_id)
        self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": target_folder_id})

    def mark_mail_flagged(self, mail_id: int, flagged: bool):
        self.db.mark_mail_flagged(mail_id, flagged)

    def mark_mail_read(self, mail_id: int, is_read: bool):
        self.db.mark_mail_read(mail_id, is_read)

    # ------------------------------------------------------------------ #
    #  Ordner löschen                                                     #
    # ------------------------------------------------------------------ #

    def delete_folder(self, folder_id: int, mailbox_id: int,
                      use_trash: bool = None) -> str:
        """
        Löscht einen Ordner. use_trash=True: Mails in Papierkorb, Ordner entfernen.
        Gibt 'deleted' oder 'moved_to_trash' zurück.
        """
        if use_trash is None:
            use_trash = self.db.get_setting("delete_to_trash", "1") == "1"

        conn = self.db._get_mailstore_conn()

        if use_trash:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id and trash_id != folder_id:
                # Alle Mails in den Papierkorb verschieben
                conn.execute(
                    "UPDATE mails SET folder_id = ? WHERE folder_id = ?",
                    (trash_id, folder_id)
                )
                conn.commit()
                self.db.update_folder_unread(trash_id)

        # Unterordner-Mails löschen, dann Ordner
        conn.execute(
            "DELETE FROM mails WHERE folder_id IN "
            "(SELECT id FROM folders WHERE id = ? OR parent_id = ?)",
            (folder_id, folder_id)
        )
        conn.execute("DELETE FROM folders WHERE parent_id = ?", (folder_id,))
        conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        conn.commit()
        return "deleted"

    # ------------------------------------------------------------------ #
    #  Mail-Export / -Import                                              #
    # ------------------------------------------------------------------ #

    def save_mail_as_email(self, mail_id: int, path: str) -> bool:
        mail = self.db.get_mail(mail_id)
        if not mail:
            return False
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dict(mail), f, ensure_ascii=False, indent=2, default=str)
            return True
        except OSError:
            return False

    def open_email_file(self, path: str) -> Optional[dict]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def save_mail_as_txt(self, mail_id: int, path: str) -> bool:
        mail = self.db.get_mail(mail_id)
        if not mail:
            return False
        lines = [
            f"Von:     {mail['sender_name']} <{mail['sender']}>",
            f"An:      {mail['recipients']}",
            f"Betreff: {mail['subject']}",
            f"Datum:   {mail['date']}",
            "",
            mail["body_text"] or "",
        ]
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------ #
    #  Konten                                                             #
    # ------------------------------------------------------------------ #

    def get_accounts(self) -> list:
        return self.db.get_accounts()

    def get_account(self, account_id: int):
        return self.db.get_account(account_id)

    def save_account(self, data: dict) -> int:
        return self.db.save_account(data)

    def delete_account(self, account_id: int):
        self.db.delete_account(account_id)

    # ------------------------------------------------------------------ #
    #  Einstellungen                                                      #
    # ------------------------------------------------------------------ #

    def get_setting(self, key: str, default: str = "") -> str:
        return self.db.get_setting(key, default)

    def set_setting(self, key: str, value: str):
        self.db.set_setting(key, value)

    # ------------------------------------------------------------------ #
    #  Protokoll-Platzhalter                                              #
    # ------------------------------------------------------------------ #

    def fetch_new_mails(self, account_id: int):
        raise NotImplementedError("IMAP/POP3-Protokoll noch nicht implementiert.")

    def send_mail(self, account_id: int, mail_data: dict):
        raise NotImplementedError("SMTP-Protokoll noch nicht implementiert.")
