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

        # Addons laden und deren Sprachdateien einlesen
        self.addon_manager.load_all(self.controller, lang=lang)

        self.frame = MainFrame(
            parent=None,
            title="MailClient",
            controller=self.controller
        )
        self.frame.Show()
        self.SetTopWindow(self.frame)
        return True

    def OnExit(self):
        self.db_manager.close()
        return 0


def main():
    app = MailClientApp(False)
    app.MainLoop()


if __name__ == "__main__":
    main()
