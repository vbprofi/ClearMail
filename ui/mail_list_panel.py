"""
MailListPanel – Obere rechte Seite: Liste der E-Mails eines Ordners
Screenreader-optimiert: Spaltenüberschriften, Tastennavigation
"""

import wx
from datetime import datetime


COL_FLAG    = 0
COL_READ    = 1
COL_FROM    = 2
COL_SUBJECT = 3
COL_DATE    = 4
COL_SIZE    = 5


class MailListPanel(wx.Panel):
    """Panel mit Mail-Liste als wx.ListCtrl (Report-Ansicht)."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.on_mail_selected  = None   # callback(mail_id)
        self.on_mail_delete    = None   # callback(event)
        self.on_context_menu   = None   # callback(event)

        self._mail_data  = []           # [dict, ...]  – aktuell angezeigte Mails
        self._mail_index = {}           # list_row -> mail dict

        self._build_ui()
        self._bind_events()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(self, label="Nachrichten")
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 4)

        self.list_ctrl = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN | wx.LC_HRULES
        )
        self.list_ctrl.SetName("Nachrichtenliste")
        self.list_ctrl.SetToolTip(
            "E-Mail-Liste. Pfeiltasten zum Navigieren. "
            "Enter oder Leertaste zum Öffnen. "
            "Entf zum Löschen. Kontextmenü mit Applikationstaste. "
            "F6 wechselt den Bereich."
        )

        self.list_ctrl.InsertColumn(COL_FLAG,    "!",       width=24)
        self.list_ctrl.InsertColumn(COL_READ,    "Status",  width=60)
        self.list_ctrl.InsertColumn(COL_FROM,    "Von",     width=180)
        self.list_ctrl.InsertColumn(COL_SUBJECT, "Betreff", width=300)
        self.list_ctrl.InsertColumn(COL_DATE,    "Datum",   width=130)
        self.list_ctrl.InsertColumn(COL_SIZE,    "Größe",   width=70)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        self.SetSizer(sizer)

    def _bind_events(self):
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED,   self._on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED,  self._on_item_activated)
        self.list_ctrl.Bind(wx.EVT_KEY_DOWN,              self._on_key_down)
        self.list_ctrl.Bind(wx.EVT_CONTEXT_MENU,          self._on_context_menu)

    # ------------------------------------------------------------------ #
    #  Daten laden                                                        #
    # ------------------------------------------------------------------ #

    def load_mails(self, mails: list):
        self.list_ctrl.DeleteAllItems()
        self._mail_data  = [dict(m) for m in mails]
        self._mail_index = {}

        for row, mail in enumerate(self._mail_data):
            # Markierungs-Spalte
            flag_str = "★" if mail.get("is_flagged") else ""
            idx = self.list_ctrl.InsertItem(row, flag_str)

            # Status
            status = "Ungelesen" if not mail.get("is_read") else "Gelesen"
            self.list_ctrl.SetItem(idx, COL_READ, status)

            # Absender – None-sicher
            sender = str(mail.get("sender_name") or mail.get("sender") or "")
            self.list_ctrl.SetItem(idx, COL_FROM, sender)

            # Betreff – None-sicher
            subject = str(mail.get("subject") or "(kein Betreff)")
            if mail.get("has_attach"):
                subject = "📎 " + subject
            self.list_ctrl.SetItem(idx, COL_SUBJECT, subject)

            # Datum – None-sicher
            date_str = self._format_date(str(mail.get("date") or ""))
            self.list_ctrl.SetItem(idx, COL_DATE, date_str)

            # Größe
            size_str = self._format_size(mail.get("size") or 0)
            self.list_ctrl.SetItem(idx, COL_SIZE, size_str)

            # Fett für ungelesene Mails
            if not mail.get("is_read"):
                font = self.list_ctrl.GetItemFont(idx)
                if not font.IsOk():
                    font = self.list_ctrl.GetFont()
                bold_font = font.Bold()
                self.list_ctrl.SetItemFont(idx, bold_font)

            self._mail_index[idx] = mail

        # Screenreader: Anzahl melden
        count = len(mails)
        self.list_ctrl.SetName(f"Nachrichtenliste, {count} Nachricht(en)")

    def reload_current_folder(self):
        """Aktuell angezeigte Mails neu laden (nach Flag-Änderung etc.)."""
        # Nur Neuladen wenn ein Ordner selektiert ist
        parent = self.GetGrandParent()
        if parent and hasattr(parent, "_selected_folder_id") and parent._selected_folder_id:
            mails = self.controller.get_mails(parent._selected_folder_id)
            self.load_mails(mails)

    # ------------------------------------------------------------------ #
    #  Event-Handler                                                      #
    # ------------------------------------------------------------------ #

    def _on_item_selected(self, event):
        idx = event.GetIndex()
        mail = self._mail_index.get(idx)
        if mail and self.on_mail_selected:
            self.on_mail_selected(mail["id"])

    def _on_item_activated(self, event):
        self._on_item_selected(event)

    def _on_key_down(self, event: wx.KeyEvent):
        key = event.GetKeyCode()
        if key == wx.WXK_DELETE:
            if self.on_mail_delete:
                self.on_mail_delete(event)
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
                status = "Gelesen" if is_read else "Ungelesen"
                self.list_ctrl.SetItem(idx, COL_READ, status)
                # Fett entfernen/setzen
                font = self.list_ctrl.GetFont()
                if is_read:
                    self.list_ctrl.SetItemFont(idx, font)
                else:
                    self.list_ctrl.SetItemFont(idx, font.Bold())
                break

    def remove_mail(self, mail_id: int):
        for idx, mail in list(self._mail_index.items()):
            if mail["id"] == mail_id:
                self.list_ctrl.DeleteItem(idx)
                del self._mail_index[idx]
                # Index neu aufbauen
                new_index = {}
                for i, m in self._mail_index.items():
                    new_i = i if i < idx else i - 1
                    new_index[new_i] = m
                self._mail_index = new_index
                break

    @staticmethod
    def _format_date(date_str: str) -> str:
        if not date_str:
            return ""
        try:
            dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            if dt.date() == now.date():
                return dt.strftime("%H:%M")
            elif dt.year == now.year:
                return dt.strftime("%d.%m. %H:%M")
            else:
                return dt.strftime("%d.%m.%Y")
        except ValueError:
            return date_str[:16]

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size // 1024} KB"
        else:
            return f"{size // (1024*1024)} MB"
