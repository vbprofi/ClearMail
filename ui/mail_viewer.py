"""
MailViewerFrame – v8-Ansatz: wx.Simplebook mit TextCtrl (Seite 0) + HTML-Widget (Seite 1).
ESC/Tab via _on_all_keys (kombinierter Handler an Frame + _book + _html_widget).
"""

import wx
import os
from core.i18n import tr
from ui.html_renderer import html_to_text, create_html_widget, set_html_content


class MailViewerFrame(wx.Frame):

    def __init__(self, parent, mail: dict, controller=None):
        subject = str(mail.get("subject") or tr("preview_no_subject"))
        super().__init__(
            parent,
            title=f"{subject} – {tr('app_title')}",
            size=(820, 650),
            style=wx.DEFAULT_FRAME_STYLE
        )
        self.mail          = mail
        self.controller    = controller or self._find_controller()
        self._html_mode    = False
        self._html_backend = "textctrl"
        self._html_widget  = None

        self._build_ui()
        self._populate(mail)
        self.Centre()

    @staticmethod
    def _find_controller():
        app = wx.GetApp()
        if app:
            return getattr(app.GetTopWindow(), "controller", None)
        return None

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        # ---- Header ----
        grid = wx.FlexGridSizer(cols=2, vgap=4, hgap=8)
        grid.AddGrowableCol(1)
        self.txt_from    = self._hdr_field(panel, grid, tr("preview_from"))
        self.txt_to      = self._hdr_field(panel, grid, tr("preview_to"))
        self.txt_cc      = self._hdr_field(panel, grid, tr("preview_cc"))
        self.txt_subject = self._hdr_field(panel, grid, tr("preview_subject"))
        self.txt_date    = self._hdr_field(panel, grid, tr("preview_date"))
        outer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)
        outer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ---- Body: wx.Simplebook ----
        # Seite 0 = TextCtrl (Plaintext)
        # Seite 1 = HTML-Widget (WebView / HtmlWindow / TextCtrl-Fallback)
        lbl_body = wx.StaticText(panel, label=tr("preview_body"))
        outer.Add(lbl_body, 0, wx.LEFT | wx.TOP, 8)

        self._book = wx.Simplebook(panel)
        outer.Add(self._book, 1, wx.EXPAND | wx.ALL, 8)

        # Seite 0: TextCtrl (initial sichtbar)
        self.txt_body = wx.TextCtrl(
            self._book,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_AUTO_URL | wx.BORDER_SUNKEN
        )
        self.txt_body.SetName(tr("preview_body"))
        self.txt_body.SetFont(wx.Font(
            10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self._book.AddPage(self.txt_body, "Text")

        # Seite 1: HTML-Widget – NACH outer.Add() erstellen damit _book
        # bereits im Window-Tree verankert ist (nötig für WebView/HtmlWindow)
        self._html_widget, self._html_backend = create_html_widget(self._book)
        self._html_widget.SetName("HTML-Nachrichteninhalt")
        self._book.AddPage(self._html_widget, "HTML")

        # Initial: Seite 0
        self._book.SetSelection(0)

        # ---- Anhang-Liste ----
        self.attach_panel = wx.Panel(panel)
        asizer = wx.BoxSizer(wx.VERTICAL)
        lbl_a  = wx.StaticText(self.attach_panel, label="📎 Anhänge:")
        lbl_a.SetFont(lbl_a.GetFont().Bold())
        asizer.Add(lbl_a, 0, wx.BOTTOM, 4)
        self.list_attach = wx.ListCtrl(
            self.attach_panel,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_attach.SetName("Anhang-Liste")
        self.list_attach.InsertColumn(0, "Dateiname", width=260)
        self.list_attach.InsertColumn(1, "Typ",       width=130)
        self.list_attach.InsertColumn(2, "Größe",     width=80)
        self.list_attach.SetMinSize((-1, 100))
        asizer.Add(self.list_attach, 1, wx.EXPAND)
        self.attach_panel.SetSizer(asizer)
        outer.Add(self.attach_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.attach_panel.Hide()

        # ---- Buttons ----
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_toggle = wx.Button(panel, label="🌐 " + tr("btn_show_html"))
        self.btn_toggle.SetName("HTML/Text umschalten")
        btn_reply   = wx.Button(panel, label=tr("menu_mail_reply"))
        btn_forward = wx.Button(panel, label=tr("menu_mail_forward"))
        btn_close   = wx.Button(panel, wx.ID_CLOSE, tr("dlg_close"))
        btn_row.Add(self.btn_toggle, 0, wx.RIGHT, 8)
        btn_row.Add(btn_reply,   0, wx.RIGHT, 6)
        btn_row.Add(btn_forward, 0, wx.RIGHT, 6)
        btn_row.AddStretchSpacer()
        btn_row.Add(btn_close)
        outer.Add(btn_row, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(outer)

        # ---- Events ----
        # Kombinierter Handler an Frame + _book + _html_widget
        # → ESC funktioniert auch wenn WebView/HtmlWindow den Fokus hat
        self.Bind(wx.EVT_CHAR_HOOK,        self._on_all_keys)
        self._book.Bind(wx.EVT_CHAR_HOOK,  self._on_all_keys)
        self._html_widget.Bind(wx.EVT_CHAR_HOOK, self._on_all_keys)

        id_esc = wx.NewIdRef()
        self.SetAcceleratorTable(wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, wx.WXK_ESCAPE, id_esc),
        ]))
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), id=id_esc)

        self.btn_toggle.Bind(wx.EVT_BUTTON,  self._on_toggle_html)
        btn_reply.Bind(wx.EVT_BUTTON,   self._on_reply)
        btn_forward.Bind(wx.EVT_BUTTON, self._on_forward)
        btn_close.Bind(wx.EVT_BUTTON,   lambda e: self.Close())
        self.list_attach.Bind(wx.EVT_CONTEXT_MENU,        self._on_attach_ctx)
        self.list_attach.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_attach_open)

        self._tab_fields = [
            self.txt_body, self.txt_from, self.txt_to,
            self.txt_cc, self.txt_subject, self.txt_date,
        ]

    @staticmethod
    def _hdr_field(parent, grid, label_text: str) -> wx.TextCtrl:
        lbl  = wx.StaticText(parent, label=label_text, size=(70, -1),
                             style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE)
        ctrl = wx.TextCtrl(parent, style=wx.TE_READONLY | wx.BORDER_SIMPLE)
        ctrl.SetName(label_text.rstrip(":"))
        grid.Add(lbl,  0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(ctrl, 1, wx.EXPAND)
        return ctrl

    # ------------------------------------------------------------------ #
    #  Daten                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _s(v, default=""): return default if v is None else str(v)

    def _populate(self, mail: dict):
        sn = self._s(mail.get("sender_name"))
        se = self._s(mail.get("sender"))
        self.txt_from.SetValue(f"{sn} <{se}>" if sn else se)
        self.txt_to.SetValue(self._s(mail.get("recipients")))
        self.txt_cc.SetValue(self._s(mail.get("cc")))
        self.txt_subject.SetValue(self._s(mail.get("subject"), tr("preview_no_subject")))
        self.txt_date.SetValue(self._s(mail.get("date")))

        body_html = self._s(mail.get("body_html"))
        body_text = self._s(mail.get("body_text"))
        has_html  = bool(body_html.strip())

        self.btn_toggle.Show(has_html)

        render = self._get_render_setting()

        if self._get_render_setting() and has_html:
            self._activate_html_mode(body_html)
        else:
            plaintext = html_to_text(body_html) if body_html else body_text
            self.txt_body.SetValue(plaintext)
            self.txt_body.SetInsertionPoint(0)
            self._book.SetSelection(0)
            self._html_mode = False
            self._update_toggle_label()
            wx.CallAfter(self.txt_body.SetFocus)

        attachments = mail.get("attachments") or []
        if attachments or mail.get("has_attach"):
            self.attach_panel.Show()
            for att in (attachments or []):
                idx = self.list_attach.InsertItem(
                    self.list_attach.GetItemCount(),
                    self._s(att.get("filename"), "(Unbekannt)"))
                self.list_attach.SetItem(idx, 1, self._s(att.get("mime_type")))
                self.list_attach.SetItem(idx, 2, self._fmt_size(att.get("size", 0)))
        self.Layout()

    def _activate_html_mode(self, body_html: str):
        """Seite 1 im Simplebook aktivieren, Inhalt via CallAfter setzen."""
        self._html_mode = True
        self._book.SetSelection(1)
        self._update_toggle_label()
        wx.CallAfter(self._do_set_html, body_html)

    def _do_set_html(self, body_html: str):
        """Setzt HTML-Inhalt – läuft nach Show() via CallAfter."""
        if not self._html_mode:
            return
        try:
            set_html_content(self._html_widget, body_html, self._html_backend)
        except Exception:
            self._book.SetSelection(0)
            self.txt_body.SetValue(html_to_text(body_html))
            self.txt_body.SetInsertionPoint(0)
            self._html_mode = False
            self._update_toggle_label()
            wx.CallAfter(self.txt_body.SetFocus)
            return
        # Fokus auf HTML-Widget: WebView2 braucht nach SetPage etwas Zeit.
        # CallLater(200ms) gibt dem Browser Zeit zum Rendern, dann SetFocus.
        if self._html_backend == "webview":
            wx.CallLater(200, self._focus_html_widget)
        else:
            wx.CallAfter(self._focus_html_widget)

    def _focus_html_widget(self):
        """Setzt Fokus auf das HTML-Widget (sicher via CallAfter/CallLater)."""
        try:
            if self._html_mode and self._html_widget.IsShown():
                self._html_widget.SetFocus()
        except Exception:
            pass

    def _get_render_setting(self) -> bool:
        if self.controller:
            return self.controller.get_setting("render_html", "0") == "1"
        return False

    def _switch_mode(self, html_on: bool):
        body_html = self._s(self.mail.get("body_html"))
        body_text = self._s(self.mail.get("body_text"))
        self._html_mode = html_on
        self._update_toggle_label()

        if html_on:
            self._book.SetSelection(1)
            try:
                set_html_content(self._html_widget, body_html, self._html_backend)
                if self._html_backend == "webview":
                    wx.CallLater(200, self._focus_html_widget)
                else:
                    wx.CallAfter(self._focus_html_widget)
            except Exception:
                self._book.SetSelection(0)
                self._html_mode = False
                self._update_toggle_label()
        else:
            self._book.SetSelection(0)
            plaintext = html_to_text(body_html) if body_html else body_text
            self.txt_body.SetValue(plaintext)
            self.txt_body.SetInsertionPoint(0)
            wx.CallAfter(self.txt_body.SetFocus)

    def _update_toggle_label(self):
        if self._html_mode:
            self.btn_toggle.SetLabel("📄 " + tr("btn_show_text"))
        else:
            self.btn_toggle.SetLabel("🌐 " + tr("btn_show_html"))

    # ------------------------------------------------------------------ #
    #  Events                                                             #
    # ------------------------------------------------------------------ #

    def _on_toggle_html(self, event):
        self._switch_mode(not self._html_mode)

    def _on_all_keys(self, event: wx.KeyEvent):
        """ESC schließt, Tab navigiert Header-Felder."""
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.Close()
            return
        if key == wx.WXK_TAB:
            focused = self.FindFocus()
            if focused in self._tab_fields:
                shift    = event.ShiftDown()
                idx      = self._tab_fields.index(focused)
                next_idx = (idx - 1) % len(self._tab_fields) if shift \
                           else (idx + 1) % len(self._tab_fields)
                self._tab_fields[next_idx].SetFocus()
                return
        event.Skip()

    # ------------------------------------------------------------------ #
    #  Anhänge                                                            #
    # ------------------------------------------------------------------ #

    def _on_attach_ctx(self, event):
        menu = wx.Menu()
        mi_open     = menu.Append(wx.ID_ANY, "Öffnen")
        mi_save_one = menu.Append(wx.ID_ANY, "Anhang speichern…")
        mi_save_all = menu.Append(wx.ID_ANY, "Alle Anhänge speichern…")
        self.Bind(wx.EVT_MENU, self._on_attach_open,     mi_open)
        self.Bind(wx.EVT_MENU, self._on_attach_save_one, mi_save_one)
        self.Bind(wx.EVT_MENU, self._on_attach_save_all, mi_save_all)
        self.list_attach.PopupMenu(menu)
        menu.Destroy()

    def _on_attach_open(self, event=None):
        idx = self.list_attach.GetFirstSelected()
        if idx < 0: return
        atts = self.mail.get("attachments") or []
        if idx < len(atts) and atts[idx].get("data"):
            import tempfile, subprocess, sys
            fn  = atts[idx].get("filename", "attachment")
            tmp = os.path.join(tempfile.gettempdir(), fn)
            try:
                with open(tmp, "wb") as f: f.write(bytes(atts[idx]["data"]))
                if sys.platform == "win32": os.startfile(tmp)
                else: subprocess.Popen(["xdg-open", tmp])
            except Exception as e:
                wx.MessageBox(str(e), tr("error_title"), wx.OK | wx.ICON_ERROR, self)
        else:
            wx.MessageBox("Anhang-Daten nicht verfügbar.", tr("hint_title"), wx.OK, self)

    def _on_attach_save_one(self, event=None):
        idx = self.list_attach.GetFirstSelected()
        if idx < 0:
            wx.MessageBox("Bitte zuerst einen Anhang auswählen.", tr("hint_title"), wx.OK, self)
            return
        atts = self.mail.get("attachments") or []
        if idx < len(atts): self._save_attachment(atts[idx])

    def _on_attach_save_all(self, event=None):
        atts = self.mail.get("attachments") or []
        if not atts:
            wx.MessageBox("Keine Anhänge vorhanden.", tr("hint_title"), wx.OK, self)
            return
        with wx.DirDialog(self, "Zielordner für alle Anhänge:") as d:
            if d.ShowModal() != wx.ID_OK: return
            target = d.GetPath()
        saved = 0
        for att in atts:
            if att.get("data"):
                fn = att.get("filename", f"attachment_{saved}")
                try:
                    with open(os.path.join(target, fn), "wb") as f:
                        f.write(bytes(att["data"]))
                    saved += 1
                except Exception: pass
        wx.MessageBox(f"{saved} Anhang/Anhänge gespeichert.", tr("hint_title"), wx.OK, self)

    def _save_attachment(self, att: dict):
        fn = att.get("filename", "attachment")
        with wx.FileDialog(self, "Anhang speichern", defaultFile=fn,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as d:
            if d.ShowModal() != wx.ID_OK: return
            try:
                with open(d.GetPath(), "wb") as f:
                    f.write(bytes(att.get("data") or b""))
            except Exception as e:
                wx.MessageBox(str(e), tr("error_title"), wx.OK | wx.ICON_ERROR, self)

    @staticmethod
    def _fmt_size(size):
        if not size: return ""
        size = int(size)
        if size < 1024: return f"{size} B"
        if size < 1024*1024: return f"{size//1024} KB"
        return f"{size//(1024*1024)} MB"

    # ------------------------------------------------------------------ #
    #  Antworten / Weiterleiten                                          #
    # ------------------------------------------------------------------ #

    def _on_reply(self, event):
        from ui.dialogs import ComposeDialog
        if self.controller:
            dlg = ComposeDialog(self, self.controller, reply_to=self.mail)
            dlg.ShowModal(); dlg.Destroy()

    def _on_forward(self, event):
        from ui.dialogs import ComposeDialog
        if self.controller:
            dlg = ComposeDialog(self, self.controller, forward=self.mail)
            dlg.ShowModal(); dlg.Destroy()
