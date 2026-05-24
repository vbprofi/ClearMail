"""
MailPreviewPanel – Mail-Vorschau (unten rechts)

Screenreader-Optimierung:
  1. StaticText-Label wird ZUERST erzeugt (niedrigerer HWND-Index)
     → Windows AT-API (UIA/MSAA) verknüpft automatisch Label mit nachfolgendem Control
  2. SetName() auf jedem TextCtrl = Label-Text (expliziter Fallback für NVDA/JAWS)
  3. Tab-Stop für readonly TextCtrl: wx.TE_READONLY entfernt auf Windows den Tab-Stop!
     Lösung: wx.WANTS_CHARS NICHT setzen, stattdessen nach dem Erzeugen
     SetWindowStyleFlag mit dem Tab-Stop-Flag ergänzen (Windows: WS_TABSTOP = 0x00010000)
     Portabler Workaround: EVT_KEY_DOWN abfangen und Tab manuell weiterleiten.
"""

import wx
from datetime import datetime


class MailPreviewPanel(wx.Panel):

    def __init__(self, parent, controller):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.controller    = controller
        self._current_mail = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        # Überschrift
        lbl_header = wx.StaticText(self, label="Mail-Vorschau")
        lbl_header.SetFont(lbl_header.GetFont().Bold())
        outer.Add(lbl_header, 0, wx.ALL, 4)

        grid = wx.FlexGridSizer(cols=2, vgap=3, hgap=6)
        grid.AddGrowableCol(1)

        # Alle Header-Felder: Label ZUERST erzeugen, dann TextCtrl
        self.txt_from    = self._make_field(grid, "Von:",     "Von")
        self.txt_to      = self._make_field(grid, "An:",      "An")
        self.txt_cc      = self._make_field(grid, "CC:",      "CC")
        self.txt_subject = self._make_field(grid, "Betreff:", "Betreff")
        self.txt_date    = self._make_field(grid, "Datum:",   "Datum")
        self.txt_attach  = self._make_field(grid, "Anhang:",  "Anhang")

        outer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 4)

        # Nachrichtentext-Label ZUERST
        lbl_body = wx.StaticText(self, label="Nachrichtentext:")
        outer.Add(lbl_body, 0, wx.LEFT | wx.BOTTOM, 4)

        # Dann das multiline TextCtrl
        self.txt_body = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_AUTO_URL | wx.BORDER_SUNKEN
        )
        self.txt_body.SetName(
            "Nachrichtentext, schreibgeschützt. Shift+F6 wechselt den Bereich."
        )
        mono = wx.Font(10, wx.FONTFAMILY_TELETYPE,
                       wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.txt_body.SetFont(mono)
        outer.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 4)

        self.SetSizer(outer)

        # Tab-Navigation für readonly Felder manuell sicherstellen
        self._header_fields = [
            self.txt_from, self.txt_to, self.txt_cc,
            self.txt_subject, self.txt_date, self.txt_attach,
            self.txt_body,
        ]
        for ctrl in self._header_fields:
            ctrl.Bind(wx.EVT_KEY_DOWN, self._on_field_key)

    def _make_field(self, grid, label_text: str, name: str) -> wx.TextCtrl:
        """
        Erzeugt ERST StaticText (niedrigerer HWND), DANN TextCtrl.
        Windows UIA verknüpft so automatisch Label → Control.
        """
        # 1. Label zuerst
        lbl = wx.StaticText(self, label=label_text, size=(70, -1),
                            style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE)
        # 2. Control danach
        ctrl = wx.TextCtrl(self, style=wx.TE_READONLY | wx.BORDER_SIMPLE)
        ctrl.SetName(name)
        ctrl.SetToolTip(f"{label_text} schreibgeschützt, Tab springt zum nächsten Feld")

        grid.Add(lbl,  0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(ctrl, 1, wx.EXPAND)
        return ctrl

    def _on_field_key(self, event: wx.KeyEvent):
        """
        Manuelle Tab-Navigation für readonly TextCtrl-Felder.
        Verwendet GetEventObject() statt FindFocus() – zuverlässiger auf Windows.
        """
        key   = event.GetKeyCode()
        shift = event.ShiftDown()

        if key == wx.WXK_TAB:
            # GetEventObject() liefert immer das Control das den Event ausgelöst hat
            source = event.GetEventObject()
            fields = self._header_fields
            if source in fields:
                idx = fields.index(source)
                if shift:
                    next_idx = (idx - 1) % len(fields)
                else:
                    next_idx = (idx + 1) % len(fields)
                fields[next_idx].SetFocus()
            else:
                event.Skip()
            return

        event.Skip()

    # ------------------------------------------------------------------ #
    #  Daten                                                              #
    # ------------------------------------------------------------------ #

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
        self.txt_subject.SetValue(self._s(mail.get("subject"), "(kein Betreff)"))
        self.txt_date.SetValue(self._format_date(self._s(mail.get("date"))))
        self.txt_attach.SetValue("Ja" if mail.get("has_attach") else "Nein")

        body = self._s(mail.get("body_text")) or self._s(mail.get("body_html"))
        self.txt_body.SetValue(body)
        self.txt_body.SetInsertionPoint(0)

        self.txt_subject.SetName(
            f"Betreff: {self._s(mail.get('subject'), 'kein Betreff')}"
        )

    def clear(self):
        self._current_mail = None
        for ctrl in self._header_fields:
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
