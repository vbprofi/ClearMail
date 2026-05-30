"""
MailListPanel – Mail-Liste. Vollständig i18n-fähig.
"""

import wx
from datetime import datetime
from core.i18n import tr


COL_FLAG    = 0
COL_READ    = 1
COL_FROM    = 2
COL_SUBJECT = 3
COL_DATE    = 4
COL_SIZE    = 5


class MailListPanel(wx.Panel):

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.on_mail_selected  = None
        self.on_mail_open      = None   # Doppelklick / Enter → eigenes Fenster
        self.on_mail_delete    = None
        self.on_context_menu   = None

        self._mail_data  = []
        self._mail_index = {}

        self._build_ui()
        self._bind_events()

    def _build_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(self, label=tr("mail_list_header"))
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 4)

        self.list_ctrl = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN | wx.LC_HRULES
        )
        self.list_ctrl.SetName(tr("mail_list_name"))
        self.list_ctrl.SetToolTip(tr("mail_list_tooltip"))

        self.list_ctrl.InsertColumn(COL_FLAG,    tr("mail_list_flag"),    width=24)
        self.list_ctrl.InsertColumn(COL_READ,    tr("mail_list_status"),  width=60)
        self.list_ctrl.InsertColumn(COL_FROM,    tr("mail_list_from"),    width=180)
        self.list_ctrl.InsertColumn(COL_SUBJECT, tr("mail_list_subject"), width=300)
        self.list_ctrl.InsertColumn(COL_DATE,    tr("mail_list_date"),    width=130)
        self.list_ctrl.InsertColumn(COL_SIZE,    tr("mail_list_size"),    width=70)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        self.SetSizer(sizer)

    def _bind_events(self):
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED,  self._on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)
        self.list_ctrl.Bind(wx.EVT_CHAR_HOOK,            self._on_key_down)
        self.list_ctrl.Bind(wx.EVT_CONTEXT_MENU,         self._on_context_menu)

    # ------------------------------------------------------------------ #
    #  Daten laden                                                        #
    # ------------------------------------------------------------------ #

    def load_mails(self, mails: list):
        self.list_ctrl.DeleteAllItems()
        self._mail_data  = [dict(m) for m in mails]
        self._mail_index = {}

        for row, mail in enumerate(self._mail_data):
            flag_str = "★" if mail.get("is_flagged") else ""
            idx = self.list_ctrl.InsertItem(row, flag_str)

            status = tr("mail_status_unread") if not mail.get("is_read") else tr("mail_status_read")
            self.list_ctrl.SetItem(idx, COL_READ, status)

            sender = str(mail.get("sender_name") or mail.get("sender") or "")
            self.list_ctrl.SetItem(idx, COL_FROM, sender)

            subject = str(mail.get("subject") or tr("preview_no_subject"))
            if mail.get("has_attach"):
                subject = "📎 " + subject
            self.list_ctrl.SetItem(idx, COL_SUBJECT, subject)

            self.list_ctrl.SetItem(idx, COL_DATE, self._format_date(str(mail.get("date") or "")))
            self.list_ctrl.SetItem(idx, COL_SIZE, self._format_size(mail.get("size") or 0))

            if not mail.get("is_read"):
                font = self.list_ctrl.GetFont()
                self.list_ctrl.SetItemFont(idx, font.Bold())

            self._mail_index[idx] = mail

        count = len(mails)
        self.list_ctrl.SetName(tr("mail_list_count", count=count))

    def reload_current_folder(self):
        parent = self.GetGrandParent()
        if parent and hasattr(parent, "_selected_folder_id") and parent._selected_folder_id:
            mails = self.controller.get_mails(parent._selected_folder_id)
            self.load_mails(mails)

    # ------------------------------------------------------------------ #
    #  Events                                                             #
    # ------------------------------------------------------------------ #

    def _on_item_selected(self, event):
        idx  = event.GetIndex()
        mail = self._mail_index.get(idx)
        if mail and self.on_mail_selected:
            self.on_mail_selected(mail["id"])

    def _on_item_activated(self, event):
        # Doppelklick / Enter → Mail in eigenem Fenster öffnen
        idx  = event.GetIndex()
        mail = self._mail_index.get(idx)
        if mail and self.on_mail_open:
            self.on_mail_open(mail["id"])
        else:
            self._on_item_selected(event)

    def _on_key_down(self, event: wx.KeyEvent):
        key = event.GetKeyCode()
        if key == wx.WXK_DELETE:
            if self.on_mail_delete:
                self.on_mail_delete(event)
            return  # kein Skip → verhindert dass ListCtrl etwas löscht
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            # Enter → Mail in eigenem Fenster öffnen (NICHT Tab ins Vorschau-Feld)
            idx  = self.list_ctrl.GetFirstSelected()
            mail = self._mail_index.get(idx)
            if mail and self.on_mail_open:
                self.on_mail_open(mail["id"])
            return  # kein Skip → kein Sprung zum nächsten Control
        if key == wx.WXK_TAB:
            # Tab → F6-Navigation (Weiterleitung an Frame)
            event.Skip()
            return
        event.Skip()

    def _on_context_menu(self, event):
        if self.on_context_menu:
            self.on_context_menu(event)

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    def refresh_mail_read(self, mail_id: int, force_read: bool = None):
        for idx, mail in self._mail_index.items():
            if mail["id"] == mail_id:
                is_read = force_read if force_read is not None else True
                mail["is_read"] = is_read
                self.list_ctrl.SetItem(idx, COL_READ,
                    tr("mail_status_read") if is_read else tr("mail_status_unread"))
                font = self.list_ctrl.GetFont()
                self.list_ctrl.SetItemFont(idx, font if is_read else font.Bold())
                break

    def remove_mail(self, mail_id: int):
        for idx, mail in list(self._mail_index.items()):
            if mail["id"] == mail_id:
                self.list_ctrl.DeleteItem(idx)
                del self._mail_index[idx]
                new_index = {}
                for i, m in self._mail_index.items():
                    new_index[i if i < idx else i - 1] = m
                self._mail_index = new_index
                break

    @staticmethod
    def _format_date(date_str: str) -> str:
        if not date_str:
            return ""
        try:
            dt  = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            if dt.date() == now.date():
                return dt.strftime("%H:%M")
            elif dt.year == now.year:
                return dt.strftime("%d.%m. %H:%M")
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            return date_str[:16]

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size // 1024} KB"
        return f"{size // (1024 * 1024)} MB"
