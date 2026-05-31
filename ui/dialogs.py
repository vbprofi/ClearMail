"""
Dialoge – i18n, Storage-Tab, Auto-Neustart nach Speichern.
"""

import wx, wx.adv, os, sys, zipfile, shutil, subprocess
from core.i18n import tr, get_available_languages, current_language


def add_labeled_field(parent, sizer, label_text, ctrl_factory, name=None):
    lbl  = wx.StaticText(parent, label=label_text)
    ctrl = ctrl_factory(parent)
    ctrl.SetName(name or label_text.rstrip(":").strip())
    sizer.Add(lbl,  0, wx.ALIGN_CENTER_VERTICAL)
    sizer.Add(ctrl, 1, wx.EXPAND)
    return ctrl


def _restart_app():
    """Startet die Anwendung neu."""
    python = sys.executable
    script = os.path.abspath(sys.argv[0])
    subprocess.Popen([python, script])
    wx.GetApp().GetTopWindow().Close()


# ================================================================== #
#  AccountDialog                                                      #
# ================================================================== #

class AccountDialog(wx.Dialog):
    PROTOCOLS = ["IMAP", "POP3"]

    def __init__(self, parent, controller, account_id=None):
        title = tr("account_title_edit") if account_id else tr("account_title_new")
        super().__init__(parent, title=title, size=(500, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self.account_id = account_id
        self._build_ui()
        if account_id:
            self._load_account(account_id)
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)
        nb    = wx.Notebook(panel)

        pg1 = wx.Panel(nb)
        gs1 = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs1.AddGrowableCol(1)
        self.txt_name  = add_labeled_field(pg1, gs1, tr("account_display_name"), lambda p: wx.TextCtrl(p))
        self.txt_email = add_labeled_field(pg1, gs1, tr("account_email"),        lambda p: wx.TextCtrl(p))
        self.cho_proto = add_labeled_field(pg1, gs1, tr("account_protocol"),
                                           lambda p: wx.Choice(p, choices=self.PROTOCOLS))
        self.cho_proto.SetSelection(0)
        pg1.SetSizer(self._w(gs1));  nb.AddPage(pg1, tr("account_tab_general"))

        pg2 = wx.Panel(nb)
        gs2 = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs2.AddGrowableCol(1)
        self.txt_in_host = add_labeled_field(pg2, gs2, tr("account_server_in"), lambda p: wx.TextCtrl(p))
        self.txt_in_port = add_labeled_field(pg2, gs2, tr("account_port"),
                                              lambda p: wx.SpinCtrl(p, min=1, max=65535, initial=993))
        gs2.Add(wx.StaticText(pg2, label=""), 0)
        self.chk_in_ssl = wx.CheckBox(pg2, label=tr("account_ssl"))
        self.chk_in_ssl.SetValue(True);  gs2.Add(self.chk_in_ssl, 0)
        self.txt_user = add_labeled_field(pg2, gs2, tr("account_username"), lambda p: wx.TextCtrl(p))
        self.txt_pass = add_labeled_field(pg2, gs2, tr("account_password"),
                                           lambda p: wx.TextCtrl(p, style=wx.TE_PASSWORD))
        pg2.SetSizer(self._w(gs2));  nb.AddPage(pg2, tr("account_tab_incoming"))

        pg3 = wx.Panel(nb)
        gs3 = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs3.AddGrowableCol(1)
        self.txt_out_host = add_labeled_field(pg3, gs3, tr("account_server_out"), lambda p: wx.TextCtrl(p))
        self.txt_out_port = add_labeled_field(pg3, gs3, tr("account_port"),
                                               lambda p: wx.SpinCtrl(p, min=1, max=65535, initial=587))
        gs3.Add(wx.StaticText(pg3, label=""), 0)
        self.chk_out_ssl = wx.CheckBox(pg3, label=tr("account_ssl"))
        self.chk_out_ssl.SetValue(True);  gs3.Add(self.chk_out_ssl, 0)
        pg3.SetSizer(self._w(gs3));  nb.AddPage(pg3, tr("account_tab_outgoing"))

        outer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)
        bs = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, tr("account_save"))
        btn_cancel  = wx.Button(panel, wx.ID_CANCEL, tr("dlg_cancel"))
        self.btn_ok.SetDefault()
        bs.AddButton(self.btn_ok);  bs.AddButton(btn_cancel);  bs.Realize()
        outer.Add(bs, 0, wx.EXPAND | wx.ALL, 6)
        panel.SetSizer(outer)
        self.btn_ok.Bind(wx.EVT_BUTTON, self._on_save)
        self.cho_proto.Bind(wx.EVT_CHOICE, self._on_proto_changed)
        self.txt_name.SetFocus()

    @staticmethod
    def _w(grid):
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(grid, 1, wx.EXPAND | wx.ALL, 12)
        return s

    def _on_proto_changed(self, event):
        """
        Setzt den Eingangs-Port automatisch wenn das Protokoll wechselt:
          IMAP → 993 (SSL) / 143 (plain)
          POP3 → 995 (SSL) / 110 (plain)
        Ändert den Port nur wenn er noch einem bekannten Standard entspricht.
        """
        proto    = self.PROTOCOLS[self.cho_proto.GetSelection()]
        ssl_on   = self.chk_in_ssl.GetValue()
        cur_port = self.txt_in_port.GetValue()
        DEFAULTS = {
            ("IMAP", True):  993,
            ("IMAP", False): 143,
            ("POP3", True):  995,
            ("POP3", False): 110,
        }
        if cur_port in set(DEFAULTS.values()):
            self.txt_in_port.SetValue(DEFAULTS[(proto, ssl_on)])
        event.Skip()

    def _load_account(self, aid):
        acc = self.controller.get_account(aid)
        if not acc: return
        self.txt_name.SetValue(str(acc["name"] or ""))
        self.txt_email.SetValue(str(acc["email"] or ""))
        idx = self.PROTOCOLS.index(acc["protocol"]) if acc["protocol"] in self.PROTOCOLS else 0
        self.cho_proto.SetSelection(idx)
        self.txt_in_host.SetValue(str(acc["in_host"] or ""))
        self.txt_in_port.SetValue(acc["in_port"] or 993)
        self.chk_in_ssl.SetValue(bool(acc["in_ssl"]))
        self.txt_out_host.SetValue(str(acc["out_host"] or ""))
        self.txt_out_port.SetValue(acc["out_port"] or 587)
        self.chk_out_ssl.SetValue(bool(acc["out_ssl"]))
        self.txt_user.SetValue(str(acc["username"] or ""))
        self.txt_pass.SetValue(str(acc["password"] or ""))

    def _on_save(self, event):
        data = {
            "id": self.account_id,
            "name":     self.txt_name.GetValue().strip(),
            "email":    self.txt_email.GetValue().strip(),
            "protocol": self.PROTOCOLS[self.cho_proto.GetSelection()],
            "in_host":  self.txt_in_host.GetValue().strip(),
            "in_port":  self.txt_in_port.GetValue(),
            "in_ssl":   1 if self.chk_in_ssl.GetValue() else 0,
            "out_host": self.txt_out_host.GetValue().strip(),
            "out_port": self.txt_out_port.GetValue(),
            "out_ssl":  1 if self.chk_out_ssl.GetValue() else 0,
            "username": self.txt_user.GetValue().strip(),
            "password": self.txt_pass.GetValue(),
        }
        if not data["name"] or not data["email"]:
            wx.MessageBox(tr("account_err_required"), tr("error_title"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        self.controller.save_account(data)
        self.EndModal(wx.ID_OK)


# ================================================================== #
#  SettingsDialog                                                     #
# ================================================================== #

# Storage-Mode-Codes (müssen mit db_manager übereinstimmen)
STORAGE_SQLITE_ONE         = "sqlite_one"
STORAGE_SQLITE_PER_ACCOUNT = "sqlite_per_account"
STORAGE_FILES              = "files"
STORAGE_MBOX               = "mbox"


class SettingsDialog(wx.Dialog):

    def __init__(self, parent, controller):
        super().__init__(parent, title=tr("settings_title"), size=(500, 480),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._load()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)
        nb    = wx.Notebook(panel)

        # ---- General ----
        pg1 = wx.Panel(nb)
        gs1 = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs1.AddGrowableCol(1)
        gs1.Add(wx.StaticText(pg1, label=""), 0)
        self.chk_auto = wx.CheckBox(pg1, label=tr("settings_auto_fetch"))
        self.chk_auto.SetName(tr("settings_auto_fetch"))
        gs1.Add(self.chk_auto, 0)
        self.spn_interval = add_labeled_field(
            pg1, gs1, tr("settings_interval"),
            lambda p: wx.SpinCtrl(p, min=1, max=60, initial=10))
        gs1.Add(wx.StaticText(pg1, label=""), 0)
        self.chk_html = wx.CheckBox(pg1, label=tr("settings_html"))
        self.chk_html.SetName(tr("settings_html"))
        gs1.Add(self.chk_html, 0)
        langs = get_available_languages()
        self._lang_codes  = [c for c, _ in langs]
        self._lang_labels = [n for _, n in langs]
        self.cho_lang = add_labeled_field(
            pg1, gs1, tr("settings_language"),
            lambda p: wx.Choice(p, choices=self._lang_labels),
            name=tr("settings_language"))
        self.spn_mark_read = add_labeled_field(
            pg1, gs1, tr("settings_mark_unread_after"),
            lambda p: wx.SpinCtrl(p, min=0, max=120, initial=0),
            name=tr("settings_mark_unread_after"))

        # ---- Benachrichtigungston ----
        # Trennlinie + Abschnittstitel
        gs1.Add(wx.StaticLine(pg1), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 6)
        gs1.Add(wx.StaticLine(pg1), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 6)
        lbl_section = wx.StaticText(pg1, label=tr("settings_sound_section"))
        lbl_section.SetFont(lbl_section.GetFont().Bold())
        gs1.Add(wx.StaticText(pg1, label=""), 0)
        gs1.Add(lbl_section, 0)

        # Modus-Auswahl
        self._sound_modes  = ["none", "system", "beep", "wav"]
        self._sound_labels = [
            tr("settings_sound_none"),
            tr("settings_sound_system"),
            tr("settings_sound_beep"),
            tr("settings_sound_wav"),
        ]
        self.cho_sound = add_labeled_field(
            pg1, gs1, tr("settings_sound_mode"),
            lambda p: wx.Choice(p, choices=self._sound_labels),
            name=tr("settings_sound_mode"))
        self.cho_sound.SetSelection(0)

        # WAV-Pfad-Zeile
        lbl_wav = wx.StaticText(pg1, label=tr("settings_sound_wav_path"))
        gs1.Add(lbl_wav, 0, wx.ALIGN_CENTER_VERTICAL)
        wav_row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_sound_wav = wx.TextCtrl(pg1)
        self.txt_sound_wav.SetName(tr("settings_sound_wav_path"))
        btn_wav_browse = wx.Button(pg1, label=tr("settings_sound_wav_browse"))
        btn_wav_browse.SetName(tr("settings_sound_wav_browse"))
        wav_row.Add(self.txt_sound_wav, 1, wx.EXPAND | wx.RIGHT, 4)
        wav_row.Add(btn_wav_browse, 0)
        gs1.Add(wav_row, 1, wx.EXPAND)

        # Frequenz + Länge (Beep)
        self.spn_sound_freq = add_labeled_field(
            pg1, gs1, tr("settings_sound_beep_freq"),
            lambda p: wx.SpinCtrl(p, min=37, max=32767, initial=880),
            name=tr("settings_sound_beep_freq"))
        self.spn_sound_dur = add_labeled_field(
            pg1, gs1, tr("settings_sound_beep_dur"),
            lambda p: wx.SpinCtrl(p, min=10, max=5000, initial=200),
            name=tr("settings_sound_beep_dur"))

        # Test-Button
        gs1.Add(wx.StaticText(pg1, label=""), 0)
        btn_sound_test = wx.Button(pg1, label=tr("settings_sound_test"))
        btn_sound_test.SetName(tr("settings_sound_test"))
        gs1.Add(btn_sound_test, 0)

        pg1.SetSizer(self._w(gs1))
        nb.AddPage(pg1, tr("settings_tab_general"))

        # Events für Sound-Sektion
        self.cho_sound.Bind(wx.EVT_CHOICE,  self._on_sound_mode_changed)
        btn_wav_browse.Bind(wx.EVT_BUTTON,  self._on_browse_wav)
        btn_sound_test.Bind(wx.EVT_BUTTON,  self._on_test_sound)
        self._on_sound_mode_changed(None)   # initiale Sichtbarkeit

        # ---- Display ----
        pg2 = wx.Panel(nb)
        gs2 = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs2.AddGrowableCol(1)
        self.spn_font = add_labeled_field(
            pg2, gs2, tr("settings_font_size"),
            lambda p: wx.SpinCtrl(p, min=8, max=24, initial=10))
        pg2.SetSizer(self._w(gs2))
        nb.AddPage(pg2, tr("settings_tab_display"))

        # ---- Delete ----
        pg3 = wx.Panel(nb)
        gs3 = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs3.AddGrowableCol(1)
        gs3.Add(wx.StaticText(pg3, label=""), 0)
        self.chk_confirm_del = wx.CheckBox(pg3, label=tr("settings_confirm_delete"))
        self.chk_confirm_del.SetName(tr("settings_confirm_delete"))
        gs3.Add(self.chk_confirm_del, 0)
        lbl_mode = wx.StaticText(pg3, label=tr("settings_delete_mode"))
        gs3.Add(lbl_mode, 0, wx.ALIGN_CENTER_VERTICAL)
        mode_panel = wx.Panel(pg3)
        mode_sizer = wx.BoxSizer(wx.VERTICAL)
        self.rb_trash  = wx.RadioButton(mode_panel, label=tr("settings_delete_trash"), style=wx.RB_GROUP)
        self.rb_direct = wx.RadioButton(mode_panel, label=tr("settings_delete_direct"))
        self.rb_trash.SetName(tr("settings_delete_trash"))
        self.rb_direct.SetName(tr("settings_delete_direct"))
        mode_sizer.Add(self.rb_trash, 0, wx.BOTTOM, 4)
        mode_sizer.Add(self.rb_direct, 0)
        mode_panel.SetSizer(mode_sizer)
        gs3.Add(mode_panel, 1, wx.EXPAND)
        pg3.SetSizer(self._w(gs3))
        nb.AddPage(pg3, tr("settings_tab_delete"))

        # ---- Storage ----
        pg4 = wx.Panel(nb)
        gs4 = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs4.AddGrowableCol(1)

        # Label zuerst, dann Choice (HWND-Reihenfolge für Screenreader)
        lbl_storage = wx.StaticText(pg4, label=tr("settings_storage_mode"))
        self._storage_codes  = [STORAGE_SQLITE_ONE, STORAGE_SQLITE_PER_ACCOUNT, STORAGE_FILES, STORAGE_MBOX]
        self._storage_labels = [
            tr("settings_storage_sqlite_one"),
            tr("settings_storage_sqlite_per_account"),
            tr("settings_storage_files"),
            tr("settings_storage_mbox"),
        ]
        self.cho_storage = wx.Choice(pg4, choices=self._storage_labels)
        self.cho_storage.SetName(tr("settings_storage_mode"))
        gs4.Add(lbl_storage, 0, wx.ALIGN_CENTER_VERTICAL)
        gs4.Add(self.cho_storage, 1, wx.EXPAND)

        pg4.SetSizer(self._w(gs4))
        nb.AddPage(pg4, tr("settings_tab_storage"))

        # ---- Developer ----
        import os as _os
        pg5 = wx.Panel(nb)
        gs5 = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs5.AddGrowableCol(1)
        gs5.Add(wx.StaticText(pg5, label=""), 0)
        self.chk_dev_log = wx.CheckBox(pg5, label=tr("settings_dev_logging"))
        self.chk_dev_log.SetName(tr("settings_dev_logging"))
        gs5.Add(self.chk_dev_log, 0)

        lbl_log_path = wx.StaticText(pg5, label=tr("settings_dev_log_path"))
        gs5.Add(lbl_log_path, 0, wx.ALIGN_CENTER_VERTICAL)
        data_dir = _os.path.join(_os.path.expanduser("~"), ".mailclient")
        self.txt_log_path = wx.TextCtrl(pg5)
        self.txt_log_path.SetValue(_os.path.join(data_dir, "protocol.log"))
        self.txt_log_path.SetName(tr("settings_dev_log_path"))
        gs5.Add(self.txt_log_path, 1, wx.EXPAND)

        gs5.Add(wx.StaticText(pg5, label=""), 0)
        btn_row5 = wx.BoxSizer(wx.HORIZONTAL)
        btn_open_log  = wx.Button(pg5, label=tr("settings_dev_open_log"))
        btn_clear_log = wx.Button(pg5, label=tr("settings_dev_clear_log"))
        btn_open_log.Bind(wx.EVT_BUTTON, self._on_open_log)
        btn_clear_log.Bind(wx.EVT_BUTTON, self._on_clear_log)
        btn_row5.Add(btn_open_log, 0, wx.RIGHT, 6)
        btn_row5.Add(btn_clear_log)
        gs5.Add(btn_row5, 0)

        pg5.SetSizer(self._w(gs5))
        nb.AddPage(pg5, tr("settings_tab_developer"))

        outer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)
        bs = wx.StdDialogButtonSizer()
        btn_ok     = wx.Button(panel, wx.ID_OK,     tr("dlg_save"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, tr("dlg_cancel"))
        btn_ok.SetDefault()
        bs.AddButton(btn_ok);  bs.AddButton(btn_cancel);  bs.Realize()
        outer.Add(bs, 0, wx.EXPAND | wx.ALL, 6)
        panel.SetSizer(outer)
        btn_ok.Bind(wx.EVT_BUTTON, self._on_save)

    @staticmethod
    def _w(grid):
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(grid, 1, wx.EXPAND | wx.ALL, 12)
        return s

    def _on_sound_mode_changed(self, event):
        """Zeigt/versteckt WAV- und Beep-Felder je nach Modus."""
        idx  = self.cho_sound.GetSelection()
        mode = self._sound_modes[idx] if 0 <= idx < len(self._sound_modes) else "none"
        is_wav  = mode == "wav"
        is_beep = mode == "beep"
        self.txt_sound_wav.Enable(is_wav)
        # btn_wav_browse ist Geschwister-Widget – über Parent finden
        for child in self.txt_sound_wav.GetParent().GetChildren():
            if hasattr(child, "GetLabel") and child.GetLabel() == tr("settings_sound_wav_browse"):
                child.Enable(is_wav)
                break
        self.spn_sound_freq.Enable(is_beep)
        self.spn_sound_dur.Enable(is_beep)
        if event:
            event.Skip()

    def _on_browse_wav(self, event):
        with wx.FileDialog(
            self, tr("settings_sound_wav_path"),
            wildcard=tr("settings_sound_wav_filter"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.txt_sound_wav.SetValue(dlg.GetPath())

    def _on_test_sound(self, event):
        from core.sound_notify import test_sound
        idx  = self.cho_sound.GetSelection()
        mode = self._sound_modes[idx] if 0 <= idx < len(self._sound_modes) else "none"
        test_sound(
            mode=mode,
            wav_path=self.txt_sound_wav.GetValue().strip(),
            freq=self.spn_sound_freq.GetValue(),
            duration_ms=self.spn_sound_dur.GetValue(),
        )

    def _on_open_log(self, event):
        import os, sys, subprocess
        path = self.txt_log_path.GetValue().strip()
        if not os.path.exists(path):
            open(path, "w").close()
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def _on_clear_log(self, event):
        path = self.txt_log_path.GetValue().strip()
        try:
            open(path, "w").close()
            wx.MessageBox(tr("settings_dev_clear_log") + " OK",
                          tr("hint_title"), wx.OK, self)
        except Exception as e:
            wx.MessageBox(str(e), tr("error_title"), wx.OK | wx.ICON_ERROR, self)

    def _load(self):
        g = self.controller.get_setting
        self.chk_auto.SetValue(g("auto_fetch",      "0") == "1")
        self.spn_mark_read.SetValue(int(g("mark_read_after", "0")))
        self.spn_interval.SetValue(int(g("fetch_interval", "10")))
        self.chk_html.SetValue(g("render_html",     "0") == "1")
        self.chk_confirm_del.SetValue(g("confirm_delete", "1") == "1")
        self.spn_font.SetValue(int(g("font_size",   "10")))
        trash = g("delete_to_trash", "1") == "1"
        self.rb_trash.SetValue(trash)
        self.rb_direct.SetValue(not trash)
        cur_lang = g("language", "de")
        idx_lang = self._lang_codes.index(cur_lang) if cur_lang in self._lang_codes else 0
        self.cho_lang.SetSelection(idx_lang)
        cur_storage = g("mail_storage", STORAGE_SQLITE_ONE)
        idx_st = self._storage_codes.index(cur_storage) if cur_storage in self._storage_codes else 0
        self.cho_storage.SetSelection(idx_st)
        self.chk_dev_log.SetValue(g("dev_logging", "0") == "1")
        import os as _os2
        log_p = g("dev_log_path", _os2.path.join(_os2.path.expanduser("~"), ".mailclient", "protocol.log"))
        self.txt_log_path.SetValue(log_p)

        # Sound
        cur_mode = g("sound_mode", "none")
        idx_snd  = self._sound_modes.index(cur_mode) if cur_mode in self._sound_modes else 0
        self.cho_sound.SetSelection(idx_snd)
        self.txt_sound_wav.SetValue(g("sound_wav_path", ""))
        self.spn_sound_freq.SetValue(int(g("sound_beep_freq",   "880")))
        self.spn_sound_dur.SetValue(int(g("sound_beep_dur_ms",  "200")))
        self._on_sound_mode_changed(None)

    def _on_save(self, event):
        s   = self.controller.set_setting
        g   = self.controller.get_setting
        s("auto_fetch",     "1" if self.chk_auto.GetValue() else "0")
        s("mark_read_after", str(self.spn_mark_read.GetValue()))
        s("fetch_interval", str(self.spn_interval.GetValue()))
        s("render_html",    "1" if self.chk_html.GetValue() else "0")
        s("confirm_delete", "1" if self.chk_confirm_del.GetValue() else "0")
        s("font_size",      str(self.spn_font.GetValue()))
        s("delete_to_trash","1" if self.rb_trash.GetValue() else "0")

        # Sprache
        idx_lang = self.cho_lang.GetSelection()
        if 0 <= idx_lang < len(self._lang_codes):
            s("language", self._lang_codes[idx_lang])

        # Developer
        dev_log = self.chk_dev_log.GetValue()
        s("dev_logging",  "1" if dev_log else "0")
        s("dev_log_path", self.txt_log_path.GetValue().strip())
        from core.protocol_runner import setup_logging, disable_logging
        if dev_log:
            setup_logging(self.txt_log_path.GetValue().strip())
        else:
            disable_logging()

        # Sound
        idx_snd = self.cho_sound.GetSelection()
        s("sound_mode",       self._sound_modes[idx_snd] if 0 <= idx_snd < len(self._sound_modes) else "none")
        s("sound_wav_path",   self.txt_sound_wav.GetValue().strip())
        s("sound_beep_freq",  str(self.spn_sound_freq.GetValue()))
        s("sound_beep_dur_ms", str(self.spn_sound_dur.GetValue()))

        # Storage-Modus prüfen
        idx_st   = self.cho_storage.GetSelection()
        new_mode = self._storage_codes[idx_st] if 0 <= idx_st < len(self._storage_codes) else STORAGE_SQLITE_ONE
        old_mode = g("mail_storage", STORAGE_SQLITE_ONE)

        self.EndModal(wx.ID_OK)

        if new_mode != old_mode:
            # Migration mit Fortschrittsfenster (importiert hier um Zirkelbezüge zu vermeiden)
            from ui.migration_dialog import MigrationDialog
            dlg = MigrationDialog(None, self.controller, new_mode)
            dlg.ShowModal()
            dlg.Destroy()
            # Neustart erfolgt im MigrationDialog – hier nichts mehr tun
        else:
            # Kein Moduswechsel: einfacher Neustart
            wx.MessageBox(tr("settings_restart_now"), tr("settings_restart_title"),
                          wx.OK | wx.ICON_INFORMATION)
            _restart_app()


# ================================================================== #
#  PrintPreviewDialog                                                 #
# ================================================================== #

class PrintPreviewDialog(wx.Dialog):

    def __init__(self, parent, mail: dict):
        super().__init__(parent, title=tr("print_title"), size=(620, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.mail = mail
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl   = wx.StaticText(panel, label=tr("print_title"))
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 8)
        txt = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN)
        txt.SetName(tr("print_title"))
        s   = self.mail
        txt.SetValue(
            f"{tr('preview_from')}   {s.get('sender_name','') or ''} <{s.get('sender','') or ''}>\n"
            f"{tr('preview_to')}     {s.get('recipients','') or ''}\n"
            f"{tr('preview_subject')} {s.get('subject','') or ''}\n"
            f"{tr('preview_date')}   {s.get('date','') or ''}\n"
            f"\n{'─'*60}\n\n{s.get('body_text','') or ''}"
        )
        sizer.Add(txt, 1, wx.EXPAND | wx.ALL, 8)
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_print = wx.Button(panel, label=tr("print_btn"))
        btn_close = wx.Button(panel, wx.ID_CLOSE, tr("dlg_close"))
        btn_print.Bind(wx.EVT_BUTTON, lambda e: wx.MessageBox(
            tr("print_todo"), tr("print_title"), wx.OK | wx.ICON_INFORMATION, self))
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        btn_row.Add(btn_print, 0, wx.RIGHT, 8);  btn_row.Add(btn_close)
        sizer.Add(btn_row, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        panel.SetSizer(sizer)
        txt.SetFocus()


# ================================================================== #
#  PGPDialog                                                          #
# ================================================================== #

class PGPDialog(wx.Dialog):

    def __init__(self, parent):
        super().__init__(parent, title=tr("pgp_title"), size=(520, 400),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=tr("pgp_title") + "\n\n(Platzhalter)\npython-gnupg"), 0, wx.ALL, 14)
        lst = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        lst.SetName(tr("pgp_title"))
        lst.InsertColumn(0, tr("pgp_col_name"),  width=250)
        lst.InsertColumn(1, tr("pgp_col_id"),    width=130)
        lst.InsertColumn(2, tr("pgp_col_valid"), width=80)
        sizer.Add(lst, 1, wx.EXPAND | wx.ALL, 8)
        row = wx.BoxSizer(wx.HORIZONTAL)
        for lbl in (tr("pgp_import"), tr("pgp_export")):
            b = wx.Button(panel, label=lbl)
            b.Bind(wx.EVT_BUTTON, lambda e: wx.MessageBox(
                tr("pgp_not_impl"), tr("pgp_not_impl_title"), wx.OK, self))
            row.Add(b, 0, wx.RIGHT, 6)
        row.AddStretchSpacer()
        btn_close = wx.Button(panel, wx.ID_CLOSE, tr("dlg_close"))
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        row.Add(btn_close)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)


# ================================================================== #
#  AddonManagerDialog                                                 #
# ================================================================== #

class AddonManagerDialog(wx.Dialog):

    def __init__(self, parent, controller):
        super().__init__(parent, title=tr("addon_title"), size=(600, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._load_addons()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=tr("addon_desc")), 0, wx.ALL, 8)
        self.list_addons = wx.ListCtrl(panel,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_addons.SetName(tr("addon_col_name"))
        self.list_addons.InsertColumn(0, tr("addon_col_name"),    width=160)
        self.list_addons.InsertColumn(1, tr("addon_col_version"), width=65)
        self.list_addons.InsertColumn(2, tr("addon_col_status"),  width=85)
        self.list_addons.InsertColumn(3, tr("addon_col_desc"),    width=240)
        sizer.Add(self.list_addons, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_toggle = wx.Button(panel, label=tr("addon_toggle"))
        btn_install     = wx.Button(panel, label=tr("addon_install"))
        btn_open_dir    = wx.Button(panel, label=tr("addon_open_dir"))
        btn_close       = wx.Button(panel, wx.ID_CLOSE, tr("dlg_close"))
        self.btn_toggle.Bind(wx.EVT_BUTTON, self._on_toggle)
        btn_install.Bind(wx.EVT_BUTTON,     self._on_install)
        btn_open_dir.Bind(wx.EVT_BUTTON,    self._on_open_dir)
        btn_close.Bind(wx.EVT_BUTTON,       lambda e: self.EndModal(wx.ID_CLOSE))
        for b in (self.btn_toggle, btn_install, btn_open_dir):
            row.Add(b, 0, wx.RIGHT, 6)
        row.AddStretchSpacer();  row.Add(btn_close)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(wx.StaticText(panel,
            label=tr("addon_dir_label", path=self.controller.addon_mgr.addon_dir)),
            0, wx.LEFT | wx.BOTTOM, 8)
        panel.SetSizer(sizer)
        self.list_addons.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_toggle)

    def _load_addons(self):
        self.list_addons.DeleteAllItems()
        loaded    = self.controller.addon_mgr.get_loaded_addons()
        available = self.controller.addon_mgr.scan_addon_dir()
        if not available:
            self.list_addons.InsertItem(0, "(–)");  return
        for name in sorted(available):
            addon = loaded.get(name)
            idx   = self.list_addons.InsertItem(self.list_addons.GetItemCount(), name)
            self.list_addons.SetItem(idx, 1, addon.VERSION if addon else "–")
            self.list_addons.SetItem(idx, 2, tr("addon_status_active") if addon else tr("addon_status_inactive"))
            self.list_addons.SetItem(idx, 3, addon.DESCRIPTION if addon else "")
            if addon:
                self.list_addons.SetItemTextColour(idx, wx.Colour(0, 100, 0))

    def _on_toggle(self, event):
        idx = self.list_addons.GetFirstSelected()
        if idx < 0:
            wx.MessageBox(tr("addon_no_select"), tr("hint_title"), wx.OK, self);  return
        name   = self.list_addons.GetItemText(idx, 0)
        status = self.list_addons.GetItemText(idx, 2)
        mgr    = self.controller.addon_mgr
        lang   = self.controller.get_setting("language", "de")
        if status == tr("addon_status_active"):
            mgr.unload_addon(name)
            wx.MessageBox(tr("addon_deactivated", name=name), tr("addon_title"), wx.OK, self)
        else:
            ok = mgr.load_addon(name, self.controller, lang=lang)
            wx.MessageBox(tr("addon_activated", name=name) if ok else tr("addon_load_error", name=name),
                          tr("addon_title"), wx.OK | (wx.ICON_INFORMATION if ok else wx.ICON_ERROR), self)
        self._load_addons()

    def _on_install(self, event):
        with wx.FileDialog(self, tr("addon_install"), wildcard=tr("wildcard_zip"),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as d:
            if d.ShowModal() != wx.ID_OK:  return
            zip_path = d.GetPath()
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
        except zipfile.BadZipFile:
            wx.MessageBox(tr("addon_not_valid_zip"), tr("error_title"), wx.OK | wx.ICON_ERROR, self);  return
        addon_name = None
        for n in names:
            parts = n.replace("\\", "/").split("/")
            if len(parts) == 2 and parts[1] == "__init__.py" and parts[0]:
                addon_name = parts[0];  break
        if not addon_name:
            wx.MessageBox(tr("addon_install_invalid"), tr("error_title"), wx.OK | wx.ICON_WARNING, self);  return
        target = os.path.join(self.controller.addon_mgr.addon_dir, addon_name)
        if os.path.exists(target):
            if wx.MessageBox(tr("addon_install_overwrite", name=addon_name), tr("addon_title"),
                             wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:  return
            shutil.rmtree(target, ignore_errors=True)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(self.controller.addon_mgr.addon_dir)
        except Exception as e:
            wx.MessageBox(tr("addon_install_error", error=str(e)), tr("error_title"), wx.OK | wx.ICON_ERROR, self);  return
        wx.MessageBox(tr("addon_install_ok", name=addon_name), tr("addon_restart_title"), wx.OK, self)
        _restart_app()

    def _on_open_dir(self, event):
        d = self.controller.addon_mgr.addon_dir
        os.makedirs(d, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(d)
        else:
            subprocess.Popen(["xdg-open", d])


# ================================================================== #
#  AboutDialog  – liest Version aus version_info.APP_VERSION          #
# ================================================================== #

class AboutDialog(wx.Dialog):

    def __init__(self, parent):
        super().__init__(parent, title=tr("about_title"), size=(420, 310),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(panel, label=tr("app_title"))
        title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        sizer.Add(title, 0, wx.ALIGN_CENTER | wx.TOP, 20)

        # Version: bevorzugt direkt aus der EXE-VERSIONINFO (win32api oder struct).
        # Fallback: version.txt → Entwicklungsumgebung.
        # version_info.py liegt im App-Root; sys.path wird entsprechend erweitert.
        version = "?"
        try:
            import sys as _sys, os as _os, importlib
            # Mögliche Verzeichnisse für version_info.py
            _dirs = []
            _meipass = getattr(_sys, "_MEIPASS", None)
            if _meipass: _dirs.append(_meipass)
            # ui/ → ../ (App-Root)
            _ui_dir  = _os.path.dirname(_os.path.abspath(__file__))
            _app_dir = _os.path.dirname(_ui_dir)
            for _d in (_app_dir, _ui_dir):
                if _d and _d not in _sys.path:
                    _sys.path.insert(0, _d)
            # Importieren – ggf. neu laden falls bereits gecacht
            if "version_info" in _sys.modules:
                _vi = _sys.modules["version_info"]
            else:
                import version_info as _vi  # type: ignore
            version = _vi.get_version()
        except Exception:
            version = "?"

        info = wx.StaticText(panel,
            label=tr("about_version", version=version) + "\n\n" + tr("about_desc"),
            style=wx.ALIGN_CENTER)
        sizer.Add(info, 1, wx.ALIGN_CENTER | wx.ALL, 16)
        btn = wx.Button(panel, wx.ID_CLOSE, tr("dlg_close"))
        btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        sizer.Add(btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 16)
        panel.SetSizer(sizer)


# ================================================================== #
#  ComposeDialog                                                      #
# ================================================================== #

class ComposeDialog(wx.Dialog):
    """
    Verfassen / Antworten / Weiterleiten.

    v4-Erweiterungen:
      - HTML/Text-Schalter: wx.Notebook Body (Text | HTML)
        Standard: abhängig von Einstellung render_html
      - Anhang-Kontextmenü: Speichern, Entfernen, Hinzufügen
      - Vollständige HTML-Mail-Erstellung via MIMEMultipart/alternative
      - Vorwärts-Anhänge werden korrekt mitgenommen
      - Antwort-HTML-Zitat wenn Quell-Mail HTML hatte
    """

    def __init__(self, parent, controller,
                 reply_to=None, reply_all=False, forward=None):
        title = (tr("compose_title_reply")   if reply_to else
                 tr("compose_title_forward") if forward  else
                 tr("compose_title_new"))
        super().__init__(parent, title=title, size=(720, 660),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller   = controller
        self._attachments = []   # [{name, path, data(bytes|None), mime_type, size}]
        self._accs        = [dict(a) for a in controller.get_accounts()
                             if dict(a).get("protocol", "IMAP") != "LOCAL"]
        # HTML-Modus: Standard aus Einstellungen
        self._html_mode   = controller.get_setting("render_html", "0") == "1"
        self._build_ui()
        self._prefill(reply_to, reply_all, forward)
        self.Centre()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ---- Header ----
        gs = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        gs.AddGrowableCol(1)
        from_choices = [f"{a['name']} <{a['email']}>" for a in self._accs] or ["(–)"]
        self.cho_from    = add_labeled_field(panel, gs, tr("compose_from"),
                                              lambda p: wx.Choice(p, choices=from_choices))
        self.cho_from.SetSelection(0)
        self.txt_to      = add_labeled_field(panel, gs, tr("compose_to"),
                                              lambda p: wx.TextCtrl(p))
        self.txt_cc      = add_labeled_field(panel, gs, tr("compose_cc"),
                                              lambda p: wx.TextCtrl(p))
        self.txt_subject = add_labeled_field(panel, gs, tr("compose_subject"),
                                              lambda p: wx.TextCtrl(p))
        sizer.Add(gs, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ---- HTML/Text-Schalter ----
        row_mode = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_toggle_html = wx.Button(panel, label=self._toggle_label())
        self.btn_toggle_html.SetName(tr("compose_toggle_html"))
        row_mode.Add(self.btn_toggle_html, 0, wx.ALL, 4)
        sizer.Add(row_mode, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        # ---- Body: Notebook (Text | HTML) ----
        self._nb_body = wx.Notebook(panel)

        # Seite 0: Plaintext
        pg_text = wx.Panel(self._nb_body)
        self.txt_body = wx.TextCtrl(
            pg_text, style=wx.TE_MULTILINE | wx.BORDER_SUNKEN)
        self.txt_body.SetName(tr("compose_body"))
        pg_text_s = wx.BoxSizer(wx.VERTICAL)
        pg_text_s.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 4)
        pg_text.SetSizer(pg_text_s)
        self._nb_body.AddPage(pg_text, tr("compose_tab_text"))

        # Seite 1: HTML-Editor (wx.html2.WebView wenn verfügbar, sonst TextCtrl)
        pg_html = wx.Panel(self._nb_body)
        self._html_editor, self._html_backend = self._create_html_editor(pg_html)
        self._html_editor.SetName(tr("compose_tab_html"))
        pg_html_s = wx.BoxSizer(wx.VERTICAL)
        pg_html_s.Add(self._html_editor, 1, wx.EXPAND | wx.ALL, 4)
        pg_html.SetSizer(pg_html_s)
        self._nb_body.AddPage(pg_html, tr("compose_tab_html"))

        # Initial-Seite
        self._nb_body.SetSelection(1 if self._html_mode else 0)
        sizer.Add(self._nb_body, 1, wx.EXPAND | wx.ALL, 8)

        # ---- Anhang-Bereich ----
        self.lbl_attach = wx.StaticText(panel, label=tr("compose_attach_empty"))
        sizer.Add(self.lbl_attach, 0, wx.LEFT | wx.RIGHT, 8)
        self.list_attach = wx.ListCtrl(
            panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_attach.SetName(tr("compose_attach_label"))
        self.list_attach.InsertColumn(0, tr("compose_attach_col_name"), width=300)
        self.list_attach.InsertColumn(1, tr("compose_attach_col_size"), width=80)
        self.list_attach.SetMinSize((-1, 80))
        sizer.Add(self.list_attach, 0, wx.EXPAND | wx.ALL, 8)

        # ---- Buttons ----
        row = wx.BoxSizer(wx.HORIZONTAL)
        btn_send   = wx.Button(panel, label=tr("compose_send"))
        btn_attach = wx.Button(panel, label=tr("compose_attach"))
        btn_disc   = wx.Button(panel, wx.ID_CANCEL, tr("compose_discard"))
        btn_send.SetDefault()
        row.Add(btn_send,   0, wx.RIGHT, 8)
        row.Add(btn_attach, 0, wx.RIGHT, 8)
        row.AddStretchSpacer()
        row.Add(btn_disc)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)

        # ---- Events ----
        btn_send.Bind(wx.EVT_BUTTON,   self._on_send)
        btn_attach.Bind(wx.EVT_BUTTON, self._on_add_attach)
        self.btn_toggle_html.Bind(wx.EVT_BUTTON, self._on_toggle_html)
        self.list_attach.Bind(wx.EVT_CONTEXT_MENU, self._on_attach_ctx)
        self.list_attach.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_attach_open)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

        self.txt_to.SetFocus()

    def _create_html_editor(self, parent):
        """Erstellt HTML-Editor: WebView (editable) wenn verfügbar, sonst TextCtrl."""
        try:
            import wx.html2
            wv = wx.html2.WebView.New(parent)
            # Leeres editierbares Dokument laden
            wv.SetPage(
                '<html><body contenteditable="true" style="font-family:sans-serif;'
                'font-size:10pt;padding:6px;outline:none;"></body></html>', "")
            return wv, "webview"
        except Exception:
            tc = wx.TextCtrl(parent, style=wx.TE_MULTILINE | wx.BORDER_SUNKEN)
            return tc, "textctrl"

    def _toggle_label(self):
        return ("🌐 " + tr("compose_switch_to_html")
                if not self._html_mode
                else "📄 " + tr("compose_switch_to_text"))

    # ------------------------------------------------------------------ #
    #  Daten vorbelegen                                                   #
    # ------------------------------------------------------------------ #

    def _prefill(self, reply_to, reply_all, forward):
        re_prefix  = tr("compose_re_prefix")
        fwd_prefix = tr("compose_fwd_prefix")

        if reply_to:
            self.txt_to.SetValue(str(reply_to.get("sender") or ""))
            if reply_all:
                existing = str(reply_to.get("recipients") or "")
                self.txt_cc.SetValue(existing)
            subj = str(reply_to.get("subject") or "")
            self.txt_subject.SetValue(
                subj if subj.startswith(re_prefix) else re_prefix + subj)
            # Zitat – HTML wenn Quell-Mail HTML hatte und HTML-Modus aktiv
            src_html = str(reply_to.get("body_html") or "")
            src_text = str(reply_to.get("body_text") or "")
            quote_html = (
                f'<br><br><hr style="border:1px solid #ccc">'
                f'<b>{tr("preview_from")}</b> '
                f'{reply_to.get("sender_name","")} &lt;{reply_to.get("sender","")}&gt;<br>'
                f'<blockquote style="border-left:3px solid #888;margin:0 0 0 6px;padding-left:8px;">'
                f'{src_html or src_text.replace(chr(10),"<br>")}</blockquote>'
            )
            quote_text = (
                f'\n\n{"─"*40}\n'
                f'{tr("preview_from")} {reply_to.get("sender_name","")} '
                f'<{reply_to.get("sender","")}>\n'
                + "\n".join(f"> {l}" for l in src_text.splitlines())
            )
            self._set_body_content("", quote_html, quote_text)

        elif forward:
            subj = str(forward.get("subject") or "")
            self.txt_subject.SetValue(
                subj if subj.startswith(fwd_prefix) else fwd_prefix + subj)
            src_html = str(forward.get("body_html") or "")
            src_text = str(forward.get("body_text") or "")
            fwd_html = (
                f'<br><br><hr style="border:1px solid #ccc">'
                f'<b>{"Weitergeleitete Nachricht"}</b><br>'
                f'<b>{tr("preview_from")}</b> '
                f'{forward.get("sender_name","")} &lt;{forward.get("sender","")}&gt;<br>'
                f'<b>{tr("preview_subject")}</b> {forward.get("subject","")}<br><br>'
                f'{src_html or src_text.replace(chr(10),"<br>")}'
            )
            fwd_text = (
                f'\n\n{"─"*40}\n'
                f'{tr("preview_from")} {forward.get("sender_name","")} '
                f'<{forward.get("sender","")}>\n'
                f'{tr("preview_subject")} {forward.get("subject","")}\n\n'
                f'{src_text}'
            )
            self._set_body_content("", fwd_html, fwd_text)
            # Anhänge der Original-Mail mitnehmen
            for att in (forward.get("attachments") or []):
                if att.get("data"):
                    self._attachments.append({
                        "name":      att.get("filename", "attachment"),
                        "path":      None,
                        "data":      bytes(att["data"]),
                        "mime_type": att.get("mime_type", "application/octet-stream"),
                        "size":      att.get("size", 0),
                    })
            self._refresh_attach_list()

    def _set_body_content(self, text_prefix: str, html_content: str, text_content: str):
        """Setzt Inhalt in beiden Body-Editoren."""
        # Plaintext
        self.txt_body.SetValue(text_content)
        self.txt_body.SetInsertionPoint(0)
        # HTML-Editor
        if self._html_backend == "webview":
            import wx
            wx.CallAfter(self._html_editor.SetPage,
                f'<html><body contenteditable="true" style="font-family:sans-serif;'
                f'font-size:10pt;padding:6px;outline:none;">'
                f'{html_content}</body></html>', "")
        else:
            self._html_editor.SetValue(html_content)

    def _get_body_content(self) -> tuple[str, str]:
        """Gibt (body_text, body_html) zurück je nach aktivem Modus."""
        if self._html_mode:
            if self._html_backend == "webview":
                try:
                    html = self._html_editor.GetPageSource()
                except Exception:
                    html = ""
            else:
                html = self._html_editor.GetValue()
            # Aus HTML Plaintext ableiten
            from ui.html_renderer import html_to_text
            text = html_to_text(html)
            return text, html
        else:
            text = self.txt_body.GetValue()
            return text, ""

    # ------------------------------------------------------------------ #
    #  HTML/Text umschalten                                               #
    # ------------------------------------------------------------------ #

    def _on_toggle_html(self, event):
        self._html_mode = not self._html_mode
        self._nb_body.SetSelection(1 if self._html_mode else 0)
        self.btn_toggle_html.SetLabel(self._toggle_label())

    # ------------------------------------------------------------------ #
    #  Anhänge – Kontextmenü                                             #
    # ------------------------------------------------------------------ #

    def _on_attach_ctx(self, event):
        menu = wx.Menu()
        mi_add    = menu.Append(wx.ID_ANY, tr("compose_attach_ctx_add"))
        mi_save   = menu.Append(wx.ID_ANY, tr("compose_attach_ctx_save"))
        mi_remove = menu.Append(wx.ID_ANY, tr("compose_attach_ctx_remove"))
        self.Bind(wx.EVT_MENU, self._on_add_attach,    mi_add)
        self.Bind(wx.EVT_MENU, self._on_save_attach,   mi_save)
        self.Bind(wx.EVT_MENU, self._on_remove_attach, mi_remove)
        idx = self.list_attach.GetFirstSelected()
        mi_save.Enable(idx >= 0)
        mi_remove.Enable(idx >= 0)
        self.list_attach.PopupMenu(menu)
        menu.Destroy()

    def _on_add_attach(self, event=None):
        with wx.FileDialog(self, tr("attach_title"),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as d:
            if d.ShowModal() != wx.ID_OK:
                return
            import os
            for path in d.GetPaths():
                if not any(a.get("path") == path for a in self._attachments):
                    size = os.path.getsize(path) if os.path.exists(path) else 0
                    self._attachments.append({
                        "name":      os.path.basename(path),
                        "path":      path,
                        "data":      None,   # lazy – aus Pfad beim Senden laden
                        "mime_type": "application/octet-stream",
                        "size":      size,
                    })
        self._refresh_attach_list()

    def _on_save_attach(self, event=None):
        idx = self.list_attach.GetFirstSelected()
        if idx < 0 or idx >= len(self._attachments):
            return
        att = self._attachments[idx]
        import os
        with wx.FileDialog(self, tr("attach_title"),
                           defaultFile=att["name"],
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as d:
            if d.ShowModal() != wx.ID_OK:
                return
            data = att.get("data")
            if data is None and att.get("path") and os.path.exists(att["path"]):
                with open(att["path"], "rb") as f:
                    data = f.read()
            if data:
                with open(d.GetPath(), "wb") as f:
                    f.write(data)

    def _on_remove_attach(self, event=None):
        idx = self.list_attach.GetFirstSelected()
        if 0 <= idx < len(self._attachments):
            del self._attachments[idx]
            self._refresh_attach_list()

    def _on_attach_open(self, event=None):
        idx = self.list_attach.GetFirstSelected()
        if idx < 0 or idx >= len(self._attachments):
            return
        att = self._attachments[idx]
        import os, sys, tempfile, subprocess
        path = att.get("path")
        if not path and att.get("data"):
            path = os.path.join(tempfile.gettempdir(), att["name"])
            with open(path, "wb") as f:
                f.write(att["data"])
        if path and os.path.exists(path):
            try:
                if sys.platform == "win32":
                    os.startfile(path)
                else:
                    subprocess.Popen(["xdg-open", path])
            except Exception as e:
                wx.MessageBox(str(e), tr("error_title"), wx.OK | wx.ICON_ERROR, self)

    def _refresh_attach_list(self):
        self.list_attach.DeleteAllItems()
        for att in self._attachments:
            size = att.get("size") or 0
            sz   = (f"{size//1024} KB" if size >= 1024 else f"{size} B") if size else "?"
            idx  = self.list_attach.InsertItem(
                self.list_attach.GetItemCount(), att["name"])
            self.list_attach.SetItem(idx, 1, sz)
        count = len(self._attachments)
        self.lbl_attach.SetLabel(
            tr("compose_attach_list", count=count) if count
            else tr("compose_attach_empty"))

    # ------------------------------------------------------------------ #
    #  Senden                                                             #
    # ------------------------------------------------------------------ #

    def _on_send(self, event):
        to_str = self.txt_to.GetValue().strip()
        if not to_str:
            wx.MessageBox(tr("compose_err_no_to"), tr("error_title"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        if not self._accs:
            wx.MessageBox(tr("imap_no_account"), tr("hint_title"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return

        idx = self.cho_from.GetSelection()
        acc = self._accs[idx] if 0 <= idx < len(self._accs) else self._accs[0]

        body_text, body_html = self._get_body_content()

        # Anhang-Pfade für SMTPHandler (nur Pfade, keine Bytes)
        import os, tempfile
        attach_paths = []
        for att in self._attachments:
            if att.get("path") and os.path.exists(att["path"]):
                attach_paths.append(att["path"])
            elif att.get("data"):
                # Temp-Datei für Bytes-Anhänge (Weiterleitungs-Anhänge)
                tmp = os.path.join(tempfile.gettempdir(), att["name"])
                with open(tmp, "wb") as f:
                    f.write(att["data"])
                attach_paths.append(tmp)

        from datetime import datetime as _dt
        mail_data = {
            "subject":     self.txt_subject.GetValue().strip(),
            "sender":      acc["email"],
            "sender_name": acc["name"],
            "recipients":  to_str,
            "cc":          self.txt_cc.GetValue().strip(),
            "date":        _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            "body_text":   body_text,
            "body_html":   body_html,
            "is_read":     1,
            "has_attach":  int(bool(self._attachments)),
            "size":        len(body_text) + len(body_html),
        }

        try:
            from protocols.pop3_smtp_handler import SMTPHandler
            to_list = [a.strip() for a in to_str.split(",") if a.strip()]
            cc_list = [a.strip() for a in self.txt_cc.GetValue().split(",") if a.strip()]
            smtp = SMTPHandler(
                host=acc["out_host"], port=int(acc.get("out_port") or 587),
                username=acc.get("username") or acc["email"],
                password=acc.get("password") or "",
                use_ssl=bool(acc.get("out_ssl", 1)),
            )
            raw_bytes = smtp.send(
                from_addr=acc["email"],
                to_addrs=to_list,
                subject=mail_data["subject"],
                body_text=body_text,
                body_html=body_html,
                cc=cc_list,
                attachments=attach_paths,
            )
            # In Gesendet-Ordner speichern
            sent_id = self.controller._get_sent_folder_id(acc["id"])
            if sent_id:
                self.controller.db.insert_mail(sent_id, mail_data)
            # IMAP: als gelesene Mail in Gesendet-Ordner hochladen
            if acc.get("protocol", "IMAP").upper() == "IMAP" and acc.get("in_host"):
                import threading
                from core.app_controller import _make_imap
                def _append(acc=acc, raw=raw_bytes):
                    try:
                        with _make_imap(acc) as imap:
                            folders = imap.list_folders()
                            for fo in folders:
                                if self.controller._guess_folder_type(
                                        fo["name"]) == "sent":
                                    imap.append_mail(fo["path"], raw, "\\Seen")
                                    break
                    except Exception:
                        pass
                threading.Thread(target=_append, daemon=True).start()
            wx.MessageBox(tr("compose_send_ok"), tr("hint_title"),
                          wx.OK | wx.ICON_INFORMATION, self)
            self.EndModal(wx.ID_OK)

        except RuntimeError as e:
            outbox_id = self.controller._get_outbox_folder_id()
            if outbox_id:
                self.controller.db.insert_mail(outbox_id, mail_data)
                wx.MessageBox(
                    tr("compose_send_err", error=str(e)) + "\n\n" +
                    tr("compose_saved_outbox"),
                    tr("error_title"), wx.OK | wx.ICON_WARNING, self)
            else:
                wx.MessageBox(tr("compose_send_err", error=str(e)),
                              tr("error_title"), wx.OK | wx.ICON_ERROR, self)

    def _on_key(self, event: wx.KeyEvent):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            if wx.MessageBox(tr("compose_discard_confirm"),
                             tr("compose_title_new"),
                             wx.YES_NO | wx.NO_DEFAULT, self) == wx.YES:
                self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()


# ================================================================== #
#  SetupDialog – Ersteinrichtung beim ersten Start                    #
# ================================================================== #

class SetupDialog(wx.Dialog):
    """Wird beim ersten Start angezeigt wenn noch kein Konto vorhanden ist."""

    def __init__(self, parent, controller):
        super().__init__(parent, title=tr("setup_title"), size=(480, 220),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.controller = controller
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label=tr("setup_title"))
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 14)

        desc = wx.StaticText(panel, label=tr("setup_desc"))
        sizer.Add(desc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 14)

        sizer.AddStretchSpacer()

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_create = wx.Button(panel, wx.ID_OK,     tr("setup_create"))
        btn_skip   = wx.Button(panel, wx.ID_CANCEL, tr("setup_skip"))
        btn_create.SetDefault()
        btn_row.Add(btn_create, 0, wx.RIGHT, 8)
        btn_row.Add(btn_skip)
        sizer.Add(btn_row, 0, wx.ALIGN_RIGHT | wx.ALL, 14)

        panel.SetSizer(sizer)

# Re-export FolderPickerDialog for import from dialogs
from ui.folder_picker import FolderPickerDialog


# ================================================================== #
#  AuthCredentialsDialog – Zugangsdaten bei Auth-Fehler              #
# ================================================================== #

class AuthCredentialsDialog(wx.Dialog):
    """
    Wird angezeigt wenn eine IMAP/POP3/SMTP-Anmeldung fehlschlägt.
    Erlaubt dem Nutzer Username und Passwort zu korrigieren.
    Bei Erfolg werden die neuen Daten in der DB gespeichert.
    """

    def __init__(self, parent, controller, account_id: int, host: str):
        super().__init__(parent,
                         title=tr("auth_error_title"),
                         size=(420, 260),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.controller = controller
        self.account_id = account_id
        self.host       = host
        self._build_ui(host)
        self.Centre()

    def _build_ui(self, host: str):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel,
            label=tr("auth_error_msg", host=host))
        lbl.SetForegroundColour(wx.Colour(180, 0, 0))
        sizer.Add(lbl, 0, wx.ALL, 12)

        gs = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs.AddGrowableCol(1)

        gs.Add(wx.StaticText(panel, label=tr("auth_new_username")),
               0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_user = wx.TextCtrl(panel)
        gs.Add(self.txt_user, 1, wx.EXPAND)

        gs.Add(wx.StaticText(panel, label=tr("auth_new_password")),
               0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_pass = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        gs.Add(self.txt_pass, 1, wx.EXPAND)

        sizer.Add(gs, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # Aktuelle Daten vorladen
        acc = self.controller.get_account(self.account_id)
        if acc:
            self.txt_user.SetValue(str(acc["username"] or acc["email"] or ""))

        bs = wx.StdDialogButtonSizer()
        btn_ok     = wx.Button(panel, wx.ID_OK,     tr("auth_retry"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, tr("dlg_cancel"))
        btn_ok.SetDefault()
        bs.AddButton(btn_ok); bs.AddButton(btn_cancel); bs.Realize()
        sizer.Add(bs, 0, wx.EXPAND | wx.ALL, 12)

        panel.SetSizer(sizer)
        btn_ok.Bind(wx.EVT_BUTTON, self._on_ok)
        self.txt_user.SetFocus()

    def _on_ok(self, event):
        username = self.txt_user.GetValue().strip()
        password = self.txt_pass.GetValue()
        if not username:
            wx.MessageBox(tr("account_err_required"), tr("error_title"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        # Zugangsdaten in DB aktualisieren
        acc = self.controller.get_account(self.account_id)
        if acc:
            data = dict(acc)
            data["username"] = username
            data["password"] = password
            self.controller.save_account(data)
        self.EndModal(wx.ID_OK)

    def get_credentials(self):
        """Gibt (username, password) zurück."""
        return self.txt_user.GetValue().strip(), self.txt_pass.GetValue()
