"""
SearchDialog – Mail-Suche nach Thunderbird-Vorbild.

Aufbau (kompakt, wie Thunderbird):
  [ Suchbegriff _________________ ] [ Suchen in: ▼ Alles ] [ Suchen ] [ Zurücksetzen ]
  [ ] Nur ungelesen  [ ] Nur markiert  [ ] Alle Ordner
  Von (Datum):  [DatePicker]   Bis: [DatePicker]
  ──────────────────────────────────────────────
  Ergebnisliste
"""

import wx
import wx.adv
from core.i18n import tr


# Suchtypen: (Schlüssel, Locale-Key)
SEARCH_TYPES = [
    ("all",       "search_field_all"),
    ("subject",   "search_field_subject"),
    ("sender",    "search_field_sender"),
    ("recipient", "search_field_recipient"),
    ("body",      "search_field_body"),
]


class SearchDialog(wx.Frame):
    """Nicht-modales Suchfenster, bleibt offen während Mails angesehen werden."""

    def __init__(self, parent, controller, on_open_mail=None):
        super().__init__(parent, title=tr("search_title"), size=(820, 540),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.controller   = controller
        self.on_open_mail = on_open_mail
        self._results     = []   # list of (mail_dict, folder_id, path_label)
        self._build_ui()
        self.Centre()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        # ---- Hauptsuche: Suchfeld + Typ-Dropdown + Buttons ----
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_kw = wx.StaticText(panel, label=tr("search_keyword") + ":")
        self.txt_keyword = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.txt_keyword.SetName(tr("search_keyword"))
        self.txt_keyword.SetMinSize((280, -1))

        # Suchtyp-Aufklappliste
        type_choices = [tr(key) for _, key in SEARCH_TYPES]
        self.cho_type = wx.Choice(panel, choices=type_choices)
        self.cho_type.SetSelection(0)   # "Alles"
        self.cho_type.SetName(tr("search_field_all"))

        self.btn_search = wx.Button(panel, label=tr("search_btn"))
        self.btn_clear  = wx.Button(panel, label=tr("search_clear"))
        self.btn_search.SetDefault()

        row1.Add(lbl_kw,           0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row1.Add(self.txt_keyword, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        row1.Add(self.cho_type,    0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        row1.Add(self.btn_search,  0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row1.Add(self.btn_clear,   0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(row1, 0, wx.EXPAND | wx.ALL, 8)

        # ---- Filter-Zeile: Checkboxen + Datum ----
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_unread  = wx.CheckBox(panel, label=tr("search_unread_only"))
        self.chk_flagged = wx.CheckBox(panel, label=tr("search_flagged_only"))
        self.chk_all     = wx.CheckBox(panel, label=tr("search_all_folders"))
        self.chk_all.SetValue(True)

        lbl_df = wx.StaticText(panel, label=tr("search_date_from"))
        self.dp_from = wx.adv.DatePickerCtrl(
            panel, style=wx.adv.DP_DROPDOWN | wx.adv.DP_ALLOWNONE)
        self.dp_from.SetName(tr("search_date_from"))

        lbl_dt = wx.StaticText(panel, label=tr("search_date_to"))
        self.dp_to = wx.adv.DatePickerCtrl(
            panel, style=wx.adv.DP_DROPDOWN | wx.adv.DP_ALLOWNONE)
        self.dp_to.SetName(tr("search_date_to"))

        row2.Add(self.chk_unread,  0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 14)
        row2.Add(self.chk_flagged, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 14)
        row2.Add(self.chk_all,     0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)
        row2.Add(lbl_df,           0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row2.Add(self.dp_from,     0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        row2.Add(lbl_dt,           0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row2.Add(self.dp_to,       0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(row2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Status
        self.lbl_status = wx.StaticText(panel, label="")
        outer.Add(self.lbl_status, 0, wx.LEFT | wx.BOTTOM, 8)

        outer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ---- Ergebnisliste ----
        self.list_results = wx.ListCtrl(
            panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_results.SetName(tr("search_results", count=0))
        self.list_results.InsertColumn(0, tr("mail_list_from"),    width=180)
        self.list_results.InsertColumn(1, tr("mail_list_subject"), width=300)
        self.list_results.InsertColumn(2, tr("mail_list_date"),    width=110)
        self.list_results.InsertColumn(3, tr("folder_mailboxes"),  width=130)
        outer.Add(self.list_results, 1, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(outer)

        # ---- Events ----
        self.btn_search.Bind(wx.EVT_BUTTON,           self._on_search)
        self.btn_clear.Bind(wx.EVT_BUTTON,            self._on_clear)
        self.txt_keyword.Bind(wx.EVT_TEXT_ENTER,      self._on_search)
        self.list_results.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_open)
        self.list_results.Bind(wx.EVT_CHAR_HOOK,      self._on_list_key)
        self.Bind(wx.EVT_CHAR_HOOK,                   self._on_key)

        self.txt_keyword.SetFocus()

    # ------------------------------------------------------------------ #
    #  Suche                                                              #
    # ------------------------------------------------------------------ #

    def _on_search(self, event=None):
        self.list_results.DeleteAllItems()
        self._results.clear()
        self.lbl_status.SetLabel(tr("search_in_progress") if hasattr(tr("search_in_progress"), "__len__")
                                  else "Suche läuft…")
        wx.GetApp().Yield()

        kw       = self.txt_keyword.GetValue().strip()
        if not kw and not self.chk_unread.GetValue() and not self.chk_flagged.GetValue():
            self.lbl_status.SetLabel("")
            return

        # Suchtyp aus Aufklappliste
        type_idx = self.cho_type.GetSelection()
        field    = SEARCH_TYPES[type_idx][0] if 0 <= type_idx < len(SEARCH_TYPES) else "all"

        unread   = self.chk_unread.GetValue()
        flagged  = self.chk_flagged.GetValue()
        date_from = self._wx_date_to_str(self.dp_from.GetValue())
        date_to   = self._wx_date_to_str(self.dp_to.GetValue())

        # Ordner-Scope
        folder_scope: list[tuple[int, str]] = []
        for mb in self.controller.get_mailboxes():
            for f in self.controller.get_folders(mb["id"]):
                folder_scope.append((f["id"], f"{mb['name']} / {f['name']}"))

        kw_lower = kw.lower()
        for fid, path_label in folder_scope:
            try:
                mails = self.controller.db.get_mails(fid)
            except Exception:
                continue
            for mail in mails:
                m = dict(mail)
                if not self._matches(m, kw_lower, field, unread, flagged,
                                     date_from, date_to):
                    continue
                self._results.append((m, fid, path_label))
                idx = self.list_results.InsertItem(
                    self.list_results.GetItemCount(),
                    str(m.get("sender_name") or m.get("sender") or ""))
                self.list_results.SetItem(idx, 1, str(m.get("subject") or ""))
                self.list_results.SetItem(idx, 2, str(m.get("date") or "")[:16])
                self.list_results.SetItem(idx, 3, path_label)
                if not int(m.get("is_read") or 0):
                    self.list_results.SetItemFont(
                        idx, self.list_results.GetFont().Bold())

        count = len(self._results)
        self.lbl_status.SetLabel(
            tr("search_no_results") if count == 0
            else tr("search_results", count=count))
        self.list_results.SetName(tr("search_results", count=count))

    @staticmethod
    def _matches(m: dict, kw: str, field: str,
                 unread: bool, flagged: bool,
                 d_from: str, d_to: str) -> bool:
        # Flags
        if unread  and int(m.get("is_read")    or 0): return False
        if flagged and not int(m.get("is_flagged") or 0): return False
        # Datum
        mail_date = str(m.get("date") or "")[:10]
        if d_from and mail_date and mail_date < d_from: return False
        if d_to   and mail_date and mail_date > d_to:   return False
        # Kein Suchbegriff → nur Filter
        if not kw:
            return True
        def c(f): return str(m.get(f) or "").lower()
        if field == "subject":
            return kw in c("subject")
        elif field == "sender":
            return kw in c("sender") or kw in c("sender_name")
        elif field == "recipient":
            return kw in c("recipients") or kw in c("cc")
        elif field == "body":
            return kw in c("body_text") or kw in c("body_html")
        else:  # "all"
            return any(kw in c(f) for f in
                       ("subject", "sender", "sender_name",
                        "recipients", "body_text", "body_html"))

    @staticmethod
    def _wx_date_to_str(dt: wx.DateTime) -> str:
        if not dt.IsValid(): return ""
        return f"{dt.GetYear():04d}-{dt.GetMonth()+1:02d}-{dt.GetDay():02d}"

    def _on_clear(self, event=None):
        self.txt_keyword.SetValue("")
        self.cho_type.SetSelection(0)
        self.chk_unread.SetValue(False)
        self.chk_flagged.SetValue(False)
        self.chk_all.SetValue(True)
        self.list_results.DeleteAllItems()
        self._results.clear()
        self.lbl_status.SetLabel("")
        self.txt_keyword.SetFocus()

    # ------------------------------------------------------------------ #
    #  Öffnen / Navigation                                               #
    # ------------------------------------------------------------------ #

    def _on_open(self, event=None):
        idx = self.list_results.GetFirstSelected()
        if idx < 0 or idx >= len(self._results): return
        mail, fid, _ = self._results[idx]
        if self.on_open_mail:
            self.on_open_mail(mail["id"], fid)

    def _on_list_key(self, event: wx.KeyEvent):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_open(); return
        event.Skip()

    def _on_key(self, event: wx.KeyEvent):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close(); return
        event.Skip()
