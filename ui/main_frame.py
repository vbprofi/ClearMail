"""
MainFrame – Hauptfenster des MailClients (MVC-View)
Outlook-Express/Thunderbird-ähnliches Layout:
  Links:  Postfach-/Ordner-Baumstruktur
  Rechts: Oben Mail-Liste, unten Mail-Vorschau
"""

import wx
import wx.adv

from ui.folder_panel import FolderPanel
from ui.mail_list_panel import MailListPanel
from ui.mail_preview_panel import MailPreviewPanel
from ui.dialogs import (
    AccountDialog, SettingsDialog, PrintPreviewDialog,
    PGPDialog, AddonManagerDialog, AboutDialog, ComposeDialog
)


class MainFrame(wx.Frame):
    """Hauptfenster"""

    def __init__(self, parent, title: str, controller):
        super().__init__(
            parent,
            title=title,
            size=(1024, 700),
            style=wx.DEFAULT_FRAME_STYLE
        )
        self.controller = controller
        controller.view = self

        self._selected_folder_id = None
        self._selected_mail_id = None

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
        menu_bar = wx.MenuBar()

        # Datei
        m_file = wx.Menu()
        self.mi_new_mail    = m_file.Append(wx.ID_NEW,     "&Neue E-Mail\tCtrl+N",   "Neue E-Mail verfassen")
        m_file.AppendSeparator()
        self.mi_open_email  = m_file.Append(wx.ID_OPEN,   "&Öffnen (.email)\tCtrl+O", "E-Mail-Datei öffnen")
        self.mi_save_email  = m_file.Append(wx.ID_SAVE,   "&Speichern (.email)\tCtrl+S", "Als .email speichern")
        self.mi_save_txt    = m_file.Append(wx.ID_ANY,    "Speichern als .&txt",     "Als Textdatei speichern")
        m_file.AppendSeparator()
        self.mi_print       = m_file.Append(wx.ID_PRINT,  "&Drucken\tCtrl+P",        "Druckansicht")
        m_file.AppendSeparator()
        self.mi_exit        = m_file.Append(wx.ID_EXIT,   "&Beenden\tAlt+F4",        "Anwendung beenden")
        menu_bar.Append(m_file, "&Datei")

        # Bearbeiten
        m_edit = wx.Menu()
        self.mi_select_all  = m_edit.Append(wx.ID_SELECTALL, "Alles &markieren\tCtrl+A")
        self.mi_copy        = m_edit.Append(wx.ID_COPY,      "&Kopieren\tCtrl+C")
        m_edit.AppendSeparator()
        self.mi_find        = m_edit.Append(wx.ID_FIND,      "&Suchen\tCtrl+F", "In Mails suchen")
        menu_bar.Append(m_edit, "&Bearbeiten")

        # Ansicht
        m_view = wx.Menu()
        self.mi_refresh     = m_view.Append(wx.ID_REFRESH, "A&ktualisieren\tF5", "Ordner aktualisieren")
        m_view.AppendSeparator()
        self.mi_col_date    = m_view.AppendCheckItem(wx.ID_ANY, "&Datum anzeigen")
        self.mi_col_date.Check(True)
        self.mi_col_size    = m_view.AppendCheckItem(wx.ID_ANY, "&Größe anzeigen")
        self.mi_col_size.Check(True)
        menu_bar.Append(m_view, "&Ansicht")

        # Mail
        m_mail = wx.Menu()
        self.mi_reply       = m_mail.Append(wx.ID_ANY, "&Antworten\tCtrl+R",       "Auf Mail antworten")
        self.mi_reply_all   = m_mail.Append(wx.ID_ANY, "Allen &antworten\tCtrl+Shift+R")
        self.mi_forward     = m_mail.Append(wx.ID_ANY, "&Weiterleiten\tCtrl+L")
        m_mail.AppendSeparator()
        self.mi_delete_mail = m_mail.Append(wx.ID_DELETE, "&Löschen\tEntf",        "Mail löschen")
        self.mi_mark_read   = m_mail.Append(wx.ID_ANY,   "Als &gelesen markieren")
        self.mi_mark_unread = m_mail.Append(wx.ID_ANY,   "Als &ungelesen markieren")
        self.mi_flag        = m_mail.Append(wx.ID_ANY,   "Markierung &setzen/entfernen")
        menu_bar.Append(m_mail, "&Mail")

        # Konten
        m_accounts = wx.Menu()
        self.mi_new_account = m_accounts.Append(wx.ID_ANY, "&Neues Konto...", "E-Mail-Konto hinzufügen")
        self.mi_edit_account= m_accounts.Append(wx.ID_ANY, "Konto &bearbeiten...")
        self.mi_del_account = m_accounts.Append(wx.ID_ANY, "Konto &löschen")
        m_accounts.AppendSeparator()
        self.mi_fetch       = m_accounts.Append(wx.ID_ANY, "&E-Mails abrufen\tF9")
        menu_bar.Append(m_accounts, "&Konten")

        # Extras
        m_extras = wx.Menu()
        self.mi_settings    = m_extras.Append(wx.ID_PREFERENCES, "&Einstellungen...\tCtrl+,")
        self.mi_pgp         = m_extras.Append(wx.ID_ANY, "&OpenPGP-Schlüssel...")
        self.mi_addons      = m_extras.Append(wx.ID_ANY, "&Addon-Verwaltung...")
        menu_bar.Append(m_extras, "&Extras")

        # Hilfe
        m_help = wx.Menu()
        self.mi_about       = m_help.Append(wx.ID_ABOUT, "&Über MailClient...")
        menu_bar.Append(m_help, "&Hilfe")

        self.SetMenuBar(menu_bar)

    # ------------------------------------------------------------------ #
    #  Statusleiste                                                       #
    # ------------------------------------------------------------------ #

    def _build_status_bar(self):
        self.status_bar = self.CreateStatusBar(3)
        self.status_bar.SetStatusWidths([-3, -1, -1])
        self.status_bar.SetStatusText("Bereit", 0)
        self.status_bar.SetStatusText("0 Nachrichten", 1)
        self.status_bar.SetStatusText("", 2)
        self.status_bar.SetName("Statusleiste")

    # ------------------------------------------------------------------ #
    #  Layout                                                             #
    # ------------------------------------------------------------------ #

    def _build_layout(self):
        # Haupt-Splitter: links Ordnerstruktur, rechts Inhalt
        self.main_splitter = wx.SplitterWindow(
            self, style=wx.SP_LIVE_UPDATE | wx.SP_3D
        )
        self.main_splitter.SetMinimumPaneSize(160)
        self.main_splitter.SetName("Haupt-Teiler")

        # Linke Seite: Ordner-Panel
        self.folder_panel = FolderPanel(self.main_splitter, self.controller)
        self.folder_panel.SetName("Ordnerbereich")

        # Rechte Seite: vertikaler Splitter
        self.right_splitter = wx.SplitterWindow(
            self.main_splitter, style=wx.SP_LIVE_UPDATE | wx.SP_3D
        )
        self.right_splitter.SetMinimumPaneSize(80)
        self.right_splitter.SetName("Inhalts-Teiler")

        # Mail-Liste
        self.mail_list_panel = MailListPanel(self.right_splitter, self.controller)
        self.mail_list_panel.SetName("Mail-Liste")

        # Mail-Vorschau
        self.mail_preview_panel = MailPreviewPanel(self.right_splitter, self.controller)
        self.mail_preview_panel.SetName("Mail-Vorschau")

        self.right_splitter.SplitHorizontally(
            self.mail_list_panel, self.mail_preview_panel, 280
        )

        self.main_splitter.SplitVertically(
            self.folder_panel, self.right_splitter, 220
        )

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.main_splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)

    # ------------------------------------------------------------------ #
    #  Events                                                             #
    # ------------------------------------------------------------------ #

    def _bind_events(self):
        # Tastatur
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)

        # Datei-Menü
        self.Bind(wx.EVT_MENU, self._on_new_mail,     self.mi_new_mail)
        self.Bind(wx.EVT_MENU, self._on_open_email,   self.mi_open_email)
        self.Bind(wx.EVT_MENU, self._on_save_email,   self.mi_save_email)
        self.Bind(wx.EVT_MENU, self._on_save_txt,     self.mi_save_txt)
        self.Bind(wx.EVT_MENU, self._on_print,        self.mi_print)
        self.Bind(wx.EVT_MENU, self._on_exit,         self.mi_exit)

        # Mail-Menü
        self.Bind(wx.EVT_MENU, self._on_reply,        self.mi_reply)
        self.Bind(wx.EVT_MENU, self._on_reply_all,    self.mi_reply_all)
        self.Bind(wx.EVT_MENU, self._on_forward,      self.mi_forward)
        self.Bind(wx.EVT_MENU, self._on_delete_mail,  self.mi_delete_mail)
        self.Bind(wx.EVT_MENU, lambda e: self._on_mark(True),  self.mi_mark_read)
        self.Bind(wx.EVT_MENU, lambda e: self._on_mark(False), self.mi_mark_unread)
        self.Bind(wx.EVT_MENU, self._on_flag,         self.mi_flag)

        # Ansicht
        self.Bind(wx.EVT_MENU, self._on_refresh,      self.mi_refresh)

        # Konten
        self.Bind(wx.EVT_MENU, self._on_new_account,  self.mi_new_account)
        self.Bind(wx.EVT_MENU, self._on_edit_account, self.mi_edit_account)
        self.Bind(wx.EVT_MENU, self._on_del_account,  self.mi_del_account)
        self.Bind(wx.EVT_MENU, self._on_fetch,        self.mi_fetch)

        # Extras
        self.Bind(wx.EVT_MENU, self._on_settings,     self.mi_settings)
        self.Bind(wx.EVT_MENU, self._on_pgp,          self.mi_pgp)
        self.Bind(wx.EVT_MENU, self._on_addons,       self.mi_addons)

        # Hilfe
        self.Bind(wx.EVT_MENU, self._on_about,        self.mi_about)

        # Callbacks von Panels
        self.folder_panel.on_folder_selected = self._on_folder_selected
        self.mail_list_panel.on_mail_selected = self._on_mail_selected
        self.mail_list_panel.on_mail_delete   = self._on_delete_mail
        self.mail_list_panel.on_context_menu  = self._show_mail_context_menu

    def _set_initial_accessibility(self):
        """Setzt Accessible-Namen für Screenreader."""
        self.SetName("MailClient Hauptfenster")
        self.folder_panel.tree.SetName("Postfächer und Ordner")

    # ------------------------------------------------------------------ #
    #  F6 / Shift+F6 – Fokusnavigation                                   #
    # ------------------------------------------------------------------ #

    def _on_key_down(self, event: wx.KeyEvent):
        key  = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()

        if key == wx.WXK_F6:
            if shift:
                self._focus_prev_panel()
            else:
                self._focus_next_panel()
            return
        event.Skip()

    _panels_order = ["folder", "list", "preview"]

    def _focus_next_panel(self):
        current = self._current_focus_panel()
        order   = self._panels_order
        idx     = (order.index(current) + 1) % len(order) if current in order else 0
        self._focus_panel(order[idx])

    def _focus_prev_panel(self):
        current = self._current_focus_panel()
        order   = self._panels_order
        idx     = (order.index(current) - 1) % len(order) if current in order else 0
        self._focus_panel(order[idx])

    def _current_focus_panel(self) -> str:
        focused = self.FindFocus()
        if focused is None:
            return "folder"
        if self.folder_panel.IsAncestorOf(focused) or focused == self.folder_panel.tree:
            return "folder"
        if self.mail_list_panel.IsAncestorOf(focused):
            return "list"
        if self.mail_preview_panel.IsAncestorOf(focused):
            return "preview"
        return "folder"

    def _focus_panel(self, panel: str):
        if panel == "folder":
            self.folder_panel.tree.SetFocus()
            self.status_bar.SetStatusText("Fokus: Postfächer und Ordner", 2)
        elif panel == "list":
            self.mail_list_panel.list_ctrl.SetFocus()
            self.status_bar.SetStatusText("Fokus: Mail-Liste", 2)
        elif panel == "preview":
            self.mail_preview_panel.txt_body.SetFocus()
            self.status_bar.SetStatusText("Fokus: Mail-Vorschau", 2)

    # ------------------------------------------------------------------ #
    #  Callbacks von Panels                                               #
    # ------------------------------------------------------------------ #

    def _on_folder_selected(self, folder_id: int, folder_name: str):
        self._selected_folder_id = folder_id
        mails = self.controller.get_mails(folder_id)
        self.mail_list_panel.load_mails(mails)
        self.mail_preview_panel.clear()
        count = len(mails)
        self.status_bar.SetStatusText(f"Ordner: {folder_name}", 0)
        self.status_bar.SetStatusText(f"{count} Nachricht(en)", 1)
        self._selected_mail_id = None

    def _on_mail_selected(self, mail_id: int):
        self._selected_mail_id = mail_id
        mail = self.controller.get_mail(mail_id)
        if mail:
            self.mail_preview_panel.show_mail(dict(mail))
            self.mail_list_panel.refresh_mail_read(mail_id)
            # Ordner-Ungelesen-Zähler aktualisieren
            if self._selected_folder_id:
                self.folder_panel.refresh_folder_unread(self._selected_folder_id)

    # ------------------------------------------------------------------ #
    #  Mail-Aktionen                                                      #
    # ------------------------------------------------------------------ #

    def _on_new_mail(self, event):
        dlg = ComposeDialog(self, self.controller)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_reply(self, event):
        if not self._selected_mail_id:
            return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            dlg = ComposeDialog(self, self.controller, reply_to=dict(mail))
            dlg.ShowModal()
            dlg.Destroy()

    def _on_reply_all(self, event):
        if not self._selected_mail_id:
            return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            dlg = ComposeDialog(self, self.controller, reply_to=dict(mail), reply_all=True)
            dlg.ShowModal()
            dlg.Destroy()

    def _on_forward(self, event):
        if not self._selected_mail_id:
            return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            dlg = ComposeDialog(self, self.controller, forward=dict(mail))
            dlg.ShowModal()
            dlg.Destroy()

    def _on_delete_mail(self, event=None):
        if not self._selected_mail_id:
            return
        result = wx.MessageBox(
            "Diese E-Mail wirklich löschen?",
            "E-Mail löschen",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
            self
        )
        if result == wx.YES:
            self.controller.delete_mail(self._selected_mail_id, self._selected_folder_id)
            self.mail_list_panel.remove_mail(self._selected_mail_id)
            self.mail_preview_panel.clear()
            self._selected_mail_id = None
            if self._selected_folder_id:
                self.folder_panel.refresh_folder_unread(self._selected_folder_id)

    def _on_mark(self, is_read: bool):
        if self._selected_mail_id:
            self.controller.mark_mail_read(self._selected_mail_id, is_read)
            self.mail_list_panel.refresh_mail_read(self._selected_mail_id, force_read=is_read)

    def _on_flag(self, event):
        if self._selected_mail_id:
            mail = self.controller.get_mail(self._selected_mail_id)
            if mail:
                new_flag = not bool(mail["is_flagged"])
                self.controller.mark_mail_flagged(self._selected_mail_id, new_flag)
                self.mail_list_panel.reload_current_folder()

    def _on_refresh(self, event):
        if self._selected_folder_id:
            self._on_folder_selected(
                self._selected_folder_id,
                self.folder_panel.get_selected_folder_name()
            )

    # ------------------------------------------------------------------ #
    #  Datei-Aktionen                                                     #
    # ------------------------------------------------------------------ #

    def _on_open_email(self, event):
        with wx.FileDialog(
            self, "E-Mail-Datei öffnen",
            wildcard="E-Mail-Datei (*.email)|*.email",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                data = self.controller.open_email_file(dlg.GetPath())
                if data:
                    self.mail_preview_panel.show_mail(data)
                else:
                    wx.MessageBox("Datei konnte nicht geöffnet werden.", "Fehler", wx.OK | wx.ICON_ERROR, self)

    def _on_save_email(self, event):
        if not self._selected_mail_id:
            wx.MessageBox("Bitte zuerst eine E-Mail auswählen.", "Hinweis", wx.OK | wx.ICON_INFORMATION, self)
            return
        with wx.FileDialog(
            self, "E-Mail speichern",
            wildcard="E-Mail-Datei (*.email)|*.email",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                ok = self.controller.save_mail_as_email(self._selected_mail_id, dlg.GetPath())
                if not ok:
                    wx.MessageBox("Fehler beim Speichern.", "Fehler", wx.OK | wx.ICON_ERROR, self)

    def _on_save_txt(self, event):
        if not self._selected_mail_id:
            wx.MessageBox("Bitte zuerst eine E-Mail auswählen.", "Hinweis", wx.OK | wx.ICON_INFORMATION, self)
            return
        with wx.FileDialog(
            self, "Als Textdatei speichern",
            wildcard="Textdatei (*.txt)|*.txt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                ok = self.controller.save_mail_as_txt(self._selected_mail_id, dlg.GetPath())
                if not ok:
                    wx.MessageBox("Fehler beim Speichern.", "Fehler", wx.OK | wx.ICON_ERROR, self)

    def _on_print(self, event):
        if not self._selected_mail_id:
            return
        mail = self.controller.get_mail(self._selected_mail_id)
        if mail:
            dlg = PrintPreviewDialog(self, dict(mail))
            dlg.ShowModal()
            dlg.Destroy()

    # ------------------------------------------------------------------ #
    #  Konten                                                             #
    # ------------------------------------------------------------------ #

    def _on_new_account(self, event):
        dlg = AccountDialog(self, self.controller)
        if dlg.ShowModal() == wx.ID_OK:
            self.folder_panel.reload()
        dlg.Destroy()

    def _on_edit_account(self, event):
        accounts = self.controller.get_accounts()
        if not accounts:
            wx.MessageBox("Keine Konten vorhanden.", "Hinweis", wx.OK, self)
            return
        choices = [f"{a['name']} <{a['email']}>" for a in accounts]
        with wx.SingleChoiceDialog(self, "Konto auswählen:", "Konto bearbeiten", choices) as d:
            if d.ShowModal() == wx.ID_OK:
                acc = accounts[d.GetSelection()]
                dlg = AccountDialog(self, self.controller, account_id=acc["id"])
                dlg.ShowModal()
                dlg.Destroy()

    def _on_del_account(self, event):
        accounts = self.controller.get_accounts()
        if not accounts:
            return
        choices = [f"{a['name']} <{a['email']}>" for a in accounts]
        with wx.SingleChoiceDialog(self, "Konto löschen:", "Konto löschen", choices) as d:
            if d.ShowModal() == wx.ID_OK:
                acc = accounts[d.GetSelection()]
                if wx.MessageBox(f"Konto '{acc['name']}' wirklich löschen?", "Bestätigung",
                                 wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) == wx.YES:
                    self.controller.delete_account(acc["id"])

    def _on_fetch(self, event):
        wx.MessageBox(
            "E-Mail-Abruf noch nicht implementiert.\n\n"
            "Die IMAP/POP3-Protokollmodule können in protocols/ ergänzt werden.",
            "Protokoll nicht implementiert",
            wx.OK | wx.ICON_INFORMATION,
            self
        )

    # ------------------------------------------------------------------ #
    #  Extras / Sonstiges                                                 #
    # ------------------------------------------------------------------ #

    def _on_settings(self, event):
        dlg = SettingsDialog(self, self.controller)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_pgp(self, event):
        dlg = PGPDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_addons(self, event):
        dlg = AddonManagerDialog(self, self.controller)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_about(self, event):
        dlg = AboutDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_exit(self, event):
        self.Close()

    # ------------------------------------------------------------------ #
    #  Kontext-Menü (Mail-Liste)                                         #
    # ------------------------------------------------------------------ #

    def _show_mail_context_menu(self, event):
        menu = wx.Menu()

        item_open    = menu.Append(wx.ID_ANY, "Öffnen / Vorschau")
        item_reply   = menu.Append(wx.ID_ANY, "Antworten")
        item_forward = menu.Append(wx.ID_ANY, "Weiterleiten")
        menu.AppendSeparator()
        item_save_em = menu.Append(wx.ID_ANY, "Speichern als .email")
        item_save_tx = menu.Append(wx.ID_ANY, "Speichern als .txt")
        menu.AppendSeparator()
        item_read    = menu.Append(wx.ID_ANY, "Als gelesen markieren")
        item_unread  = menu.Append(wx.ID_ANY, "Als ungelesen markieren")
        item_flag    = menu.Append(wx.ID_ANY, "Markierung setzen/entfernen")
        menu.AppendSeparator()
        item_delete  = menu.Append(wx.ID_DELETE, "Löschen")

        self.Bind(wx.EVT_MENU, lambda e: self._on_mail_selected(self._selected_mail_id), item_open)
        self.Bind(wx.EVT_MENU, self._on_reply,       item_reply)
        self.Bind(wx.EVT_MENU, self._on_forward,     item_forward)
        self.Bind(wx.EVT_MENU, self._on_save_email,  item_save_em)
        self.Bind(wx.EVT_MENU, self._on_save_txt,    item_save_tx)
        self.Bind(wx.EVT_MENU, lambda e: self._on_mark(True),  item_read)
        self.Bind(wx.EVT_MENU, lambda e: self._on_mark(False), item_unread)
        self.Bind(wx.EVT_MENU, self._on_flag,        item_flag)
        self.Bind(wx.EVT_MENU, self._on_delete_mail, item_delete)

        # Addon-Menüeinträge anhängen
        for item_def in self.controller.addon_mgr.get_all_menu_items():
            mi = menu.Append(wx.ID_ANY, item_def["label"])
            self.Bind(wx.EVT_MENU, lambda e, h=item_def["handler"]: h(self._selected_mail_id), mi)

        self.PopupMenu(menu)
        menu.Destroy()

    # ------------------------------------------------------------------ #
    #  Öffentliche Update-Methoden (von Controller aufrufbar)            #
    # ------------------------------------------------------------------ #

    def set_status(self, text: str, pane: int = 0):
        self.status_bar.SetStatusText(text, pane)
