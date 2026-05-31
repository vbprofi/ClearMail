"""
SearchDialog v4 – erweiterte Mail-Suche.

Neu in v4:
  • Kontofilter (Konto-Auswahl oder "Alle Konten")
  • Filter: Nur mit Anhang
  • Volltext-Suche respektiert body_text UND body_html
  • Ergebnisliste: Doppelklick öffnet Mail im Viewer
  • Sortierung durch Klick auf Spaltenheader
  • Statuszeile zeigt Suchzeit
"""

import time
import wx
import wx.adv
from core.i18n import tr

SEARCH_TYPES = [
    ("all",       "search_field_all"),
    ("subject",   "search_field_subject"),
    ("sender",    "search_field_sender"),
    ("recipient", "search_field_recipient"),
    ("body",      "search_field_body"),
]

COL_FROM    = 0
COL_SUBJECT = 1
COL_DATE    = 2
COL_FOLDER  = 3
COL_ATTACH  = 4


class SearchDialog(wx.Frame):

    def __init__(self, parent, controller, on_open_mail=None):
        super().__init__(parent, title=tr("search_title"), size=(900, 580),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.controller   = controller
        self.on_open_mail = on_open_mail
        self._results     = []
        self._sort_col    = COL_DATE
        self._sort_asc    = False
        self._build_ui()
        self.Centre()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        # ---- Zeile 1: Suchbegriff + Typ + Buttons ----
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_kw = wx.StaticText(panel, label=tr("search_keyword") + ":")
        self.txt_keyword = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.txt_keyword.SetName(tr("search_keyword"))
        self.txt_keyword.SetMinSize((260, -1))

        type_choices = [tr(key) for _, key in SEARCH_TYPES]
        self.cho_type = wx.Choice(panel, choices=type_choices)
        self.cho_type.SetSelection(0)
        self.cho_type.SetName(tr("search_field_all"))

        self.btn_search = wx.Button(panel, label=tr("search_btn"))
        self.btn_clear  = wx.Button(panel, label=tr("search_clear"))
        self.btn_search.SetDefault()

        row1.Add(lbl_kw,           0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row1.Add(self.txt_keyword, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row1.Add(self.cho_type,    0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row1.Add(self.btn_search,  0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row1.Add(self.btn_clear,   0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(row1, 0, wx.EXPAND | wx.ALL, 8)

        # ---- Zeile 2: Checkboxen ----
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_unread  = wx.CheckBox(panel, label=tr("search_unread_only"))
        self.chk_flagged = wx.CheckBox(panel, label=tr("search_flagged_only"))
        self.chk_attach  = wx.CheckBox(panel, label=tr("search_has_attach"))
        self.chk_all     = wx.CheckBox(panel, label=tr("search_all_folders"))
        self.chk_all.SetValue(True)
        row2.Add(self.chk_unread,  0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 14)
        row2.Add(self.chk_flagged, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 14)
        row2.Add(self.chk_attach,  0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 14)
        row2.Add(self.chk_all,     0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(row2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # ---- Zeile 3: Datum + Kontofilter ----
        row3 = wx.BoxSizer(wx.HORIZONTAL)
        lbl_df = wx.StaticText(panel, label=tr("search_date_from"))
        self.dp_from = wx.adv.DatePickerCtrl(
            panel, style=wx.adv.DP_DROPDOWN | wx.adv.DP_ALLOWNONE)
        self.dp_from.SetName(tr("search_date_from"))
        lbl_dt = wx.StaticText(panel, label=tr("search_date_to"))
        self.dp_to = wx.adv.DatePickerCtrl(
            panel, style=wx.adv.DP_DROPDOWN | wx.adv.DP_ALLOWNONE)
        self.dp_to.SetName(tr("search_date_to"))

        # Kontofilter
        lbl_acc = wx.StaticText(panel, label=tr("search_account_filter"))
        self._acc_list = [None] + [dict(a) for a in self.controller.get_accounts()
                                   if dict(a).get("protocol", "IMAP") != "LOCAL"]
        acc_labels = [tr("search_account_all")] + [
            a["name"] for a in self._acc_list if a]
        self.cho_acc = wx.Choice(panel, choices=acc_labels)
        self.cho_acc.SetSelection(0)
        self.cho_acc.SetName(tr("search_account_filter"))

        row3.Add(lbl_df,       0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row3.Add(self.dp_from, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        row3.Add(lbl_dt,       0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row3.Add(self.dp_to,   0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)
        row3.Add(lbl_acc,      0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        row3.Add(self.cho_acc, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(row3, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Status
        self.lbl_status = wx.StaticText(panel, label="")
        outer.Add(self.lbl_status, 0, wx.LEFT | wx.BOTTOM, 8)
        outer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ---- Ergebnisliste ----
        self.list_results = wx.ListCtrl(
            panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_results.SetName(tr("search_results", count=0))
        self.list_results.InsertColumn(COL_FROM,    tr("mail_list_from"),    width=190)
        self.list_results.InsertColumn(COL_SUBJECT, tr("mail_list_subject"), width=280)
        self.list_results.InsertColumn(COL_DATE,    tr("mail_list_date"),    width=120)
        self.list_results.InsertColumn(COL_FOLDER,  tr("folder_mailboxes"), width=150)
        self.list_results.InsertColumn(COL_ATTACH,  "📎",                    width=30)
        outer.Add(self.list_results, 1, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(outer)

        # Events
        self.btn_search.Bind(wx.EVT_BUTTON,                self._on_search)
        self.btn_clear.Bind(wx.EVT_BUTTON,                 self._on_clear)
        self.txt_keyword.Bind(wx.EVT_TEXT_ENTER,           self._on_search)
        self.list_results.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_open)
        self.list_results.Bind(wx.EVT_LIST_COL_CLICK,      self._on_col_click)
        self.list_results.Bind(wx.EVT_CHAR_HOOK,           self._on_list_key)
        self.list_results.Bind(wx.EVT_CONTEXT_MENU,        self._on_result_ctx)
        self.Bind(wx.EVT_CHAR_HOOK,                        self._on_key)
        self.txt_keyword.SetFocus()

    # ------------------------------------------------------------------ #
    #  Suche                                                              #
    # ------------------------------------------------------------------ #

    def _on_search(self, event=None):
        self.list_results.DeleteAllItems()
        self._results.clear()
        self.lbl_status.SetLabel("Suche läuft…")
        wx.GetApp().Yield()

        kw = self.txt_keyword.GetValue().strip()
        if (not kw and not self.chk_unread.GetValue()
                and not self.chk_flagged.GetValue()
                and not self.chk_attach.GetValue()):
            self.lbl_status.SetLabel("")
            return

        t0       = time.monotonic()
        type_idx = self.cho_type.GetSelection()
        field    = SEARCH_TYPES[type_idx][0] if 0 <= type_idx < len(SEARCH_TYPES) else "all"
        unread   = self.chk_unread.GetValue()
        flagged  = self.chk_flagged.GetValue()
        attach   = self.chk_attach.GetValue()
        date_from = self._wx_date_to_str(self.dp_from.GetValue())
        date_to   = self._wx_date_to_str(self.dp_to.GetValue())

        # Konto-Scope
        acc_idx      = self.cho_acc.GetSelection()
        filter_acc   = self._acc_list[acc_idx] if acc_idx > 0 else None
        filter_acc_id = filter_acc["id"] if filter_acc else None

        # Ordner-Scope
        folder_scope = []
        for mb in self.controller.get_mailboxes():
            mb = dict(mb)
            if filter_acc_id:
                sc = self.controller.db._get_structure_conn()
                mb_row = sc.execute(
                    "SELECT id FROM mailboxes WHERE account_id=?",
                    (filter_acc_id,)
                ).fetchone()
                if not mb_row or mb_row[0] != mb["id"]:
                    continue
            for f in self.controller.get_folders(mb["id"]):
                f = dict(f)
                folder_scope.append((f["id"], f"{mb['name']} / {f['name']}"))

        kw_lower = kw.lower()
        for fid, path_label in folder_scope:
            try:
                mails = self.controller.db.get_mails(fid)
            except Exception:
                continue
            for mail in mails:
                m = dict(mail)
                if not self._matches(m, kw_lower, field, unread,
                                     flagged, attach, date_from, date_to):
                    continue
                self._results.append((m, fid, path_label))

        # Sortieren
        self._sort_results()
        self._render_results()

        elapsed = time.monotonic() - t0
        count   = len(self._results)
        self.lbl_status.SetLabel(
            (tr("search_no_results") if count == 0
             else tr("search_results", count=count))
            + f"  ({elapsed:.2f}s)")
        self.list_results.SetName(tr("search_results", count=count))

    @staticmethod
    def _matches(m: dict, kw: str, field: str,
                 unread: bool, flagged: bool, attach: bool,
                 d_from: str, d_to: str) -> bool:
        if unread  and int(m.get("is_read")    or 0):     return False
        if flagged and not int(m.get("is_flagged") or 0): return False
        if attach  and not int(m.get("has_attach") or 0): return False
        mail_date = str(m.get("date") or "")[:10]
        if d_from and mail_date and mail_date < d_from:   return False
        if d_to   and mail_date and mail_date > d_to:     return False
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
            # Volltext: body_text + HTML-stripped body_html
            body = c("body_text")
            html = c("body_html")
            if not body and html:
                from ui.html_renderer import html_to_text
                body = html_to_text(m.get("body_html", "")).lower()
            return kw in body or kw in html
        else:  # "all"
            body = c("body_text") or c("body_html")
            return any(kw in c(f) for f in
                       ("subject", "sender", "sender_name",
                        "recipients", "body_text")) or kw in body

    # ------------------------------------------------------------------ #
    #  Sortierung                                                         #
    # ------------------------------------------------------------------ #

    def _on_col_click(self, event: wx.ListEvent):
        col = event.GetColumn()
        if col == self._sort_col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col in (COL_FROM, COL_SUBJECT, COL_FOLDER)
        self._sort_results()
        self._render_results()

    def _sort_results(self):
        col = self._sort_col
        asc = self._sort_asc
        def key(t):
            m = t[0]
            if col == COL_DATE:    return str(m.get("date") or "")
            if col == COL_FROM:    return (str(m.get("sender_name") or m.get("sender") or "")).lower()
            if col == COL_SUBJECT: return str(m.get("subject") or "").lower()
            if col == COL_FOLDER:  return t[2].lower()
            if col == COL_ATTACH:  return int(m.get("has_attach") or 0)
            return str(m.get("date") or "")
        self._results.sort(key=key, reverse=not asc)

    def _render_results(self):
        lc   = self.list_results
        font = lc.GetFont()
        bold = font.Bold()
        lc.Freeze()
        try:
            lc.DeleteAllItems()
            for mail, fid, path_label in self._results:
                idx = lc.InsertItem(
                    lc.GetItemCount(),
                    str(mail.get("sender_name") or mail.get("sender") or ""))
                lc.SetItem(idx, COL_SUBJECT, str(mail.get("subject") or ""))
                lc.SetItem(idx, COL_DATE,    str(mail.get("date") or "")[:16])
                lc.SetItem(idx, COL_FOLDER,  path_label)
                lc.SetItem(idx, COL_ATTACH,  "📎" if mail.get("has_attach") else "")
                if not int(mail.get("is_read") or 0):
                    lc.SetItemFont(idx, bold)
        finally:
            lc.Thaw()

    # ------------------------------------------------------------------ #
    #  Kontextmenü auf Ergebnisliste                                     #
    # ------------------------------------------------------------------ #

    def _on_result_ctx(self, event):
        idx = self.list_results.GetFirstSelected()
        if idx < 0 or idx >= len(self._results):
            return
        menu = wx.Menu()
        mi_open = menu.Append(wx.ID_ANY, tr("ctx_open"))
        self.Bind(wx.EVT_MENU, lambda e: self._on_open(), mi_open)
        self.list_results.PopupMenu(menu)
        menu.Destroy()

    # ------------------------------------------------------------------ #
    #  Navigation                                                         #
    # ------------------------------------------------------------------ #

    def _on_open(self, event=None):
        idx = self.list_results.GetFirstSelected()
        if idx < 0 or idx >= len(self._results):
            return
        mail, fid, _ = self._results[idx]
        if self.on_open_mail:
            self.on_open_mail(mail["id"], fid)

    def _on_clear(self, event=None):
        self.txt_keyword.SetValue("")
        self.cho_type.SetSelection(0)
        self.chk_unread.SetValue(False)
        self.chk_flagged.SetValue(False)
        self.chk_attach.SetValue(False)
        self.chk_all.SetValue(True)
        self.cho_acc.SetSelection(0)
        self.list_results.DeleteAllItems()
        self._results.clear()
        self.lbl_status.SetLabel("")
        self.txt_keyword.SetFocus()

    def _on_list_key(self, event: wx.KeyEvent):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_open()
            return
        event.Skip()

    def _on_key(self, event: wx.KeyEvent):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()

    @staticmethod
    def _wx_date_to_str(dt: wx.DateTime) -> str:
        if not dt.IsValid():
            return ""
        return f"{dt.GetYear():04d}-{dt.GetMonth()+1:02d}-{dt.GetDay():02d}"
