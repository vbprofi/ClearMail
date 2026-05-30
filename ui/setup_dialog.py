"""
SetupDialog – Ersteinrichtung: lokales Konto anlegen.
Wird beim ersten Start angezeigt wenn keine Konten vorhanden sind.
"""

import re
import wx
from core.i18n import tr


class SetupDialog(wx.Dialog):

    def __init__(self, parent):
        super().__init__(parent, title=tr("setup_title"), size=(420, 280),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.result_name  = ""
        self.result_email = ""
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        desc = wx.StaticText(panel, label=tr("setup_desc"))
        desc.Wrap(380)
        outer.Add(desc, 0, wx.ALL, 12)
        outer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        gs = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs.AddGrowableCol(1)

        gs.Add(wx.StaticText(panel, label=tr("setup_name_label")),
               0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_name = wx.TextCtrl(panel)
        self.txt_name.SetName(tr("setup_name_label"))
        gs.Add(self.txt_name, 1, wx.EXPAND)

        gs.Add(wx.StaticText(panel, label=tr("setup_email_label")),
               0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_email = wx.TextCtrl(panel)
        self.txt_email.SetName(tr("setup_email_label"))
        gs.Add(self.txt_email, 1, wx.EXPAND)

        outer.Add(gs, 0, wx.EXPAND | wx.ALL, 12)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_create = wx.Button(panel, label=tr("setup_btn_create"))
        btn_skip   = wx.Button(panel, wx.ID_CANCEL, tr("setup_btn_skip"))
        btn_create.SetDefault()
        btn_row.Add(btn_create, 0, wx.RIGHT, 8)
        btn_row.Add(btn_skip)
        outer.Add(btn_row, 0, wx.ALIGN_RIGHT | wx.ALL, 12)

        panel.SetSizer(outer)
        btn_create.Bind(wx.EVT_BUTTON, self._on_create)
        self.txt_name.SetFocus()

    def _on_create(self, event):
        name  = self.txt_name.GetValue().strip()
        email = self.txt_email.GetValue().strip()
        if not name:
            wx.MessageBox(tr("setup_err_name"), tr("error_title"),
                          wx.OK | wx.ICON_WARNING, self)
            self.txt_name.SetFocus()
            return
        if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            wx.MessageBox(tr("setup_err_email"), tr("error_title"),
                          wx.OK | wx.ICON_WARNING, self)
            self.txt_email.SetFocus()
            return
        self.result_name  = name
        self.result_email = email
        self.EndModal(wx.ID_OK)
