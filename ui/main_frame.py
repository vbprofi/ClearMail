import os
"""
MainFrame – Hauptfenster (i18n, Papierkorb-Unterstützung)
"""

import wx, wx.adv
from core.i18n import tr
from ui.folder_panel import FolderPanel
from ui.mail_list_panel import MailListPanel
from ui.mail_preview_panel import MailPreviewPanel
from ui.mail_viewer import MailViewerFrame
from ui.search_dialog import SearchDialog
from ui.dialogs import (
    AccountDialog, SettingsDialog, PrintPreviewDialog,
    PGPDialog, AddonManagerDialog, AboutDialog, ComposeDialog,
    SetupDialog, FolderPickerDialog, AuthCredentialsDialog
)


class MainFrame(wx.Frame):

    def __init__(self, parent, title, controller):
        super().__init__(parent, title=title, size=(1024, 700),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.controller = controller
        controller.view = self
        self._selected_folder_id   = None
        self._selected_mail_id    = None
        self._selected_mailbox_id = None
        self._selected_folder_name = ""
        self._mark_read_timer      = None   # wx.CallLater für „Als gelesen nach X Sek."

        self._build_menu()
        self._build_status_bar()
        self._build_layout()
        self._bind_events()
        self.Centre()
        self._set_initial_accessibility()

    # ------------------------------------------------------------------ #
    #  Menü                                                               #
    # ------------------------------------------------------------------ #

    def _build_menu(self):
        mb = wx.MenuBar()

        mf = wx.Menu()
        self.mi_new_mail   = mf.Append(wx.ID_NEW,    tr("menu_file_new"))
        mf.AppendSeparator()
        self.mi_open_email = mf.Append(wx.ID_OPEN,   tr("menu_file_open"))
        self.mi_save_email = mf.Append(wx.ID_SAVE,   tr("menu_file_save"))
        self.mi_save_txt   = mf.Append(wx.ID_ANY,    tr("menu_file_save_txt"))
        mf.AppendSeparator()
        self.mi_print      = mf.Append(wx.ID_PRINT,  tr("menu_file_print"))
        mf.AppendSeparator()
        self.mi_exit       = mf.Append(wx.ID_EXIT,   tr("menu_file_exit"))
        mb.Append(mf, tr("menu_file"))

        me = wx.Menu()
        self.mi_select_all = me.Append(wx.ID_SELECTALL, tr("menu_edit_select_all"))
        self.mi_copy       = me.Append(wx.ID_COPY,       tr("menu_edit_copy"))
        me.AppendSeparator()
        self.mi_find       = me.Append(wx.ID_FIND,       tr("menu_edit_find"))
        mb.Append(me, tr("menu_edit"))

        mv = wx.Menu()
        self.mi_refresh    = mv.Append(wx.ID_REFRESH, tr("menu_view_refresh"))
        mv.AppendSeparator()
        self.mi_col_date   = mv.AppendCheckItem(wx.ID_ANY, tr("menu_view_col_date"))
        self.mi_col_size   = mv.AppendCheckItem(wx.ID_ANY, tr("menu_view_col_size"))
        self.mi_col_date.Check(True);  self.mi_col_size.Check(True)
        mv.AppendSeparator()

        # ---- Sortieren-Untermenü (Thunderbird-Stil) ----
        ms = wx.Menu()
        # Sortierfelder
        self._sort_items = {}
        for key, label in [
            ("date",    tr("sort_date")),
            ("from",    tr("sort_from")),
            ("subject", tr("sort_subject")),
            ("size",    tr("sort_size")),
            ("status",  tr("sort_status")),
            ("flag",    tr("sort_flag")),
            ("attach",  tr("sort_attach")),
        ]:
            mi = ms.AppendRadioItem(wx.ID_ANY, label)
            self._sort_items[key] = mi
            self.Bind(wx.EVT_MENU, lambda e, k=key: self._on_sort(k), mi)
        self._sort_items["date"].Check(True)

        ms.AppendSeparator()
        self.mi_sort_asc  = ms.AppendRadioItem(wx.ID_ANY, tr("sort_asc"))
        self.mi_sort_desc = ms.AppendRadioItem(wx.ID_ANY, tr("sort_desc"))
        self.mi_sort_desc.Check(True)
        self.Bind(wx.EVT_MENU, lambda e: self._on_sort_direction(), self.mi_sort_asc)
        self.Bind(wx.EVT_MENU, lambda e: self._on_sort_direction(), self.mi_sort_desc)

        mv.AppendSubMenu(ms, tr("menu_view_sort"))
        mb.Append(mv, tr("menu_view"))

        mm = wx.Menu()
        self.mi_reply      = mm.Append(wx.ID_ANY, tr("menu_mail_reply"))
        self.mi_reply_all  = mm.Append(wx.ID_ANY, tr("menu_mail_reply_all"))
        self.mi_forward    = mm.Append(wx.ID_ANY, tr("menu_mail_forward"))
        mm.AppendSeparator()
        self.mi_delete_mail= mm.Append(wx.ID_DELETE, tr("menu_mail_delete"))
        self.mi_mark_read  = mm.Append(wx.ID_ANY, tr("menu_mail_mark_read"))
        self.mi_mark_unread= mm.Append(wx.ID_ANY, tr("menu_mail_mark_unread"))
        self.mi_flag       = mm.Append(wx.ID_ANY, tr("menu_mail_flag"))
        mb.Append(mm, tr("menu_mail"))

        mac = wx.Menu()
        self.mi_new_account  = mac.Append(wx.ID_ANY, tr("menu_accounts_new"))
        self.mi_edit_account = mac.Append(wx.ID_ANY, tr("menu_accounts_edit"))
        self.mi_del_account  = mac.Append(wx.ID_ANY, tr("menu_accounts_delete"))
        mac.AppendSeparator()
        self.mi_fetch        = mac.Append(wx.ID_ANY, tr("menu_accounts_fetch"))
        self.mi_send_outbox  = mac.Append(wx.ID_ANY, tr("menu_accounts_send_outbox"))
        mb.Append(mac, tr("menu_accounts"))

        mx = wx.Menu()
        self.mi_settings = mx.Append(wx.ID_PREFERENCES, tr("menu_extras_settings"))
        self.mi_pgp      = mx.Append(wx.ID_ANY,         tr("menu_extras_pgp"))
        self.mi_addons   = mx.Append(wx.ID_ANY,         tr("menu_extras_addons"))
        self.mi_addrbook = mx.Append(wx.ID_ANY,         tr("menu_extras_addressbook"))
        mb.Append(mx, tr("menu_extras"))

        mh = wx.Menu()
        self.mi_about = mh.Append(wx.ID_ABOUT, tr("menu_help_about"))
        mb.Append(mh, tr("menu_help"))

        self.SetMenuBar(mb)

    def _build_status_bar(self):
        self.status_bar = self.CreateStatusBar(3)
        self.status_bar.SetStatusWidths([-3, 160, -1])
        self.status_bar.SetStatusText(tr("status_ready"), 0)
        # Fortschrittsleiste in Statusbar-Feld 1
        self._gauge = wx.Gauge(self.status_bar, range=100,
                               style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self._gauge.Hide()
        self.status_bar.Bind(wx.EVT_SIZE, self._on_statusbar_size)

    def _on_statusbar_size(self, event):
        rect = self.status_bar.GetFieldRect(1)
        self._gauge.SetPosition((rect.x + 2, rect.y + 2))
        self._gauge.SetSize((rect.width - 4, rect.height - 4))
        event.Skip()

    def _show_gauge(self, pct: int):
        if pct < 0:
            self._gauge.Pulse()
        else:
            self._gauge.SetValue(min(pct, 100))
        self._gauge.Show()
        # Gauge neu positionieren
        rect = self.status_bar.GetFieldRect(1)
        self._gauge.SetPosition((rect.x + 2, rect.y + 2))
        self._gauge.SetSize((rect.width - 4, rect.height - 4))

    def _hide_gauge(self):
        self._gauge.Hide()
        self._gauge.SetValue(0)

    def _build_layout(self):
        self.main_splitter  = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.main_splitter.SetMinimumPaneSize(160)
        self.folder_panel   = FolderPanel(self.main_splitter, self.controller)

        self.right_splitter = wx.SplitterWindow(self.main_splitter, style=wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.right_splitter.SetMinimumPaneSize(80)
        self.mail_list_panel    = MailListPanel(self.right_splitter, self.controller)
        self.mail_preview_panel = MailPreviewPanel(self.right_splitter, self.controller)

        self.right_splitter.SplitHorizontally(self.mail_list_panel, self.mail_preview_panel, 280)
        self.main_splitter.SplitVertically(self.folder_panel, self.right_splitter, 220)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.main_splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def _bind_events(self):
        id_f6       = wx.NewIdRef()
        id_shift_f6 = wx.NewIdRef()
        id_search   = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, self._on_search_mail, id=id_search)
        self.Bind(wx.EVT_MENU, self._on_search_mail, self.mi_find)
        self.SetAcceleratorTable(wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, wx.WXK_F6,   id_f6),
            (wx.ACCEL_SHIFT,  wx.WXK_F6,   id_shift_f6),
            (wx.ACCEL_CTRL,   ord("F"),     id_search),
        ]))
        self.Bind(wx.EVT_MENU, lambda e: self._focus_next_panel(), id=id_f6)
        self.Bind(wx.EVT_MENU, lambda e: self._focus_prev_panel(), id=id_shift_f6)

        self.Bind(wx.EVT_MENU, self._on_new_mail,     self.mi_new_mail)
        self.Bind(wx.EVT_MENU, self._on_open_email,   self.mi_open_email)
        self.Bind(wx.EVT_MENU, self._on_save_email,   self.mi_save_email)
        self.Bind(wx.EVT_MENU, self._on_save_txt,     self.mi_save_txt)
        self.Bind(wx.EVT_MENU, self._on_print,        self.mi_print)
        self.Bind(wx.EVT_MENU, self._on_exit,         self.mi_exit)
        self.Bind(wx.EVT_MENU, self._on_reply,        self.mi_reply)
        self.Bind(wx.EVT_MENU, self._on_reply_all,    self.mi_reply_all)
        self.Bind(wx.EVT_MENU, self._on_forward,      self.mi_forward)
        self.Bind(wx.EVT_MENU, self._on_delete_mail,  self.mi_delete_mail)
        self.Bind(wx.EVT_MENU, lambda e: self._on_mark(True),  self.mi_mark_read)
        self.Bind(wx.EVT_MENU, lambda e: self._on_mark(False), self.mi_mark_unread)
        self.Bind(wx.EVT_MENU, self._on_flag,         self.mi_flag)
        self.Bind(wx.EVT_MENU, self._on_refresh,      self.mi_refresh)
        self.Bind(wx.EVT_MENU, self._on_new_account,  self.mi_new_account)
        self.Bind(wx.EVT_MENU, self._on_edit_account, self.mi_edit_account)
        self.Bind(wx.EVT_MENU, self._on_del_account,  self.mi_del_account)
        self.Bind(wx.EVT_MENU, self._on_fetch,        self.mi_fetch)
        self.Bind(wx.EVT_MENU, self._on_send_outbox,  self.mi_send_outbox)
        self.Bind(wx.EVT_MENU, self._on_settings,     self.mi_settings)
        self.Bind(wx.EVT_MENU, self._on_pgp,          self.mi_pgp)
        self.Bind(wx.EVT_MENU, self._on_addons,       self.mi_addons)
        self.Bind(wx.EVT_MENU, self._on_addressbook,  self.mi_addrbook)
        self.Bind(wx.EVT_MENU, self._on_about,        self.mi_about)

        self.folder_panel.on_folder_selected    = self._on_folder_selected
        self.mail_list_panel.on_mail_selected   = self._on_mail_selected
        self.mail_list_panel.on_mail_open       = self._on_open_mail_viewer
        self.mail_list_panel.on_mail_delete     = self._on_delete_mail
        self.mail_list_panel.on_context_menu    = self._show_mail_context_menu

    def _set_initial_accessibility(self):
        self.SetName(tr("app_title"))
        self.folder_panel.tree.SetName(tr("folder_mailboxes"))

    # ------------------------------------------------------------------ #
    #  F6-Navigation                                                      #
    # ------------------------------------------------------------------ #

    _panels_order = ["folder", "list", "preview"]

    def _focus_next_panel(self):
        cur = self._current_focus_panel()
        o   = self._panels_order
        self._focus_panel(o[(o.index(cur) + 1) % len(o)])

    def _focus_prev_panel(self):
        cur = self._current_focus_panel()
        o   = self._panels_order
        self._focus_panel(o[(o.index(cur) - 1) % len(o)])

    @staticmethod
    def _is_child_of(child, ancestor) -> bool:
        try:
            w = child
            while w is not None:
                if w is ancestor: return True
                w = w.GetParent()
        except RuntimeError:
            pass
        return False

    def _current_focus_panel(self) -> str:
        f = self.FindFocus()
        if f is None: return "folder"
        if self._is_child_of(f, self.folder_panel):    return "folder"
        if self._is_child_of(f, self.mail_list_panel): return "list"
        if self._is_child_of(f, self.mail_preview_panel): return "preview"
        return "folder"

    def _focus_panel(self, panel: str):
        if panel == "folder":
            self.folder_panel.tree.SetFocus()
            self.status_bar.SetStatusText(tr("status_focus_folder"), 2)
        elif panel == "list":
            self.mail_list_panel.list_ctrl.SetFocus()
            self.status_bar.SetStatusText(tr("status_focus_list"), 2)
        elif panel == "preview":
            self.mail_preview_panel.txt_body.SetFocus()
            self.status_bar.SetStatusText(tr("status_focus_preview"), 2)

    # ------------------------------------------------------------------ #
    #  Panel-Callbacks                                                    #
    # ------------------------------------------------------------------ #

    def _on_folder_selected(self, folder_id: int, folder_name: str, mailbox_id: int = None):
        self._selected_folder_id  = folder_id
        self._selected_mailbox_id = mailbox_id
        self._selected_folder_name = folder_name
        mails = self.controller.get_mails(folder_id)
        self.mail_list_panel.load_mails(mails)
        self.mail_preview_panel.clear()
        self.status_bar.SetStatusText(tr("status_folder", name=folder_name), 0)
        self.status_bar.SetStatusText(tr("status_messages", count=len(mails)), 1)
        self._selected_mail_id = None
        # Titelleiste aktualisieren
        app_name = tr("app_title")
        self.SetTitle(tr("title_bar_format", folder=folder_name, app=app_name))
        # Ausgewählten Ordner persistent speichern
        self.controller.set_setting("last_folder_id", str(folder_id))

    def _on_mail_selected(self, mail_id: int):
        # Laufenden Timer abbrechen (andere Mail angeklickt)
        if self._mark_read_timer:
            try: self._mark_read_timer.Stop()
            except Exception: pass
            self._mark_read_timer = None

        self._selected_mail_id = mail_id
        # get_mail OHNE automatisches Markieren als gelesen – das steuert der Timer
        mail = self.controller.db.get_mail(mail_id, self._selected_folder_id)
        if mail:
            self.mail_preview_panel.show_mail(dict(mail))
            if self._selected_folder_id:
                self.folder_panel.refresh_folder_unread(self._selected_folder_id)

            delay_s = int(self.controller.get_setting("mark_read_after", "0"))
            mail_d  = dict(mail)
            already_read = int(mail_d.get("is_read") or 0)

            if already_read:
                # Bereits gelesen – nichts tun
                return

            if delay_s == 0:
                # Sofort als gelesen markieren
                fid = self._selected_folder_id
                self.controller.mark_mail_read(mail_id, True, folder_id=fid)
                if fid:
                    self.controller.db.update_folder_unread(fid)
                self.mail_list_panel.refresh_mail_read(mail_id, force_read=True)
                if fid:
                    self.folder_panel.refresh_folder_unread(fid)
                self.controller.addon_mgr.fire("mail_read", {"mail_id": mail_id})
            elif delay_s > 0:
                # Nach X Sekunden als gelesen markieren
                self._mark_read_timer = wx.CallLater(
                    delay_s * 1000, self._auto_mark_read, mail_id
                )

    def _auto_mark_read(self, mail_id: int):
        """Wird nach Ablauf des Timers aufgerufen – markiert Mail als gelesen."""
        self._mark_read_timer = None
        if self._selected_mail_id != mail_id:
            return  # Nutzer hat inzwischen andere Mail gewählt
        fid = self._selected_folder_id
        self.controller.mark_mail_read(mail_id, True, folder_id=fid)
        if fid:
            self.controller.db.update_folder_unread(fid)
        self.mail_list_panel.refresh_mail_read(mail_id, force_read=True)
        if fid:
            self.folder_panel.refresh_folder_unread(fid)

    def _on_open_mail_viewer(self, mail_id: int):
        """Öffnet eine Mail in einem eigenen Fenster (Doppelklick / Enter)."""
        mail = self.controller.get_mail(mail_id, self._selected_folder_id)
        if mail:
            viewer = MailViewerFrame(self, dict(mail), controller=self.controller)
            viewer.Show()
            # Ungelesen-Status in Liste aktualisieren
            self.mail_list_panel.refresh_mail_read(mail_id)
            if self._selected_folder_id:
                self.folder_panel.refresh_folder_unread(self._selected_folder_id)

    # ------------------------------------------------------------------ #
    #  Mail-Aktionen                                                      #
    # ------------------------------------------------------------------ #

    def _on_new_mail(self, event):
        dlg = ComposeDialog(self, self.controller)
        dlg.ShowModal(); dlg.Destroy()

    def _on_reply(self, event):
        if not self._selected_mail_id: return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            dlg = ComposeDialog(self, self.controller, reply_to=dict(mail))
            dlg.ShowModal(); dlg.Destroy()

    def _on_reply_all(self, event):
        if not self._selected_mail_id: return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            dlg = ComposeDialog(self, self.controller, reply_to=dict(mail), reply_all=True)
            dlg.ShowModal(); dlg.Destroy()

    def _on_forward(self, event):
        if not self._selected_mail_id: return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            dlg = ComposeDialog(self, self.controller, forward=dict(mail))
            dlg.ShowModal(); dlg.Destroy()

    def _on_delete_mail(self, event=None):
        if not self._selected_mail_id:
            return
        use_trash   = self.controller.get_setting("delete_to_trash", "1") == "1"
        confirm     = self.controller.get_setting("confirm_delete",  "1") == "1"

        if confirm:
            msg   = tr("dlg_delete_mail_trash") if use_trash else tr("dlg_delete_mail_msg")
            title = tr("dlg_delete_mail_title")
            if wx.MessageBox(msg, title, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
                return

        result = self.controller.delete_mail(
            self._selected_mail_id,
            self._selected_folder_id,
            mailbox_id=self._selected_mailbox_id,
            use_trash=use_trash
        )
        self.mail_list_panel.remove_mail(self._selected_mail_id)
        self.mail_preview_panel.clear()
        self._selected_mail_id = None

        if self._selected_folder_id:
            self.folder_panel.refresh_folder_unread(self._selected_folder_id)
        # Papierkorb-Counter aktualisieren
        if result == "moved_to_trash" and self._selected_mailbox_id:
            trash_id = self.controller.get_trash_folder_id(self._selected_mailbox_id)
            if trash_id:
                self.folder_panel.refresh_folder_unread(trash_id)

    def _on_mark(self, is_read: bool):
        if not self._selected_mail_id: return
        fid = self._selected_folder_id
        self.controller.mark_mail_read(self._selected_mail_id, is_read, folder_id=fid)
        if fid:
            self.controller.db.update_folder_unread(fid)
        self.mail_list_panel.refresh_mail_read(self._selected_mail_id, force_read=is_read)
        if fid:
            self.folder_panel.refresh_folder_unread(fid)

    def _on_flag(self, event):
        if not self._selected_mail_id: return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            self.controller.mark_mail_flagged(self._selected_mail_id, not bool(mail["is_flagged"]))
            self.mail_list_panel.reload_current_folder()

    def _on_copy_mail(self, event=None):
        """Mail in einen anderen Ordner kopieren."""
        if not self._selected_mail_id: return
        dlg = FolderPickerDialog(self, self.controller,
                                 title=tr("ctx_copy_to_folder"))
        if dlg.ShowModal() == wx.ID_OK:
            target_fid = dlg.selected_folder_id
            if target_fid:
                self.controller.copy_mail(
                    self._selected_mail_id, target_fid,
                    source_folder_id=self._selected_folder_id)
                self.folder_panel.refresh_folder_unread(target_fid)
        dlg.Destroy()

    def _on_move_mail(self, event=None):
        """Mail in einen anderen Ordner verschieben."""
        if not self._selected_mail_id: return
        dlg = FolderPickerDialog(self, self.controller,
                                 title=tr("ctx_move_to"))
        if dlg.ShowModal() == wx.ID_OK:
            target_fid = dlg.selected_folder_id
            if target_fid and target_fid != self._selected_folder_id:
                self.controller.move_mail(
                    self._selected_mail_id, target_fid,
                    source_folder_id=self._selected_folder_id)
                if self._selected_folder_id:
                    self.folder_panel.refresh_folder_unread(self._selected_folder_id)
                self.folder_panel.refresh_folder_unread(target_fid)
                self.mail_list_panel.remove_mail(self._selected_mail_id)
                self.mail_preview_panel.clear()
        dlg.Destroy()

    def _on_search(self, event=None):
        """Suchfenster öffnen."""
        dlg = SearchDialog(self, self.controller)
        dlg.Show()

    def _on_sort(self, sort_key: str):
        """Sortiert die Mailliste nach dem gewählten Feld."""
        from ui.mail_list_panel import COL_DATE, COL_FROM, COL_SUBJECT, COL_SIZE, COL_READ, COL_FLAG
        col_map = {
            "date":    COL_DATE,
            "from":    COL_FROM,
            "subject": COL_SUBJECT,
            "size":    COL_SIZE,
            "status":  COL_READ,
            "flag":    COL_FLAG,
            "attach":  COL_SUBJECT,
        }
        self.mail_list_panel._sort_col = col_map.get(sort_key, COL_DATE)
        self.mail_list_panel._sort_asc = self.mi_sort_asc.IsChecked()
        self.mail_list_panel._apply_sort_to_data()
        self.mail_list_panel._rebuild_from_sorted_data()

    def _on_sort_direction(self):
        """Richtungswechsel ohne Feldwechsel."""
        self.mail_list_panel._sort_asc = self.mi_sort_asc.IsChecked()
        self.mail_list_panel._apply_sort_to_data()
        self.mail_list_panel._rebuild_from_sorted_data()

    def _on_refresh(self, event):
        if self._selected_folder_id:
            self._on_folder_selected(self._selected_folder_id,
                                     self.folder_panel.get_selected_folder_name(),
                                     self._selected_mailbox_id)

    # ------------------------------------------------------------------ #
    #  Datei-Aktionen                                                     #
    # ------------------------------------------------------------------ #

    def _on_open_email(self, event):
        wildcard = (
            "Alle unterstützten Formate (*.email;*.eml;*.txt)|*.email;*.eml;*.txt|"
            "E-Mail-Datei (*.email)|*.email|"
            "EML-Datei (*.eml)|*.eml|"
            "Textdatei (*.txt)|*.txt"
        )
        with wx.FileDialog(self, tr("open_email_title"),
                           wildcard=wildcard,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as d:
            if d.ShowModal() == wx.ID_OK:
                data = self.controller.open_mail_file(d.GetPath())
                if data:
                    # Vorschau aktualisieren UND in eigenem Fenster öffnen
                    self.mail_preview_panel.show_mail(data)
                    viewer = MailViewerFrame(self, data, controller=self.controller)
                    viewer.Show()
                else:
                    wx.MessageBox(tr("error_open_file"), tr("error_title"), wx.OK | wx.ICON_ERROR, self)

    def _on_save_email(self, event):
        if not self._selected_mail_id:
            wx.MessageBox(tr("hint_select_mail"), tr("hint_title"), wx.OK, self); return
        with wx.FileDialog(self, tr("save_email_title"),
                           wildcard="E-Mail-Datei (*.email)|*.email|EML-Datei (*.eml)|*.eml",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as d:
            if d.ShowModal() == wx.ID_OK:
                path = d.GetPath()
                ext  = os.path.splitext(path)[1].lower()
                ok   = (self.controller.save_mail_as_eml(self._selected_mail_id, path, folder_id=self._selected_folder_id)
                        if ext == ".eml" else
                        self.controller.save_mail_as_email(self._selected_mail_id, path, folder_id=self._selected_folder_id))
                if not ok:
                    wx.MessageBox(tr("error_save_file"), tr("error_title"), wx.OK | wx.ICON_ERROR, self)

    def _on_save_txt(self, event):
        if not self._selected_mail_id:
            wx.MessageBox(tr("hint_select_mail"), tr("hint_title"), wx.OK, self); return
        with wx.FileDialog(self, tr("save_txt_title"),
                           wildcard=tr("wildcard_txt"),
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as d:
            if d.ShowModal() == wx.ID_OK:
                if not self.controller.save_mail_as_txt(self._selected_mail_id, d.GetPath(), folder_id=self._selected_folder_id):
                    wx.MessageBox(tr("error_save_file"), tr("error_title"), wx.OK | wx.ICON_ERROR, self)

    def _on_print(self, event):
        if not self._selected_mail_id: return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            dlg = PrintPreviewDialog(self, dict(mail)); dlg.ShowModal(); dlg.Destroy()

    # ------------------------------------------------------------------ #
    #  Konten                                                             #
    # ------------------------------------------------------------------ #

    def _on_new_account(self, event):
        dlg = AccountDialog(self, self.controller)
        if dlg.ShowModal() == wx.ID_OK:
            self.folder_panel.reload()
        dlg.Destroy()

    def _on_edit_account(self, event):
        accs = self.controller.get_accounts()
        if not accs:
            wx.MessageBox(tr("no_accounts"), tr("hint_title"), wx.OK, self); return
        choices = [f"{a['name']} <{a['email']}>" for a in accs]
        with wx.SingleChoiceDialog(self, tr("select_account"), tr("edit_account_title"), choices) as d:
            if d.ShowModal() == wx.ID_OK:
                dlg = AccountDialog(self, self.controller, account_id=accs[d.GetSelection()]["id"])
                dlg.ShowModal(); dlg.Destroy()
                self.folder_panel.reload()  # Name-Änderung sofort anzeigen

    def _on_del_account(self, event):
        accs = self.controller.get_accounts()
        if not accs: return
        choices = [f"{a['name']} <{a['email']}>" for a in accs]
        with wx.SingleChoiceDialog(self, tr("select_account"), tr("delete_account_title"), choices) as d:
            if d.ShowModal() == wx.ID_OK:
                acc = accs[d.GetSelection()]
                if wx.MessageBox(tr("delete_account_msg", name=acc["name"]),
                                 tr("delete_account_title"),
                                 wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) == wx.YES:
                    self.controller.delete_account(acc["id"])
                    self.folder_panel.reload()  # Baumstruktur aktualisieren
                    self.mail_list_panel.load_mails([])
                    self.mail_preview_panel.clear()

    def _on_fetch(self, event):
        """Neue Nachrichten abrufen – läuft in Worker-Thread."""
        accs = [a for a in self.controller.get_accounts()
                if dict(a).get("protocol", "LOCAL") != "LOCAL"]
        if not accs:
            wx.MessageBox(tr("imap_no_account"), tr("hint_title"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        self.status_bar.SetStatusText(tr("fetch_running"), 0)
        self.mi_fetch.Enable(False)

        from core.protocol_runner import ProtocolWorker

        def _done(count):
            self.mi_fetch.Enable(True)
            self._hide_gauge()
            self.status_bar.SetStatusText(tr("imap_fetch_ok", count=count), 0)
            self.folder_panel.reload()
            if self._selected_folder_id:
                mails = self.controller.get_mails(self._selected_folder_id)
                self.mail_list_panel.load_mails(mails)
                self.folder_panel.refresh_folder_unread(self._selected_folder_id)
            if not self._selected_folder_id:
                self._restore_last_folder()

        def _error(msg, is_auth):
            self.mi_fetch.Enable(True)
            self._hide_gauge()
            self.status_bar.SetStatusText("", 0)
            if is_auth:
                self._handle_auth_error(msg, accs)
            else:
                wx.MessageBox(tr("imap_fetch_err", error=msg),
                              tr("error_title"), wx.OK | wx.ICON_ERROR, self)

        def _progress(msg, pct=-1, total=0):
            self.status_bar.SetStatusText(msg, 0)
            self._show_gauge(pct)

        ProtocolWorker(
            fn=self.controller.fetch_new_mails,
            on_progress=_progress,
            on_done=_done,
            on_error=_error,
        ).start()

    def _on_send_outbox(self, event):
        """Postausgang senden – läuft in Worker-Thread."""
        self.status_bar.SetStatusText(tr("send_running"), 0)
        self.mi_send_outbox.Enable(False)

        from core.protocol_runner import ProtocolWorker

        def _done(count):
            self.mi_send_outbox.Enable(True)
            self._hide_gauge()
            self.status_bar.SetStatusText(
                tr("outbox_empty") if count == 0 else tr("smtp_send_ok", count=count), 0)
            self.folder_panel.reload()
            if self._selected_folder_id:
                mails = self.controller.get_mails(self._selected_folder_id)
                self.mail_list_panel.load_mails(mails)

        def _error(msg, is_auth):
            self.mi_send_outbox.Enable(True)
            self._hide_gauge()
            self.status_bar.SetStatusText("", 0)
            accs = [a for a in self.controller.get_accounts()
                    if dict(a).get("protocol", "LOCAL") != "LOCAL"]
            if is_auth:
                self._handle_auth_error(msg, accs)
            else:
                wx.MessageBox(tr("smtp_send_err", error=msg),
                              tr("error_title"), wx.OK | wx.ICON_ERROR, self)

        def _progress(msg, pct=-1, total=0):
            self.status_bar.SetStatusText(msg, 0)
            self._show_gauge(pct)

        ProtocolWorker(
            fn=self.controller.send_outbox,
            on_progress=_progress,
            on_done=_done,
            on_error=_error,
        ).start()

    def _handle_auth_error(self, error_msg: str, accs: list):
        """
        Zeigt AuthCredentialsDialog an.
        Wenn der Nutzer neue Daten eingibt und bestätigt,
        werden sie gespeichert und der Fetch-Vorgang wiederholt.
        """
        from ui.dialogs import AuthCredentialsDialog
        # Konto aus der Fehlermeldung heraussuchen (oder erstes Konto nehmen)
        acc = None
        for a in accs:
            a = dict(a)
            if a.get("in_host", "") in error_msg or a.get("out_host", "") in error_msg:
                acc = a
                break
        if not acc and accs:
            acc = dict(accs[0])
        if not acc:
            return
        host = acc.get("in_host") or acc.get("out_host") or ""
        dlg = AuthCredentialsDialog(self, self.controller, acc["id"], host)
        if dlg.ShowModal() == wx.ID_OK:
            wx.MessageBox(tr("auth_save_ok"), tr("hint_title"),
                          wx.OK | wx.ICON_INFORMATION, self)
            # Erneut versuchen mit neuen Daten
            self._on_fetch(None)
        dlg.Destroy()

    # ------------------------------------------------------------------ #
    #  Extras                                                             #
    # ------------------------------------------------------------------ #

    def _on_settings(self, event):
        dlg = SettingsDialog(self, self.controller); dlg.ShowModal(); dlg.Destroy()

    def _on_pgp(self, event):
        dlg = PGPDialog(self); dlg.ShowModal(); dlg.Destroy()

    def _on_addons(self, event):
        dlg = AddonManagerDialog(self, self.controller); dlg.ShowModal(); dlg.Destroy()

    def _on_addressbook(self, event):
        addons = self.controller.addon_mgr.get_loaded_addons()
        ab = addons.get("addressbook")
        if ab and hasattr(ab, "open_window"):
            ab.open_window(self)
        else:
            wx.MessageBox(
                tr("addressbook_not_loaded"),
                tr("hint_title"), wx.OK | wx.ICON_INFORMATION, self)

    def _on_about(self, event):
        dlg = AboutDialog(self); dlg.ShowModal(); dlg.Destroy()

    def _on_exit(self, event):
        self.Close()

    # ------------------------------------------------------------------ #
    #  Kontext-Menü Mail-Liste                                           #
    # ------------------------------------------------------------------ #

    def _show_mail_context_menu(self, event):
        menu = wx.Menu()
        use_trash = self.controller.get_setting("delete_to_trash", "1") == "1"
        del_label = tr("ctx_delete") + (" → " + tr("folder_trash") if use_trash else "")

        items = [
            (tr("ctx_open"),        lambda e: self._on_open_mail_viewer(self._selected_mail_id)),
            (tr("ctx_reply"),       self._on_reply),
            (tr("ctx_forward"),     self._on_forward),
            None,
            (tr("ctx_save_email"),  self._on_save_email),
            (tr("ctx_save_txt"),    self._on_save_txt),
            None,
            (tr("ctx_copy_to"),     self._on_copy_mail),
            (tr("ctx_move_to"),     self._on_move_mail),
            None,
            (tr("ctx_mark_read"),   lambda e: self._on_mark(True)),
            (tr("ctx_mark_unread"), lambda e: self._on_mark(False)),
            (tr("ctx_flag"),        self._on_flag),
            None,
            (del_label,             self._on_delete_mail),
        ]
        for item in items:
            if item is None:
                menu.AppendSeparator()
            else:
                lbl, fn = item
                mi = menu.Append(wx.ID_ANY, lbl)
                self.Bind(wx.EVT_MENU, fn, mi)

        # ---- Kopieren / Verschieben nach Ordner ----
        menu.AppendSeparator()
        self._append_folder_submenu(menu, tr("ctx_copy_to"), copy=True)
        self._append_folder_submenu(menu, tr("ctx_move_to"), copy=False)

        for entry in self.controller.addon_mgr.get_all_menu_items():
            menu.AppendSeparator()
            mi = menu.Append(wx.ID_ANY, entry["label"])
            self.Bind(wx.EVT_MENU,
                      lambda e, h=entry["handler"]: h(self._selected_mail_id), mi)

        self.PopupMenu(menu)
        menu.Destroy()

    def _append_folder_submenu(self, parent_menu: wx.Menu, label: str, copy: bool):
        """Erstellt ein Untermenü mit allen Postfächern und Ordnern."""
        sub = wx.Menu()
        mailboxes = self.controller.get_mailboxes()
        if not mailboxes:
            mi = sub.Append(wx.ID_ANY, "–")
            mi.Enable(False)
        else:
            for mb in mailboxes:
                mb_sub = wx.Menu()
                folders = self.controller.get_folders(mb["id"])
                for f in folders:
                    fd   = dict(f)
                    lbl  = ("  " * (1 if fd.get("parent_id") else 0)) + fd["name"]
                    mi   = mb_sub.Append(wx.ID_ANY, lbl)
                    fid  = fd["id"]
                    sfid = self._selected_folder_id
                    smid = self._selected_mail_id
                    if copy:
                        self.Bind(wx.EVT_MENU,
                            lambda e, t=fid, s=sfid, m=smid: self._copy_mail(m, t, s), mi)
                    else:
                        self.Bind(wx.EVT_MENU,
                            lambda e, t=fid, s=sfid, m=smid: self._move_mail(m, t, s), mi)
                sub.AppendSubMenu(mb_sub, mb["name"])
        parent_menu.AppendSubMenu(sub, label)

    def _copy_mail(self, mail_id: int, target_folder_id: int, source_folder_id: int):
        """Kopiert eine Mail in einen anderen Ordner (Duplikat anlegen)."""
        if not mail_id or target_folder_id == source_folder_id:
            return
        mail = self.controller.db.get_mail(mail_id, source_folder_id)
        if not mail:
            return
        d = dict(mail)
        d.pop("id", None)
        d["folder_id"] = target_folder_id
        self.controller.db.insert_mail(target_folder_id, d)
        self.controller.db.update_folder_unread(target_folder_id)
        self.folder_panel.refresh_folder_unread(target_folder_id)

    def _move_mail(self, mail_id: int, target_folder_id: int, source_folder_id: int):
        """Verschiebt eine Mail in einen anderen Ordner."""
        if not mail_id or target_folder_id == source_folder_id:
            return
        self.controller.move_mail(mail_id, target_folder_id, source_folder_id)
        self.controller.db.update_folder_unread(source_folder_id)
        self.controller.db.update_folder_unread(target_folder_id)
        self.mail_list_panel.remove_mail(mail_id)
        self.folder_panel.refresh_folder_unread(source_folder_id)
        self.folder_panel.refresh_folder_unread(target_folder_id)
        self.mail_preview_panel.clear()
        self._selected_mail_id = None


    def _on_search_mail(self, event=None):
        """Öffnet das Suchfenster (nicht-modal)."""
        dlg = SearchDialog(
            self, self.controller,
            on_open_mail=self._on_open_mail_from_search
        )
        dlg.Show()

    def _on_open_mail_from_search(self, mail_id: int, folder_id: int):
        """Callback aus SearchDialog: Mail im Viewer öffnen."""
        mail = self.controller.db.get_mail(mail_id, folder_id)
        if mail:
            from ui.mail_viewer import MailViewerFrame
            viewer = MailViewerFrame(self, dict(mail), controller=self.controller)
            viewer.Show()

    def _restore_last_folder(self):
        """Stellt den zuletzt ausgewählten Ordner wieder her.
        Fallback: erster Posteingang in der Baumstruktur."""
        last_id = self.controller.get_setting("last_folder_id", "")
        if last_id:
            try:
                self.folder_panel.select_folder_by_id(int(last_id))
                return
            except (ValueError, Exception):
                pass
        # Fallback: ersten Posteingang auswählen
        for mb in self.controller.get_mailboxes():
            for f in self.controller.get_folders(mb["id"]):
                if dict(f).get("folder_type") == "inbox":
                    self.folder_panel.select_folder_by_id(f["id"])
                    return

    def set_status(self, text: str, pane: int = 0):
        self.status_bar.SetStatusText(text, pane)
