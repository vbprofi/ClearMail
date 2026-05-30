"""
MailClient - Screenreader-optimierter E-Mail-Client
Einstiegspunkt der Anwendung
"""

import wx
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.i18n import set_language, load_addon_translations
from database.db_manager import DatabaseManager
from ui.main_frame import MainFrame
from core.app_controller import AppController
from core.addon_manager import AddonManager


class MailClientApp(wx.App):

    def OnInit(self):
        self.db_manager = DatabaseManager()
        self.db_manager.initialize()

        # Sprache aus Einstellungen laden
        lang = self.db_manager.get_setting("language", "de")
        set_language(lang)

        app_addon_dir  = os.path.join(BASE_DIR, "addons")
        user_addon_dir = os.path.join(os.path.expanduser("~"), ".mailclient", "addons")
        self.addon_manager = AddonManager(
            app_dir=app_addon_dir,
            user_dir=user_addon_dir
        )

        self.controller = AppController(self.db_manager, self.addon_manager)

        # Verbindungs-Logging aktivieren falls in Einstellungen aktiviert
        if self.db_manager.get_setting("dev_logging", "0") == "1":
            from core.protocol_runner import setup_logging, get_log_path
            import os as _os
            log_path = self.db_manager.get_setting(
                "dev_log_path",
                get_log_path(_os.path.join(_os.path.expanduser("~"), ".mailclient"))
            )
            setup_logging(log_path)

        # Addons laden und deren Sprachdateien einlesen
        self.addon_manager.load_all(self.controller, lang=lang)

        self.frame = MainFrame(
            parent=None,
            title="MailClient",
            controller=self.controller
        )
        self.frame.Show()
        self.SetTopWindow(self.frame)
        # Letzten ausgewählten Ordner wiederherstellen / Ersteinrichtung
        wx.CallAfter(self._post_start)
        return True

    def _post_start(self):
        """Wird nach dem ersten Paint aufgerufen."""
        if self.controller.is_first_run():
            from ui.dialogs import SetupDialog, AccountDialog
            dlg    = SetupDialog(self.frame, self.controller)
            result = dlg.ShowModal()
            dlg.Destroy()

            if result == wx.ID_OK:
                acc_dlg = AccountDialog(self.frame, self.controller)
                acc_dlg.ShowModal()
                acc_dlg.Destroy()

            # Lokalen Ordner IMMER anlegen (unabhängig davon ob ein
            # Mail-Konto angelegt wurde oder nicht)
            self._ensure_local_account()

            self.frame.folder_panel.reload()
            # Willkommensmail in Posteingang der Lokalen Ordner ablegen
            wx.CallAfter(self._place_welcome_mail)
        else:
            self.frame._restore_last_folder()

    def _ensure_local_account(self):
        """Stellt sicher dass Lokale Ordner vorhanden ist."""
        try:
            conn = self.db_manager._get_accounts_conn()
            row  = conn.execute(
                "SELECT id FROM accounts WHERE protocol='LOCAL'"
            ).fetchone()
            if not row:
                self._create_default_local_account()
        except Exception:
            self._create_default_local_account()

    def _place_welcome_mail(self):
        """Legt die Willkommensmail in den Posteingang der Lokalen Ordner."""
        try:
            # Schritt 1: LOCAL-Konto-IDs aus accounts.db holen
            acc_conn = self.db_manager._get_accounts_conn()
            local_ids = [
                r[0] for r in acc_conn.execute(
                    "SELECT id FROM accounts WHERE protocol='LOCAL'"
                ).fetchall()
            ]
            if not local_ids:
                return

            # Schritt 2: Posteingang in structure.db suchen (kein Cross-DB-JOIN)
            sc = self.db_manager._get_structure_conn()
            placeholders = ",".join("?" for _ in local_ids)
            row = sc.execute(
                f"SELECT f.id FROM folders f "
                f"JOIN mailboxes mb ON f.mailbox_id=mb.id "
                f"WHERE mb.account_id IN ({placeholders}) "
                f"AND f.folder_type='inbox'",
                local_ids
            ).fetchone()

            if row:
                self.controller.create_welcome_mail(row[0])
                wx.CallAfter(self.frame.folder_panel.reload)
        except Exception:
            pass

    def _create_default_local_account(self):
        """Legt ein Standard-Lokalkonto an (rein lokal, kein Mail-Server)."""
        try:
            self.controller.db.create_local_account("Lokale Ordner", "local")
        except Exception:
            # Fallback falls create_local_account nicht vorhanden
            self.controller.save_account({
                "id":       None,
                "name":     "Lokale Ordner",
                "email":    "local",
                "protocol": "LOCAL",
                "in_host":  "", "in_port":  0, "in_ssl":  0,
                "out_host": "", "out_port": 0, "out_ssl": 0,
                "username": "", "password": "",
            })

    def OnExit(self):
        self.db_manager.close()
        return 0


def main():
    app = MailClientApp(False)
    app.MainLoop()


if __name__ == "__main__":
    main()
