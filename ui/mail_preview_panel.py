"""
MailPreviewPanel – Mail-Vorschau. Vollständig i18n-fähig.
Tab-Navigation via EVT_CHAR_HOOK.
"""

import wx
from datetime import datetime
from core.i18n import tr


class MailPreviewPanel(wx.Panel):

    def __init__(self, parent, controller):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.controller    = controller
        self._current_mail = None
        self._build_ui()

    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        lbl_header = wx.StaticText(self, label=tr("preview_header"))
        lbl_header.SetFont(lbl_header.GetFont().Bold())
        outer.Add(lbl_header, 0, wx.ALL, 4)

        grid = wx.FlexGridSizer(cols=2, vgap=3, hgap=6)
        grid.AddGrowableCol(1)

        self.txt_from    = self._make_field(grid, tr("preview_from"),    "Von")
        self.txt_to      = self._make_field(grid, tr("preview_to"),      "An")
        self.txt_cc      = self._make_field(grid, tr("preview_cc"),      "CC")
        self.txt_subject = self._make_field(grid, tr("preview_subject"), "Betreff")
        self.txt_date    = self._make_field(grid, tr("preview_date"),    "Datum")
        self.txt_attach  = self._make_field(grid, tr("preview_attach"),  "Anhang")

        outer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 4)

        lbl_body = wx.StaticText(self, label=tr("preview_body"))
        outer.Add(lbl_body, 0, wx.LEFT | wx.BOTTOM, 4)

        self.txt_body = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_AUTO_URL | wx.BORDER_SUNKEN
        )
        self.txt_body.SetName(tr("preview_body_tooltip"))
        self.txt_body.SetFont(wx.Font(
            10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL
        ))
        outer.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 4)
        self.SetSizer(outer)

        self._tab_fields = [
            self.txt_body,
            self.txt_from, self.txt_to, self.txt_cc,
            self.txt_subject, self.txt_date, self.txt_attach,
        ]
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _make_field(self, grid, label_text: str, name: str) -> wx.TextCtrl:
        lbl  = wx.StaticText(self, label=label_text, size=(70, -1),
                             style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE)
        ctrl = wx.TextCtrl(self, style=wx.TE_READONLY | wx.BORDER_SIMPLE)
        ctrl.SetName(name)
        ctrl.SetToolTip(f"{label_text} {tr('mail_status_read').lower()}")
        grid.Add(lbl,  0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(ctrl, 1, wx.EXPAND)
        return ctrl

    def _on_char_hook(self, event: wx.KeyEvent):
        if event.GetKeyCode() != wx.WXK_TAB:
            event.Skip()
            return
        focused = self.FindFocus()
        fields  = self._tab_fields
        if focused not in fields:
            event.Skip()
            return
        idx      = fields.index(focused)
        shift    = event.ShiftDown()
        next_idx = (idx - 1) % len(fields) if shift else (idx + 1) % len(fields)
        fields[next_idx].SetFocus()

    @staticmethod
    def _s(value, default: str = "") -> str:
        return default if value is None else str(value)

    def show_mail(self, mail: dict):
        self._current_mail = mail
        sender_name  = self._s(mail.get("sender_name"))
        sender_email = self._s(mail.get("sender"))
        from_str = f"{sender_name} <{sender_email}>" if sender_name else sender_email

        self.txt_from.SetValue(from_str)
        self.txt_to.SetValue(self._s(mail.get("recipients")))
        self.txt_cc.SetValue(self._s(mail.get("cc")))
        self.txt_subject.SetValue(self._s(mail.get("subject"), tr("preview_no_subject")))
        self.txt_date.SetValue(self._format_date(self._s(mail.get("date"))))
        self.txt_attach.SetValue(
            tr("preview_attach_yes") if mail.get("has_attach") else tr("preview_attach_no")
        )

        body = self._s(mail.get("body_text")) or self._s(mail.get("body_html"))
        self.txt_body.SetValue(body)
        self.txt_body.SetInsertionPoint(0)

        self.txt_subject.SetName(
            f"{tr('preview_subject')} {self._s(mail.get('subject'), tr('preview_no_subject'))}"
        )

    def clear(self):
        self._current_mail = None
        for ctrl in self._tab_fields:
            ctrl.SetValue("")

    @staticmethod
    def _format_date(date_str: str) -> str:
        if not date_str:
            return ""
        try:
            dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%A, %d. %B %Y, %H:%M Uhr")
        except ValueError:
            return date_str
