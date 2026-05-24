"""
MailPreviewPanel – Mail-Vorschau (unten rechts)

Screenreader-Optimierung:
  - StaticText direkt im gleichen Panel vor dem TextCtrl → AT liest Label
  - SetName() auf jedem TextCtrl = Label-Text (Fallback für alle AT)
  - Tab-Reihenfolge ergibt sich aus der Erstellungsreihenfolge im Panel
  - KEIN MoveAfterInTabOrder (Controls müssen direkte Geschwister sein)
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
    #  UI – alle Controls direkt in diesem Panel (keine Sub-Panels)       #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        # Überschrift
        lbl_header = wx.StaticText(self, label="Mail-Vorschau")
        lbl_header.SetFont(lbl_header.GetFont().Bold())
        outer.Add(lbl_header, 0, wx.ALL, 4)

        # ---- Header-Grid: StaticText + TextCtrl direkt im selben Panel ----
        # FlexGridSizer(cols=2): Spalte 0 = Label, Spalte 1 = Feld
        # Tab-Reihenfolge = Erstellungsreihenfolge der TextCtrl-Objekte
        grid = wx.FlexGridSizer(cols=2, vgap=3, hgap=6)
        grid.AddGrowableCol(1)

        def add_field(label_text: str, name: str) -> wx.TextCtrl:
            # StaticText VOR TextCtrl → AT liest sie als Beschriftung
            lbl = wx.StaticText(self, label=label_text, size=(70, -1),
                                style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE)
            ctrl = wx.TextCtrl(self, style=wx.TE_READONLY | wx.BORDER_SIMPLE)
            ctrl.SetName(name)          # Name = Label-Text → NVDA/JAWS/Narrator
            ctrl.SetToolTip(f"{label_text} (schreibgeschützt)")
            grid.Add(lbl,  0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        # Reihenfolge = Tab-Reihenfolge
        self.txt_from    = add_field("Von:",     "Von")
        self.txt_to      = add_field("An:",      "An")
        self.txt_cc      = add_field("CC:",      "CC")
        self.txt_subject = add_field("Betreff:", "Betreff")
        self.txt_date    = add_field("Datum:",   "Datum")
        self.txt_attach  = add_field("Anhang:",  "Anhang")

        outer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 4)

        # ---- Nachrichtentext ----
        lbl_body = wx.StaticText(self, label="Nachrichtentext:")
        outer.Add(lbl_body, 0, wx.LEFT | wx.BOTTOM, 4)

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

    # ------------------------------------------------------------------ #
    #  Daten anzeigen                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _s(value, default: str = "") -> str:
        """None (SQLite NULL) → leerer String."""
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

        # Screenreader: aktuellen Betreff im Namen verankern
        self.txt_subject.SetName(f"Betreff: {self._s(mail.get('subject'), 'kein Betreff')}")

    def clear(self):
        self._current_mail = None
        for ctrl in (self.txt_from, self.txt_to, self.txt_cc,
                     self.txt_subject, self.txt_date, self.txt_attach, self.txt_body):
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
