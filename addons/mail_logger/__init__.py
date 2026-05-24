"""
Beispiel-Addon: MailLogger
Protokolliert alle Mail-Events in eine Logdatei.

Installation:
  1. Dieses Verzeichnis nach ~/.mailclient/addons/mail_logger/ kopieren
  2. MailClient neu starten
  3. Das Addon erscheint in Extras → Addon-Verwaltung
"""

import os
from datetime import datetime
from core.addon_manager import AddonBase


class Addon(AddonBase):
    """Beispiel-Addon: Protokolliert Mail-Events."""

    NAME        = "MailLogger"
    VERSION     = "1.0.0"
    DESCRIPTION = "Protokolliert Mail-Events in eine Logdatei"

    def __init__(self, controller):
        super().__init__(controller)
        self._log_path = os.path.join(
            os.path.expanduser("~"), ".mailclient", "mail_events.log"
        )

    def on_load(self):
        self._log("Addon geladen")

    def on_unload(self):
        self._log("Addon entladen")

    def on_mail_read(self, data: dict):
        self._log(f"Mail gelesen: id={data.get('mail_id')}")

    def on_mail_deleted(self, data: dict):
        self._log(f"Mail gelöscht: id={data.get('mail_id')}")

    def on_mail_moved(self, data: dict):
        self._log(f"Mail verschoben: id={data.get('mail_id')} → folder={data.get('folder_id')}")

    def get_menu_items(self) -> list:
        return [
            {
                "label":   "Logdatei öffnen (MailLogger)",
                "handler": self._open_log,
            }
        ]

    def _open_log(self, mail_id=None):
        import subprocess, sys
        if os.path.exists(self._log_path):
            if sys.platform == "win32":
                os.startfile(self._log_path)
            else:
                subprocess.Popen(["xdg-open", self._log_path])

    def _log(self, message: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except OSError:
            pass
