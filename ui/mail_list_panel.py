"""
MailListPanel – Mail-Liste. Vollständig i18n-fähig.

Korrekturen (2026-05):
  - EVT_LIST_COL_CLICK implementiert: Klick auf Spaltenheader sortiert die Liste
    und zeigt einen Sortierpfeil (▲/▼) im Spaltentitel.
  - _mail_index nutzt jetzt die Mail-ID als Schlüssel (statt dem wxListCtrl-Index
    der sich beim Sortieren/Löschen verschiebt) → kein Speicherfehler mehr beim
    Löschen nach einer Sortier-Operation (remove_mail war O(n) + falsche Indizes).
  - refresh_mail_read() und remove_mail() suchen über ID, nicht über list-Index.
  - _rebuild_from_sorted_data() konsolidiert mit load_mails() (kein doppelter Code).
  - Sortier-Pfeil im Spaltenheader via SetColumnInfo (portabel).
"""

import wx
from datetime import datetime
from core.i18n import tr
from core.date_utils import format_date_list


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
        self.on_mail_open      = None
        self.on_mail_delete    = None
        self.on_context_menu   = None

        # Daten-Store: mail_id → mail-dict  (statt listctrl-row → mail-dict)
        # Verhindert Index-Drift nach Sortierung/Löschen
        self._mail_data:  list  = []          # sortierte Reihenfolge
        self._id_to_mail: dict  = {}          # mail_id → mail-dict (O(1)-Lookup)
        self._row_to_id:  dict  = {}          # listctrl-row → mail_id

        self._sort_col: int  = COL_DATE
        self._sort_asc: bool = False

        self._build_ui()
        self._bind_events()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

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

        # Initialen Sortierpfeil setzen
        self._update_sort_header()

    def _bind_events(self):
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED,  self._on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)
        self.list_ctrl.Bind(wx.EVT_CHAR_HOOK,            self._on_key_down)
        self.list_ctrl.Bind(wx.EVT_CONTEXT_MENU,         self._on_context_menu)
        # FIX: Klick auf Spaltenheader → Sortierung
        self.list_ctrl.Bind(wx.EVT_LIST_COL_CLICK,       self._on_col_click)

    # ------------------------------------------------------------------ #
    #  Daten laden                                                        #
    # ------------------------------------------------------------------ #

    def load_mails(self, mails: list):
        self._mail_data  = [dict(m) for m in mails]
        self._id_to_mail = {m["id"]: m for m in self._mail_data if "id" in m}

        self._apply_sort_to_data()
        self._render_list()

        self.list_ctrl.SetName(tr("mail_list_count", count=len(mails)))

    def _apply_sort_to_data(self):
        """Sortiert self._mail_data nach aktuellem Sortierfeld."""
        col = self._sort_col
        asc = self._sort_asc

        def _key(m):
            if col == COL_DATE:    return str(m.get("date") or "")
            if col == COL_FROM:    return (str(m.get("sender_name") or m.get("sender") or "")).lower()
            if col == COL_SUBJECT: return str(m.get("subject") or "").lower()
            if col == COL_SIZE:    return int(m.get("size") or 0)
            if col == COL_READ:    return int(m.get("is_read") or 0)
            if col == COL_FLAG:    return int(m.get("is_flagged") or 0)
            return str(m.get("date") or "")

        self._mail_data.sort(key=_key, reverse=not asc)

    def _render_list(self):
        """
        Rendert self._mail_data in das ListCtrl. Baut _row_to_id neu auf.
        Freeze/Thaw verhindert Flimmern bei großen Listen.
        """
        lc   = self.list_ctrl
        font = lc.GetFont()
        bold = font.Bold()

        lc.Freeze()
        try:
            lc.DeleteAllItems()
            self._row_to_id = {}
            for row, mail in enumerate(self._mail_data):
                mail_id  = mail.get("id")
                flag_str = "★" if mail.get("is_flagged") else ""
                idx      = lc.InsertItem(row, flag_str)

                status = tr("mail_status_unread") if not mail.get("is_read") else tr("mail_status_read")
                lc.SetItem(idx, COL_READ, status)
                lc.SetItem(idx, COL_FROM, str(mail.get("sender_name") or mail.get("sender") or ""))

                subject = str(mail.get("subject") or tr("preview_no_subject"))
                if mail.get("has_attach"):
                    subject = "📎 " + subject
                lc.SetItem(idx, COL_SUBJECT, subject)
                lc.SetItem(idx, COL_DATE, self._format_date(str(mail.get("date") or "")))
                lc.SetItem(idx, COL_SIZE, self._format_size(mail.get("size") or 0))

                if not mail.get("is_read"):
                    lc.SetItemFont(idx, bold)

                if mail_id is not None:
                    self._row_to_id[idx] = mail_id
        finally:
            lc.Thaw()

    # ------------------------------------------------------------------ #
    #  Spalten-Sortierung                                                 #
    # ------------------------------------------------------------------ #

    def _on_col_click(self, event: wx.ListEvent):
        """
        FIX: Klick auf Spaltenheader wechselt Sortierung.
        Gleiche Spalte → Richtung umkehren. Neue Spalte → absteigende Richtung.
        """
        col = event.GetColumn()
        if col == self._sort_col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            # Datum/Größe/Flags: absteigende Vorsortierung ist intuitiver
            self._sort_asc = col in (COL_FROM, COL_SUBJECT)

        self._apply_sort_to_data()
        self._render_list()
        self._update_sort_header()

    def _update_sort_header(self):
        """Zeigt Sortierpfeil (▲/▼) im aktiven Spaltenheader."""
        col_labels = {
            COL_FLAG:    tr("mail_list_flag"),
            COL_READ:    tr("mail_list_status"),
            COL_FROM:    tr("mail_list_from"),
            COL_SUBJECT: tr("mail_list_subject"),
            COL_DATE:    tr("mail_list_date"),
            COL_SIZE:    tr("mail_list_size"),
        }
        arrow = " ▲" if self._sort_asc else " ▼"
        for col, label in col_labels.items():
            info = wx.ListItem()
            info.SetMask(wx.LIST_MASK_TEXT)
            info.SetText(label + arrow if col == self._sort_col else label)
            self.list_ctrl.SetColumn(col, info)

    # ------------------------------------------------------------------ #
    #  Hilfs-Methoden öffentlich                                         #
    # ------------------------------------------------------------------ #

    def select_mail_by_id(self, mail_id: int):
        """Wählt eine Mail anhand ihrer ID aus (Fokus + Selektion)."""
        for row, mid in self._row_to_id.items():
            if mid == mail_id:
                self.list_ctrl.SetItemState(
                    row,
                    wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                    wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
                )
                self.list_ctrl.EnsureVisible(row)
                return

    def reload_current_folder(self):
        parent = self.GetGrandParent()
        if parent and hasattr(parent, "_selected_folder_id") and parent._selected_folder_id:
            mails = self.controller.get_mails(parent._selected_folder_id)
            self.load_mails(mails)

    # ------------------------------------------------------------------ #
    #  Events                                                             #
    # ------------------------------------------------------------------ #

    def _on_item_selected(self, event):
        idx     = event.GetIndex()
        mail_id = self._row_to_id.get(idx)
        if mail_id is not None and self.on_mail_selected:
            self.on_mail_selected(mail_id)

    def _on_item_activated(self, event):
        idx     = event.GetIndex()
        mail_id = self._row_to_id.get(idx)
        if mail_id is not None and self.on_mail_open:
            self.on_mail_open(mail_id)
        elif mail_id is not None:
            self._on_item_selected(event)

    def _on_key_down(self, event: wx.KeyEvent):
        key = event.GetKeyCode()
        if key == wx.WXK_DELETE:
            if self.on_mail_delete:
                self.on_mail_delete(event)
            return
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            idx     = self.list_ctrl.GetFirstSelected()
            mail_id = self._row_to_id.get(idx)
            if mail_id is not None and self.on_mail_open:
                self.on_mail_open(mail_id)
            return
        if key == wx.WXK_TAB:
            event.Skip()
            return
        event.Skip()

    def _on_context_menu(self, event):
        if self.on_context_menu:
            self.on_context_menu(event)

    # ------------------------------------------------------------------ #
    #  Einzelne Mail aktualisieren / entfernen                           #
    # ------------------------------------------------------------------ #

    def refresh_mail_read(self, mail_id: int, force_read: bool = None):
        """
        FIX: Suche über mail_id (O(1) via _id_to_mail), nicht über ListCtrl-Index.
        Danach zugehörige Zeile in _row_to_id finden.
        """
        mail = self._id_to_mail.get(mail_id)
        if not mail:
            return
        is_read = force_read if force_read is not None else True
        mail["is_read"] = is_read

        # Zugehörige Zeile finden
        row = next((r for r, mid in self._row_to_id.items() if mid == mail_id), None)
        if row is None:
            return

        self.list_ctrl.SetItem(
            row, COL_READ,
            tr("mail_status_read") if is_read else tr("mail_status_unread")
        )
        font = self.list_ctrl.GetFont()
        self.list_ctrl.SetItemFont(row, font if is_read else font.Bold())

    def remove_mail(self, mail_id: int):
        """
        FIX: Index-sicheres Löschen.
        Findet die Zeile über _row_to_id (mail_id-basiert), löscht sie aus dem
        ListCtrl und korrigiert alle Indizes > gelöschter Zeile um -1.
        """
        row = next((r for r, mid in self._row_to_id.items() if mid == mail_id), None)
        if row is None:
            return

        self.list_ctrl.DeleteItem(row)

        # _row_to_id neu aufbauen: Indizes > row um 1 verschieben
        new_row_to_id = {}
        for r, mid in self._row_to_id.items():
            if r < row:
                new_row_to_id[r] = mid
            elif r > row:
                new_row_to_id[r - 1] = mid
            # r == row wird weggelassen (gelöscht)
        self._row_to_id = new_row_to_id

        # Auch aus _mail_data und _id_to_mail entfernen
        self._mail_data = [m for m in self._mail_data if m.get("id") != mail_id]
        self._id_to_mail.pop(mail_id, None)

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_date(date_str: str) -> str:
        return format_date_list(date_str)

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size // 1024} KB"
        return f"{size // (1024 * 1024)} MB"

    # ------------------------------------------------------------------ #
    #  Kompatibilitäts-Properties (MainFrame greift auf diese zu)        #
    # ------------------------------------------------------------------ #

    @property
    def _mail_index(self) -> dict:
        """Rückwärtskompatibel: gibt row→mail-dict zurück."""
        return {r: self._id_to_mail.get(mid, {})
                for r, mid in self._row_to_id.items()}
