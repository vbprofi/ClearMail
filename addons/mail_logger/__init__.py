"""
Addon: MailLogger
Protokolliert alle Mail-Events in eine Logdatei.

Sprachdateien: locale/de/messages.json, locale/en/messages.json
"""

import os
import subprocess
import sys
from datetime import datetime
from core.addon_manager import AddonBase
from core.i18n import tr


class Addon(AddonBase):

    NAME    = "MailLogger"
    VERSION = "1.1.0"

    # DESCRIPTION wird aus Sprachdatei geladen (nach on_load)
    @property
    def DESCRIPTION(self):
        return tr("ml_description")

    def __init__(self, controller):
        super().__init__(controller)
        self._log_path = os.path.join(
            os.path.expanduser("~"), ".mailclient", "mail_events.log"
        )

    def on_load(self):
        self._log(tr("ml_log_loaded"))

    def on_unload(self):
        self._log(tr("ml_log_unloaded"))

    def on_mail_read(self, data: dict):
        self._log(tr("ml_log_mail_read", mail_id=data.get("mail_id", "?")))

    def on_mail_deleted(self, data: dict):
        self._log(tr("ml_log_mail_deleted", mail_id=data.get("mail_id", "?")))

    def on_mail_moved(self, data: dict):
        self._log(tr("ml_log_mail_moved",
                     mail_id=data.get("mail_id", "?"),
                     folder_id=data.get("folder_id", "?")))

    def get_menu_items(self) -> list:
        return [{
            "label":   tr("ml_menu_open_log"),
            "handler": self._open_log,
        }]

    def _open_log(self, mail_id=None):
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
