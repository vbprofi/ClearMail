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
        self._is_offline           = False  # Offline-Modus
        from core.auto_fetch import AutoFetchManager
        self._auto_fetch           = AutoFetchManager()

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
        self.mi_empty_trash = mf.Append(wx.ID_ANY,   tr("menu_file_empty_trash"))
        mf.AppendSeparator()
        # Offline-Untermenü
        mo = wx.Menu()
        self.mi_offline_work = mo.AppendCheckItem(wx.ID_ANY, tr("menu_offline_work"))
        mo.AppendSeparator()
        self.mi_offline_sync = mo.Append(wx.ID_ANY, tr("menu_offline_sync"))
        self.mi_offline_sync.Enable(False)  # nur verfügbar wenn offline
        mf.AppendSubMenu(mo, tr("menu_file_offline"))
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

        # ---- Spalten anzeigen (Untermenü) ----
        mc = wx.Menu()
        def _col_item(label, checked=True):
            mi = mc.AppendCheckItem(wx.ID_ANY, label)
            mi.Check(checked); return mi
        self.mi_col_flag    = _col_item(tr("menu_view_col_flag"),    True)
        self.mi_col_status  = _col_item(tr("menu_view_col_status"),  True)
        self.mi_col_from    = _col_item(tr("menu_view_col_from"),    True)
        self.mi_col_subject = _col_item(tr("menu_view_col_subject"), True)
        self.mi_col_date    = _col_item(tr("menu_view_col_date"),    True)
        self.mi_col_size    = _col_item(tr("menu_view_col_size"),    True)
        self.mi_col_attach  = _col_item(tr("menu_view_col_attach"),  True)
        mv.AppendSubMenu(mc, tr("menu_view_columns"))
        mv.AppendSeparator()

        # ---- Sortieren nach (Untermenü) ----
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
        # Neue Nachrichten abrufen – Untermenü
        mf2 = wx.Menu()
        self.mi_fetch_all = mf2.Append(wx.ID_ANY, tr("menu_accounts_fetch_all") + "\tShift+F5")
        self.mi_fetch_cur = mf2.Append(wx.ID_ANY, tr("menu_accounts_fetch_cur") + "\tF5")
        mac.AppendSubMenu(mf2, tr("menu_accounts_fetch_sub"))
        mac.AppendSeparator()
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
        self.Bind(wx.EVT_CLOSE,                        self._on_window_close)
        self.Bind(wx.EVT_MENU, self._on_reply,        self.mi_reply)
        self.Bind(wx.EVT_MENU, self._on_reply_all,    self.mi_reply_all)
        self.Bind(wx.EVT_MENU, self._on_forward,      self.mi_forward)
        self.Bind(wx.EVT_MENU, self._on_delete_mail,  self.mi_delete_mail)
        self.Bind(wx.EVT_MENU, lambda e: self._on_mark(True),  self.mi_mark_read)
        self.Bind(wx.EVT_MENU, lambda e: self._on_mark(False), self.mi_mark_unread)
        self.Bind(wx.EVT_MENU, self._on_flag,         self.mi_flag)
        self.Bind(wx.EVT_MENU, self._on_refresh,      self.mi_refresh)
        # Spalten ein/ausblenden
        for mi, col_name in [
            (self.mi_col_flag,    "flag"),
            (self.mi_col_status,  "status"),
            (self.mi_col_from,    "from"),
            (self.mi_col_subject, "subject"),
            (self.mi_col_date,    "date"),
            (self.mi_col_size,    "size"),
            (self.mi_col_attach,  "attach"),
        ]:
            self.Bind(wx.EVT_MENU,
                      lambda e, c=col_name: self._on_col_toggle(c), mi)
        self.Bind(wx.EVT_MENU, self._on_new_account,  self.mi_new_account)
        self.Bind(wx.EVT_MENU, self._on_edit_account, self.mi_edit_account)
        self.Bind(wx.EVT_MENU, self._on_del_account,  self.mi_del_account)
        self.Bind(wx.EVT_MENU, self._on_fetch_all,    self.mi_fetch_all)
        self.Bind(wx.EVT_MENU, self._on_fetch_cur,    self.mi_fetch_cur)
        self.Bind(wx.EVT_MENU, self._on_empty_trash,  self.mi_empty_trash)
        self.Bind(wx.EVT_MENU, self._on_offline_toggle, self.mi_offline_work)
        self.Bind(wx.EVT_MENU, self._on_offline_sync,   self.mi_offline_sync)
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
        # Ausgewählte Mail persistent speichern (pro Ordner)
        if self._selected_folder_id:
            self.controller.set_setting(f"last_mail_{self._selected_folder_id}", str(mail_id))
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
        fid  = self._selected_folder_id
        mail = self.controller.get_mail(self._selected_mail_id, fid)
        if mail:
            new_flagged = not bool(mail["is_flagged"])
            self.controller.mark_mail_flagged(self._selected_mail_id, new_flagged, folder_id=fid)
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
        self.mail_list_panel._render_list()
        self.mail_list_panel._update_sort_header()
        self._save_sort_settings(sort_key, self.mi_sort_asc.IsChecked())

    def _on_sort_direction(self):
        """Richtungswechsel ohne Feldwechsel."""
        self.mail_list_panel._sort_asc = self.mi_sort_asc.IsChecked()
        self.mail_list_panel._apply_sort_to_data()
        self.mail_list_panel._render_list()
        self.mail_list_panel._update_sort_header()
        for key, mi in self._sort_items.items():
            if mi.IsChecked():
                self._save_sort_settings(key, self.mi_sort_asc.IsChecked())
                break

    def _save_sort_settings(self, sort_key: str, asc: bool):
        self.controller.set_setting("sort_field", sort_key)
        self.controller.set_setting("sort_asc",   "1" if asc else "0")

    def _restore_sort_settings(self):
        """Sortierung aus DB wiederherstellen."""
        from ui.mail_list_panel import COL_DATE, COL_FROM, COL_SUBJECT, COL_SIZE, COL_READ, COL_FLAG
        col_map = {"date": COL_DATE,"from": COL_FROM,"subject": COL_SUBJECT,
                   "size": COL_SIZE,"status": COL_READ,"flag": COL_FLAG,"attach": COL_SUBJECT}
        sort_key = self.controller.get_setting("sort_field", "date")
        sort_asc = self.controller.get_setting("sort_asc", "0") == "1"
        # Menü-RadioItems setzen
        if sort_key in self._sort_items:
            self._sort_items[sort_key].Check(True)
        if sort_asc:
            self.mi_sort_asc.Check(True)
        else:
            self.mi_sort_desc.Check(True)
        self.mail_list_panel._sort_col = col_map.get(sort_key, COL_DATE)
        self.mail_list_panel._sort_asc = sort_asc

    def _on_col_toggle(self, col_name: str):
        """Spalte ein- oder ausblenden."""
        from ui.mail_list_panel import COL_FLAG, COL_READ, COL_FROM, COL_SUBJECT, COL_DATE, COL_SIZE
        col_map = {
            "flag":    COL_FLAG,    "status":  COL_READ,
            "from":    COL_FROM,    "subject": COL_SUBJECT,
            "date":    COL_DATE,    "size":    COL_SIZE,
            "attach":  COL_SUBJECT,
        }
        mi_map = {
            "flag":    self.mi_col_flag,   "status":  self.mi_col_status,
            "from":    self.mi_col_from,   "subject": self.mi_col_subject,
            "date":    self.mi_col_date,   "size":    self.mi_col_size,
            "attach":  self.mi_col_attach,
        }
        col_idx = col_map.get(col_name)
        if col_idx is None: return
        visible = mi_map[col_name].IsChecked()
        lc = self.mail_list_panel.list_ctrl
        if visible:
            # Standardbreite wiederherstellen
            widths = {COL_FLAG: 24, COL_READ: 60, COL_FROM: 180,
                      COL_SUBJECT: 300, COL_DATE: 110, COL_SIZE: 65}
            lc.SetColumnWidth(col_idx, widths.get(col_idx, 100))
        else:
            lc.SetColumnWidth(col_idx, 0)

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
            # Neues Konto direkt herunterladen
            accs = self.controller.get_accounts()
            if accs:
                new_acc = dict(accs[-1])  # zuletzt hinzugefügt
                proto   = new_acc.get("protocol", "LOCAL")
                if proto not in ("LOCAL",) and new_acc.get("in_host"):
                    if wx.MessageBox(
                        tr("fetch_new_account_now", name=new_acc["name"]),
                        tr("hint_title"),
                        wx.YES_NO | wx.YES_DEFAULT, self
                    ) == wx.YES:
                        self._run_fetch(account_id=new_acc["id"])
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

    def _run_fetch(self, account_id: int = None):
        """Gemeinsame Fetch-Logik für Alle/Aktuelles Konto."""
        if getattr(self, "_is_offline", False):
            wx.MessageBox(tr("offline_mode_on"), tr("hint_title"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        accs = [a for a in self.controller.get_accounts()
                if dict(a).get("protocol", "LOCAL") != "LOCAL"]
        if account_id:
            accs = [a for a in accs if dict(a)["id"] == account_id]
        if not accs:
            wx.MessageBox(tr("imap_no_account"), tr("hint_title"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        self.status_bar.SetStatusText(tr("fetch_running"), 0)
        self.mi_fetch_all.Enable(False)
        self.mi_fetch_cur.Enable(False)

        from core.protocol_runner import ProtocolWorker
        import functools

        fn = functools.partial(self.controller.fetch_new_mails,
                               account_id=account_id)

        def _done(count):
            self.mi_fetch_all.Enable(True)
            self.mi_fetch_cur.Enable(True)
            self._hide_gauge()
            self.status_bar.SetStatusText(tr("imap_fetch_ok", count=count), 0)
            self.folder_panel.reload()
            if self._selected_folder_id:
                saved_mail_id = self._selected_mail_id
                mails = self.controller.get_mails(self._selected_folder_id)
                self.mail_list_panel.load_mails(mails)
                self.folder_panel.refresh_folder_unread(self._selected_folder_id)
                if saved_mail_id:
                    wx.CallAfter(self.mail_list_panel.select_mail_by_id, saved_mail_id)
            if not self._selected_folder_id:
                self._restore_last_folder()

        def _error(msg, is_auth):
            self.mi_fetch_all.Enable(True)
            self.mi_fetch_cur.Enable(True)
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

        ProtocolWorker(fn=fn, on_progress=_progress,
                       on_done=_done, on_error=_error).start()

    def _on_fetch_all(self, event):
        """Alle Konten abrufen (Shift+F5)."""
        self._run_fetch(account_id=None)

    def _on_fetch_cur(self, event):
        """Aktuelles Konto abrufen (F5)."""
        # Aktuelles Konto aus dem ausgewählten Ordner ermitteln
        acc_id = None
        if self._selected_mailbox_id:
            sc  = self.controller.db._get_structure_conn()
            row = sc.execute(
                "SELECT account_id FROM mailboxes WHERE id=?",
                (self._selected_mailbox_id,)
            ).fetchone()
            if row: acc_id = row[0]
        self._run_fetch(account_id=acc_id)

    def _on_empty_trash(self, event):
        """Papierkorb leeren – alle Mails endgültig löschen."""
        if wx.MessageBox(tr("empty_trash_confirm"), tr("menu_file_empty_trash"),
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) != wx.YES:
            return
        count = 0
        for mb in self.controller.get_mailboxes():
            for f in self.controller.get_folders(mb["id"]):
                if dict(f).get("folder_type") == "trash":
                    fid   = f["id"]
                    mails = self.controller.get_mails(fid)
                    for m in mails:
                        self.controller.db.delete_mail(dict(m)["id"], fid)
                        count += 1
                    self.controller.db.update_folder_unread(fid)
        wx.MessageBox(tr("empty_trash_done", count=count),
                      tr("hint_title"), wx.OK, self)
        self.folder_panel.reload()
        if self._selected_folder_id:
            mails = self.controller.get_mails(self._selected_folder_id)
            self.mail_list_panel.load_mails(mails)

    def _on_offline_toggle(self, event):
        """Offline-Modus umschalten."""
        self._is_offline = self.mi_offline_work.IsChecked()
        self.mi_offline_sync.Enable(self._is_offline)
        msg = tr("offline_mode_on") if self._is_offline else tr("offline_mode_off")
        self.status_bar.SetStatusText(msg, 0)
        self.controller.set_setting("offline_mode", "1" if self._is_offline else "0")

    def _on_offline_sync(self, event):
        """Im Offline-Modus: jetzt synchronisieren – mit Statusbar + Gauge."""
        # Offline-Modus temporär deaktivieren damit _run_fetch nicht abbricht
        self._is_offline = False
        self.mi_offline_work.Check(False)
        self.mi_offline_sync.Enable(False)
        self.controller.set_setting("offline_mode", "0")
        self.status_bar.SetStatusText(tr("fetch_running"), 0)
        self._run_fetch()   # nutzt ProtocolWorker mit Gauge + Prozentanzeige



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
        dlg = SettingsDialog(self, self.controller)
        dlg.ShowModal()
        dlg.Destroy()
        # Auto-Fetch neu starten falls Einstellungen geändert
        self._start_auto_fetch()

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

    def _on_window_close(self, event):
        """Auto-Fetch-Threads sauber beenden bevor das Fenster geschlossen wird."""
        self._auto_fetch.stop_all()
        event.Skip()  # normales Schließen fortsetzen

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
        """Kopiert eine Mail in einen anderen Ordner – inkl. IMAP-Server-Sync."""
        if not mail_id or target_folder_id == source_folder_id:
            return
        self.controller.copy_mail(mail_id, target_folder_id, source_folder_id)
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
        """Stellt den zuletzt ausgewählten Ordner wieder her."""
        self._restore_sort_settings()

        last_id = self.controller.get_setting("last_folder_id", "")
        if last_id:
            try:
                self.folder_panel.select_folder_by_id(int(last_id))
                wx.CallAfter(self._restore_last_mail, int(last_id))
            except (ValueError, Exception):
                pass
        else:
            for mb in self.controller.get_mailboxes():
                for f in self.controller.get_folders(mb["id"]):
                    if dict(f).get("folder_type") == "inbox":
                        self.folder_panel.select_folder_by_id(f["id"])
                        wx.CallAfter(self._restore_last_mail, f["id"])
                        break

        # Auto-Fetch starten wenn aktiviert
        wx.CallAfter(self._start_auto_fetch)

    def _start_auto_fetch(self):
        """Startet/stoppt Auto-Fetch-Threads nach aktuellen Einstellungen."""
        enabled  = self.controller.get_setting("auto_fetch", "0") == "1"
        interval = int(self.controller.get_setting("fetch_interval", "10"))
        if enabled and not getattr(self, "_is_offline", False):
            self._auto_fetch.start(
                controller=self.controller,
                interval_min=interval,
                on_new_mails=self._on_auto_fetch_done,
            )
        else:
            self._auto_fetch.stop_all()

    def _on_auto_fetch_done(self, count: int):
        """
        Wird nach erfolgreichem Auto-Fetch im Haupt-Thread aufgerufen.

        FIX: Speichert den aktuell fokussierten Mail-Index VOR dem Neuladen
        und stellt ihn NACH dem Neuladen wieder her, damit der Fokus nicht
        verloren geht wenn neue Mails eintreffen.
        """
        self.status_bar.SetStatusText(tr("imap_fetch_ok", count=count), 0)
        self.folder_panel.reload()
        if self._selected_folder_id:
            # Fokus sichern
            saved_mail_id = self._selected_mail_id
            mails = self.controller.get_mails(self._selected_folder_id)
            self.mail_list_panel.load_mails(mails)
            self.folder_panel.refresh_folder_unread(self._selected_folder_id)
            # Fokus wiederherstellen
            if saved_mail_id:
                wx.CallAfter(self.mail_list_panel.select_mail_by_id, saved_mail_id)

    def _restore_last_mail(self, folder_id: int):
        """Wählt die zuletzt fokussierte Mail im Ordner wieder aus."""
        last_mail_id = self.controller.get_setting(f"last_mail_{folder_id}", "")
        if not last_mail_id:
            return
        try:
            self.mail_list_panel.select_mail_by_id(int(last_mail_id))
        except Exception:
            pass

    def set_status(self, text: str, pane: int = 0):
        self.status_bar.SetStatusText(text, pane)
