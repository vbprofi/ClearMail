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
        self.txt_name.SetFocus()

    @staticmethod
    def _w(grid):
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(grid, 1, wx.EXPAND | wx.ALL, 12)
        return s

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
        pg1.SetSizer(self._w(gs1))
        nb.AddPage(pg1, tr("settings_tab_general"))

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
        self._storage_codes  = [STORAGE_SQLITE_ONE, STORAGE_SQLITE_PER_ACCOUNT, STORAGE_FILES]
        self._storage_labels = [
            tr("settings_storage_sqlite_one"),
            tr("settings_storage_sqlite_per_account"),
            tr("settings_storage_files"),
        ]
        self.cho_storage = wx.Choice(pg4, choices=self._storage_labels)
        self.cho_storage.SetName(tr("settings_storage_mode"))
        gs4.Add(lbl_storage, 0, wx.ALIGN_CENTER_VERTICAL)
        gs4.Add(self.cho_storage, 1, wx.EXPAND)

        pg4.SetSizer(self._w(gs4))
        nb.AddPage(pg4, tr("settings_tab_storage"))

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

    def _load(self):
        g = self.controller.get_setting
        self.chk_auto.SetValue(g("auto_fetch",      "0") == "1")
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

    def _on_save(self, event):
        s   = self.controller.set_setting
        g   = self.controller.get_setting
        s("auto_fetch",     "1" if self.chk_auto.GetValue() else "0")
        s("fetch_interval", str(self.spn_interval.GetValue()))
        s("render_html",    "1" if self.chk_html.GetValue() else "0")
        s("confirm_delete", "1" if self.chk_confirm_del.GetValue() else "0")
        s("font_size",      str(self.spn_font.GetValue()))
        s("delete_to_trash","1" if self.rb_trash.GetValue() else "0")

        # Sprache
        idx_lang = self.cho_lang.GetSelection()
        if 0 <= idx_lang < len(self._lang_codes):
            s("language", self._lang_codes[idx_lang])

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

        # Version aus version_info lesen – funktioniert in Entwicklung UND als .exe
        # Da version_info.py jetzt via datas in _MEIPASS gebündelt wird,
        # ist APP_VERSION auch in der kompilierten EXE korrekt.
        try:
            from version_info import get_version
            version = get_version()   # Immer frisch lesen (nicht gecachten APP_VERSION nutzen)
        except Exception:
            try:
                from version_info import APP_VERSION
                version = APP_VERSION
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

    def __init__(self, parent, controller, reply_to=None, reply_all=False, forward=None):
        title = tr("compose_title_reply") if reply_to else (
                tr("compose_title_forward") if forward else tr("compose_title_new"))
        super().__init__(parent, title=title, size=(640, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._prefill(reply_to, reply_all, forward)
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        gs    = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        gs.AddGrowableCol(1)
        accs         = self.controller.get_accounts()
        from_choices = [f"{a['name']} <{a['email']}>" for a in accs] or ["(–)"]
        self.cho_from    = add_labeled_field(panel, gs, tr("compose_from"),
                                              lambda p: wx.Choice(p, choices=from_choices))
        self.cho_from.SetSelection(0)
        self.txt_to      = add_labeled_field(panel, gs, tr("compose_to"),      lambda p: wx.TextCtrl(p))
        self.txt_cc      = add_labeled_field(panel, gs, tr("compose_cc"),      lambda p: wx.TextCtrl(p))
        self.txt_subject = add_labeled_field(panel, gs, tr("compose_subject"), lambda p: wx.TextCtrl(p))
        sizer.Add(gs, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(wx.StaticText(panel, label=tr("compose_body")), 0, wx.LEFT | wx.TOP, 8)
        self.txt_body = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.BORDER_SUNKEN)
        self.txt_body.SetName(tr("compose_body"))
        self.txt_body.SetMinSize((-1, 200))
        sizer.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 8)
        row = wx.BoxSizer(wx.HORIZONTAL)
        btn_send   = wx.Button(panel, label=tr("compose_send"))
        btn_attach = wx.Button(panel, label=tr("compose_attach"))
        btn_disc   = wx.Button(panel, wx.ID_CANCEL, tr("compose_discard"))
        btn_send.Bind(wx.EVT_BUTTON,   self._on_send)
        btn_attach.Bind(wx.EVT_BUTTON, self._on_attach)
        row.Add(btn_send, 0, wx.RIGHT, 8);  row.Add(btn_attach, 0, wx.RIGHT, 8)
        row.AddStretchSpacer();  row.Add(btn_disc)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)
        self.txt_to.SetFocus()

    def _prefill(self, reply_to, reply_all, forward):
        re_prefix  = tr("compose_re_prefix")
        fwd_prefix = tr("compose_fwd_prefix")
        if reply_to:
            self.txt_to.SetValue(str(reply_to.get("sender") or ""))
            if reply_all:
                self.txt_cc.SetValue(str(reply_to.get("recipients") or ""))
            subj = str(reply_to.get("subject") or "")
            self.txt_subject.SetValue(subj if subj.startswith(re_prefix) else re_prefix + subj)
            self.txt_body.SetValue(
                f"\n\n──────────────────\n"
                f"{tr('preview_from')} {reply_to.get('sender_name','')} <{reply_to.get('sender','')}>\n"
                f"{reply_to.get('body_text','') or ''}")
            self.txt_body.SetInsertionPoint(0)
        elif forward:
            subj = str(forward.get("subject") or "")
            self.txt_subject.SetValue(subj if subj.startswith(fwd_prefix) else fwd_prefix + subj)
            self.txt_body.SetValue(
                f"\n\n──────────────────\n"
                f"{tr('preview_from')} {forward.get('sender_name','')} <{forward.get('sender','')}>\n"
                f"{forward.get('body_text','') or ''}")

    def _on_send(self, event):
        if not self.txt_to.GetValue().strip():
            wx.MessageBox(tr("compose_err_no_to"), tr("error_title"), wx.OK | wx.ICON_WARNING, self)
            return
        wx.MessageBox(tr("compose_smtp_todo"), tr("hint_title"), wx.OK | wx.ICON_INFORMATION, self)

    def _on_attach(self, event):
        with wx.FileDialog(self, tr("attach_title"),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as d:
            if d.ShowModal() == wx.ID_OK:
                wx.MessageBox(tr("attach_msg", count=len(d.GetPaths())), tr("hint_title"), wx.OK, self)
