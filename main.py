"""
MailClient - Screenreader-optimierter E-Mail-Client
Einstiegspunkt der Anwendung
"""

import wx
import sys
import os

# Projektpfad zum sys.path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import DatabaseManager
from ui.main_frame import MainFrame
from core.app_controller import AppController
from core.addon_manager import AddonManager


class MailClientApp(wx.App):
    """Hauptanwendungsklasse"""

    def OnInit(self):
        # Datenbank initialisieren
        self.db_manager = DatabaseManager()
        self.db_manager.initialize()

        # Addon-Manager initialisieren
        self.addon_manager = AddonManager()

        # App-Controller initialisieren
        self.controller = AppController(self.db_manager, self.addon_manager)

        # Hauptfenster erstellen
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
