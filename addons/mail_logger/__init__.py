"""
Addon: MailLogger  v3.0
Protokolliert Mail-Events in eine Logdatei.

Einstellungen (via get_settings_panel):
  - Logpfad
  - Nur ungelesene oder alle Mails loggen
  - Log-Rotation (max. Dateigröße, Backups)
"""

import os, sys, subprocess
from datetime import datetime
import wx
from core.addon_manager import AddonBase
from core.i18n import tr


class Addon(AddonBase):

    NAME    = "MailLogger"
    VERSION = "3.0.0"

    MAX_LOG_BYTES = 2 * 1024 * 1024
    MAX_BACKUPS   = 3

    @property
    def DESCRIPTION(self):
        return tr("ml_description")

    def __init__(self, controller):
        super().__init__(controller)
        self._log_path = self._resolve_log_path()

    # ------------------------------------------------------------------ #
    #  Einstellungen                                                      #
    # ------------------------------------------------------------------ #

    def _resolve_log_path(self) -> str:
        try:
            p = self.controller.get_setting(
                "ml_log_path",
                os.path.join(os.path.expanduser("~"), ".mailclient", "mail_events.log"))
            return p if p else os.path.join(os.path.expanduser("~"), ".mailclient", "mail_events.log")
        except Exception:
            return os.path.join(os.path.expanduser("~"), ".mailclient", "mail_events.log")

    def _log_all_mails(self) -> bool:
        """True = alle Mails loggen; False = nur ungelesene."""
        return self.controller.get_setting("ml_log_all_mails", "0") == "1"

    def get_settings_panel(self, parent) -> wx.Panel:
        return MailLoggerSettingsPanel(parent, self.controller)

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def on_load(self):
        self._log_path = self._resolve_log_path()
        self._log("SYSTEM", tr("ml_log_loaded"))

    def on_unload(self):
        self._log("SYSTEM", tr("ml_log_unloaded"))

    # ------------------------------------------------------------------ #
    #  Events                                                             #
    # ------------------------------------------------------------------ #

    def on_mail_read(self, data: dict):
        already_was_read = data.get("was_read", False)
        if not self._log_all_mails() and already_was_read:
            return  # Nur ungelesene: bereits gelesene Mail überspringen

        mail_id     = data.get("mail_id", "?")
        subject     = str(data.get("subject") or "").strip() or tr("ml_no_subject")
        sender_name = str(data.get("sender_name") or "").strip()
        sender      = str(data.get("sender") or "").strip()
        date        = str(data.get("date") or "").strip()
        from_str    = f"{sender_name} <{sender}>" if sender_name and sender else (sender_name or sender or "?")
        self._log("READ",
            f"ID={mail_id} | {tr('ml_from')}: {from_str} | "
            f"{tr('ml_subject')}: {subject} | {tr('ml_date')}: {date}")

    def on_mail_deleted(self, data: dict):
        mail_id = data.get("mail_id", "?")
        subject = str(data.get("subject") or "").strip()
        sender  = str(data.get("sender")  or "").strip()
        if not subject or not sender:
            extra = self._load_mail_data(mail_id, data.get("folder_id"))
            if not subject: subject = extra.get("subject", "")
            if not sender:  sender  = extra.get("sender", "")
        self._log("DELETE",
            f"ID={mail_id} | {tr('ml_from')}: {sender} | "
            f"{tr('ml_subject')}: {subject or tr('ml_no_subject')}")

    def on_mail_moved(self, data: dict):
        mail_id   = data.get("mail_id", "?")
        folder_id = data.get("folder_id", "?")
        subject   = str(data.get("subject") or "").strip()
        sender    = str(data.get("sender")  or "").strip()
        if not subject or not sender:
            extra = self._load_mail_data(mail_id, data.get("folder_id"))
            if not subject: subject = extra.get("subject", "")
            if not sender:  sender  = extra.get("sender", "")
        self._log("MOVE",
            f"ID={mail_id} → Ordner={folder_id} | "
            f"{tr('ml_from')}: {sender} | "
            f"{tr('ml_subject')}: {subject or tr('ml_no_subject')}")

    def on_mail_received(self, data: dict):
        count   = data.get("count", 0)
        account = data.get("account_name", "?")
        self._log("INBOX",
            f"{tr('ml_new_mails', count=count)} | {tr('ml_account')}: {account}")

    # ------------------------------------------------------------------ #
    #  Menüeintrag                                                        #
    # ------------------------------------------------------------------ #

    def get_menu_items(self) -> list:
        return [{"label": tr("ml_menu_open_log"), "handler": self._open_log}]

    def _open_log(self, mail_id=None):
        self._log_path = self._resolve_log_path()
        if not os.path.exists(self._log_path):
            wx.MessageBox(tr("ml_log_not_found", path=self._log_path),
                          tr("ml_menu_open_log"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            if sys.platform == "win32":   os.startfile(self._log_path)
            elif sys.platform == "darwin": subprocess.Popen(["open", self._log_path])
            else:                          subprocess.Popen(["xdg-open", self._log_path])
        except Exception as e:
            wx.MessageBox(str(e), tr("error_title"), wx.OK | wx.ICON_ERROR)

    # ------------------------------------------------------------------ #
    #  Interne Hilfsmethoden                                             #
    # ------------------------------------------------------------------ #

    def _load_mail_data(self, mail_id, folder_id=None) -> dict:
        try:
            mail = self.controller.db.get_mail(mail_id, folder_id)
            return dict(mail) if mail else {}
        except Exception:
            return {}

    def _log(self, event_type: str, message: str):
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{event_type:<8}] {message}\n"
        try:
            log_dir = os.path.dirname(self._log_path)
            if log_dir: os.makedirs(log_dir, exist_ok=True)
            if (os.path.exists(self._log_path) and
                    os.path.getsize(self._log_path) >= self.MAX_LOG_BYTES):
                self._rotate()
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def _rotate(self):
        try:
            oldest = f"{self._log_path}.{self.MAX_BACKUPS}"
            if os.path.exists(oldest): os.remove(oldest)
            for i in range(self.MAX_BACKUPS - 1, 0, -1):
                src = f"{self._log_path}.{i}"
                dst = f"{self._log_path}.{i + 1}"
                if os.path.exists(src): os.rename(src, dst)
            os.rename(self._log_path, f"{self._log_path}.1")
        except OSError:
            pass


# ------------------------------------------------------------------ #
#  Einstellungs-Panel                                                 #
# ------------------------------------------------------------------ #

class MailLoggerSettingsPanel(wx.Panel):
    """Einstellungs-Panel für MailLogger (wird im AddonSettingsDialog angezeigt)."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self._ctrl = controller
        self._build()
        self._load()

    def _build(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Logpfad
        row_path = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label=tr("ml_settings_path"))
        self.txt_path = wx.TextCtrl(self)
        self.txt_path.SetName(tr("ml_settings_path"))
        btn_browse = wx.Button(self, label=tr("settings_sound_wav_browse"))
        row_path.Add(lbl,            0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_path.Add(self.txt_path,  1, wx.EXPAND | wx.RIGHT, 4)
        row_path.Add(btn_browse,     0)
        sizer.Add(row_path, 0, wx.EXPAND | wx.ALL, 8)

        # Log-Modus
        self.chk_log_all = wx.CheckBox(self, label=tr("ml_settings_log_all"))
        self.chk_log_all.SetName(tr("ml_settings_log_all"))
        sizer.Add(self.chk_log_all, 0, wx.LEFT | wx.BOTTOM, 8)

        lbl_hint = wx.StaticText(self, label=tr("ml_settings_log_hint"))
        lbl_hint.SetForegroundColour(wx.Colour(100, 100, 100))
        sizer.Add(lbl_hint, 0, wx.LEFT | wx.BOTTOM, 8)

        self.SetSizer(sizer)
        btn_browse.Bind(wx.EVT_BUTTON, self._on_browse)

    def _load(self):
        default_path = os.path.join(os.path.expanduser("~"), ".mailclient", "mail_events.log")
        self.txt_path.SetValue(self._ctrl.get_setting("ml_log_path", default_path))
        self.chk_log_all.SetValue(self._ctrl.get_setting("ml_log_all_mails", "0") == "1")

    def save(self):
        self._ctrl.set_setting("ml_log_path",      self.txt_path.GetValue().strip())
        self._ctrl.set_setting("ml_log_all_mails", "1" if self.chk_log_all.GetValue() else "0")

    def _on_browse(self, event):
        with wx.FileDialog(self, tr("ml_settings_path"),
                           wildcard="Log-Dateien (*.log)|*.log|Alle Dateien (*.*)|*.*",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as d:
            if d.ShowModal() == wx.ID_OK:
                self.txt_path.SetValue(d.GetPath())
