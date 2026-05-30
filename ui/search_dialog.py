"""
SearchDialog – Mail-Suche nach Thunderbird-Vorbild.
Sucht in allen oder im aktuellen Ordner nach Stichwort, Absender,
Empfänger, Betreff, Inhalt und Datum.
"""

import wx
from core.i18n import tr


class SearchDialog(wx.Frame):
    """
    Nicht-modales Suchfenster (bleibt offen während Mails angesehen werden).
    Ergebnisse werden in einer ListCtrl angezeigt.
    Doppelklick / Enter öffnet die Mail im Viewer.
    """

    def __init__(self, parent, controller, on_open_mail=None):
        super().__init__(parent, title=tr("search_title"), size=(780, 560),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.controller   = controller
        self.on_open_mail = on_open_mail   # Callback: fn(mail_id, folder_id)
        self._results     = []             # Liste von mail-dicts

        self._build_ui()
        self.Centre()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        # ---- Suchfelder ----
        search_box = wx.StaticBox(panel, label=tr("search_title"))
        sb_sizer   = wx.StaticBoxSizer(search_box, wx.VERTICAL)
        gs = wx.FlexGridSizer(cols=4, vgap=6, hgap=10)
        gs.AddGrowableCol(1); gs.AddGrowableCol(3)

        def lbl_ctrl(label, name):
            l = wx.StaticText(panel, label=label)
            c = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
            c.SetName(name)
            return l, c

        lbl_kw,  self.txt_keyword   = lbl_ctrl(tr("search_keyword"),   "keyword")
        lbl_sub, self.txt_subject   = lbl_ctrl(tr("search_subject"),    "subject")
        lbl_fr,  self.txt_sender    = lbl_ctrl(tr("search_sender"),     "sender")
        lbl_to,  self.txt_recipient = lbl_ctrl(tr("search_recipient"),  "recipient")
        lbl_bod, self.txt_body      = lbl_ctrl(tr("search_body"),       "body")

        lbl_df = wx.StaticText(panel, label=tr("search_date_from"))
        self.dp_from = wx.adv.DatePickerCtrl(
            panel, style=wx.adv.DP_DROPDOWN | wx.adv.DP_ALLOWNONE)
        self.dp_from.SetName(tr("search_date_from"))

        lbl_dt = wx.StaticText(panel, label=tr("search_date_to"))
        self.dp_to = wx.adv.DatePickerCtrl(
            panel, style=wx.adv.DP_DROPDOWN | wx.adv.DP_ALLOWNONE)
        self.dp_to.SetName(tr("search_date_to"))

        for w in (lbl_kw, self.txt_keyword, lbl_sub, self.txt_subject,
                  lbl_fr, self.txt_sender,  lbl_to,  self.txt_recipient,
                  lbl_bod, self.txt_body,   lbl_df,  self.dp_from,
                  lbl_dt, self.dp_to,       wx.StaticText(panel, label=""), wx.StaticText(panel, label="")):
            gs.Add(w, 0, wx.ALIGN_CENTER_VERTICAL | wx.EXPAND)

        sb_sizer.Add(gs, 0, wx.EXPAND | wx.ALL, 8)

        # Optionen
        opt_row = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_unread  = wx.CheckBox(panel, label=tr("search_unread_only"))
        self.chk_flagged = wx.CheckBox(panel, label=tr("search_flagged_only"))
        self.chk_all     = wx.CheckBox(panel, label=tr("search_all_folders"))
        self.chk_all.SetValue(True)
        for w in (self.chk_unread, self.chk_flagged, self.chk_all):
            opt_row.Add(w, 0, wx.RIGHT, 16)
        sb_sizer.Add(opt_row, 0, wx.LEFT | wx.BOTTOM, 8)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_search = wx.Button(panel, label=tr("search_btn"))
        self.btn_clear  = wx.Button(panel, label=tr("search_clear"))
        self.lbl_status = wx.StaticText(panel, label="")
        btn_row.Add(self.btn_search, 0, wx.RIGHT, 8)
        btn_row.Add(self.btn_clear,  0, wx.RIGHT, 16)
        btn_row.Add(self.lbl_status, 0, wx.ALIGN_CENTER_VERTICAL)
        sb_sizer.Add(btn_row, 0, wx.LEFT | wx.BOTTOM, 8)

        outer.Add(sb_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # ---- Ergebnisliste ----
        self.list_results = wx.ListCtrl(
            panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_results.SetName(tr("search_results", count=0))
        self.list_results.InsertColumn(0, tr("mail_list_from"),    width=180)
        self.list_results.InsertColumn(1, tr("mail_list_subject"), width=300)
        self.list_results.InsertColumn(2, tr("mail_list_date"),    width=110)
        self.list_results.InsertColumn(3, tr("folder_mailboxes"),  width=120)
        outer.Add(self.list_results, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(outer)

        self.btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        self.btn_clear.Bind(wx.EVT_BUTTON,  self._on_clear)
        self.list_results.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_open)
        self.list_results.Bind(wx.EVT_CHAR_HOOK,           self._on_list_key)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.txt_keyword.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.txt_subject.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.txt_sender.Bind(wx.EVT_TEXT_ENTER,  self._on_search)
        self.txt_keyword.SetFocus()

    # ------------------------------------------------------------------ #
    #  Suche                                                              #
    # ------------------------------------------------------------------ #

    def _on_search(self, event=None):
        self.lbl_status.SetLabel(tr("search_in_progress"))
        self.list_results.DeleteAllItems()
        self._results.clear()
        wx.GetApp().Yield()

        kw      = self.txt_keyword.GetValue().strip().lower()
        subj    = self.txt_subject.GetValue().strip().lower()
        sender  = self.txt_sender.GetValue().strip().lower()
        recip   = self.txt_recipient.GetValue().strip().lower()
        body    = self.txt_body.GetValue().strip().lower()
        unread  = self.chk_unread.GetValue()
        flagged = self.chk_flagged.GetValue()

        date_from = self._wx_date_to_str(self.dp_from.GetValue())
        date_to   = self._wx_date_to_str(self.dp_to.GetValue())

        # Ordner ermitteln
        folder_ids: list[tuple[int, str]] = []  # (folder_id, path_label)
        for mb in self.controller.get_mailboxes():
            for f in self.controller.get_folders(mb["id"]):
                folder_ids.append((f["id"], f"{mb['name']} / {f['name']}"))

        matched = 0
        for fid, path_label in folder_ids:
            try:
                mails = self.controller.db.get_mails(fid)
            except Exception:
                continue
            for mail in mails:
                m = dict(mail)
                if not self._matches(m, kw, subj, sender, recip, body,
                                     unread, flagged, date_from, date_to):
                    continue
                self._results.append((m, fid, path_label))
                idx = self.list_results.InsertItem(
                    self.list_results.GetItemCount(),
                    str(m.get("sender_name") or m.get("sender") or "")
                )
                self.list_results.SetItem(idx, 1, str(m.get("subject") or ""))
                self.list_results.SetItem(idx, 2, str(m.get("date") or "")[:16])
                self.list_results.SetItem(idx, 3, path_label)
                if not int(m.get("is_read") or 0):
                    self.list_results.SetItemFont(idx, self.list_results.GetFont().Bold())
                matched += 1

        count = len(self._results)
        self.lbl_status.SetLabel(
            tr("search_no_results") if count == 0
            else tr("search_results", count=count)
        )
        self.list_results.SetName(tr("search_results", count=count))

    @staticmethod
    def _matches(m, kw, subj, sender, recip, body, unread, flagged, d_from, d_to) -> bool:
        if unread and int(m.get("is_read") or 0):
            return False
        if flagged and not int(m.get("is_flagged") or 0):
            return False
        mail_date = str(m.get("date") or "")[:10]
        if d_from and mail_date and mail_date < d_from:
            return False
        if d_to   and mail_date and mail_date > d_to:
            return False

        def c(field): return str(m.get(field) or "").lower()

        if kw and not any(kw in c(f) for f in
                          ("subject","sender","sender_name","recipients","body_text","body_html")):
            return False
        if subj   and subj   not in c("subject"):    return False
        if sender  and sender  not in c("sender") and sender not in c("sender_name"): return False
        if recip   and recip   not in c("recipients"): return False
        if body    and body    not in c("body_text") and body not in c("body_html"): return False
        return True

    @staticmethod
    def _wx_date_to_str(dt: wx.DateTime) -> str:
        if not dt.IsValid(): return ""
        return f"{dt.GetYear():04d}-{dt.GetMonth()+1:02d}-{dt.GetDay():02d}"

    def _on_clear(self, event=None):
        for ctrl in (self.txt_keyword, self.txt_subject,
                     self.txt_sender, self.txt_recipient, self.txt_body):
            ctrl.SetValue("")
        self.chk_unread.SetValue(False)
        self.chk_flagged.SetValue(False)
        self.chk_all.SetValue(True)
        self.list_results.DeleteAllItems()
        self._results.clear()
        self.lbl_status.SetLabel("")
        self.txt_keyword.SetFocus()

    def _on_open(self, event=None):
        idx = self.list_results.GetFirstSelected()
        if idx < 0 or idx >= len(self._results): return
        mail, fid, _ = self._results[idx]
        if self.on_open_mail:
            self.on_open_mail(mail["id"], fid)

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
