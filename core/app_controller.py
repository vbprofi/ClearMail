"""
AppController – MVC-Controller-Schicht
Verbindet Datenbankzugriff, Protokoll-Handler und UI-Events.
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
    """Zentrale Steuerungsschicht (Controller im MVC)."""

    def __init__(self, db: "DatabaseManager", addon_mgr: "AddonManager"):
        self.db = db
        self.addon_mgr = addon_mgr

        # Protokoll-Handler (werden bei Bedarf geladen)
        self._imap_handler = None   # Platzhalter: protocols.imap_handler.IMAPHandler
        self._pop3_handler = None   # Platzhalter: protocols.pop3_handler.POP3Handler
        self._smtp_handler = None   # Platzhalter: protocols.smtp_handler.SMTPHandler

        # UI-Referenz (wird vom MainFrame gesetzt)
        self.view = None

    # ------------------------------------------------------------------ #
    #  Postfächer & Ordner                                                #
    # ------------------------------------------------------------------ #

    def get_mailboxes(self) -> list:
        return self.db.get_mailboxes()

    def get_folders(self, mailbox_id: int) -> list:
        return self.db.get_folders(mailbox_id)

    def get_folder_tree(self, mailbox_id: int) -> list:
        """Gibt Ordner als hierarchische Struktur zurück."""
        folders = self.db.get_folders(mailbox_id)
        # Ordner nach parent_id gruppieren
        by_parent = {}
        for f in folders:
            pid = f["parent_id"]
            by_parent.setdefault(pid, []).append(dict(f))

        def build(parent_id):
            result = []
            for f in by_parent.get(parent_id, []):
                f["children"] = build(f["id"])
                result.append(f)
            return result

        return build(None)

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

    def delete_mail(self, mail_id: int, folder_id: int):
        self.db.delete_mail(mail_id)
        self.db.update_folder_unread(folder_id)
        self.addon_mgr.fire("mail_deleted", {"mail_id": mail_id})

    def move_mail(self, mail_id: int, target_folder_id: int):
        self.db.move_mail(mail_id, target_folder_id)
        self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": target_folder_id})

    def mark_mail_flagged(self, mail_id: int, flagged: bool):
        self.db.mark_mail_flagged(mail_id, flagged)

    def mark_mail_read(self, mail_id: int, is_read: bool):
        self.db.mark_mail_read(mail_id, is_read)

    # ------------------------------------------------------------------ #
    #  Mail speichern / exportieren                                       #
    # ------------------------------------------------------------------ #

    def save_mail_as_email(self, mail_id: int, path: str) -> bool:
        """Speichert eine Mail als .email-Datei (JSON-Format)."""
        mail = self.db.get_mail(mail_id)
        if not mail:
            return False
        data = dict(mail)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            return True
        except OSError:
            return False

    def open_email_file(self, path: str) -> Optional[dict]:
        """Öffnet eine .email-Datei und gibt die Daten zurück."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def save_mail_as_txt(self, mail_id: int, path: str) -> bool:
        """Speichert den Mailtext als .txt-Datei."""
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
    #  Protokoll-Schnittstellen (Platzhalter für spätere Implementierung) #
    # ------------------------------------------------------------------ #

    def fetch_new_mails(self, account_id: int):
        """
        Platzhalter: IMAP/POP3-Abruf.
        Wird später durch protocols.imap_handler oder pop3_handler ersetzt.
        """
        # TODO: IMAPHandler / POP3Handler laden und nutzen
        raise NotImplementedError("IMAP/POP3-Protokoll noch nicht implementiert.")

    def send_mail(self, account_id: int, mail_data: dict):
        """
        Platzhalter: SMTP-Versand.
        Wird später durch protocols.smtp_handler ersetzt.
        """
        # TODO: SMTPHandler laden und nutzen
        raise NotImplementedError("SMTP-Protokoll noch nicht implementiert.")
