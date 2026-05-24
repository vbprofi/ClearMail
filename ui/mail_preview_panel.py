"""
MailPreviewPanel – Untere rechte Seite: Mail-Vorschau
Screenreader-optimiert:
  - Readonly-TextCtrl-Felder für Von, An, Betreff, Datum
  - Tab-Navigation durch alle Felder
  - Mailtext als mehrzeiliges Readonly-Textfeld
"""

import wx


class MailPreviewPanel(wx.Panel):
    """Panel zur Anzeige einer ausgewählten E-Mail."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self._current_mail = None

        self._build_ui()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        lbl_header = wx.StaticText(self, label="Mail-Vorschau")
        lbl_header.SetFont(lbl_header.GetFont().Bold())
        outer.Add(lbl_header, 0, wx.ALL, 4)

        # Header-Felder (Tab-navigierbar, readonly)
        grid = wx.FlexGridSizer(cols=2, vgap=4, hgap=6)
        grid.AddGrowableCol(1)

        def make_field(label_text: str, name: str) -> wx.TextCtrl:
            lbl = wx.StaticText(self, label=label_text)
            ctrl = wx.TextCtrl(
                self,
                style=wx.TE_READONLY | wx.BORDER_NONE
            )
            ctrl.SetName(name)
            ctrl.SetBackgroundColour(self.GetBackgroundColour())
            ctrl.SetToolTip(f"{label_text} (schreibgeschützt, Tab zum Weiternavigieren)")
            grid.Add(lbl,  0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.txt_from    = make_field("Von:",     "Absender")
        self.txt_to      = make_field("An:",      "Empfänger")
        self.txt_cc      = make_field("CC:",      "CC")
        self.txt_subject = make_field("Betreff:", "Betreff")
        self.txt_date    = make_field("Datum:",   "Datum")
        self.txt_attach  = make_field("Anhang:",  "Anhang")

        outer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 4)

        # Mail-Text
        self.txt_body = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_AUTO_URL | wx.BORDER_SUNKEN
        )
        self.txt_body.SetName("Nachrichtentext, schreibgeschützt")
        self.txt_body.SetToolTip(
            "Nachrichtentext (schreibgeschützt). "
            "Shift+F6 kehrt zur Mail-Liste zurück."
        )
        # Monospace-Schrift für bessere Lesbarkeit im Screenreader
        mono = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.txt_body.SetFont(mono)

        outer.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 4)

        self.SetSizer(outer)

    # ------------------------------------------------------------------ #
    #  Daten anzeigen                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _s(value, default: str = "") -> str:
        """Konvertiert None-Werte (SQLite NULL) sicher zu str."""
        if value is None:
            return default
        return str(value)

    def show_mail(self, mail: dict):
        """Zeigt eine Mail in der Vorschau an."""
        self._current_mail = mail

        sender_name  = self._s(mail.get("sender_name"))
        sender_email = self._s(mail.get("sender"))
        if sender_name:
            from_str = f"{sender_name} <{sender_email}>"
        else:
            from_str = sender_email

        self.txt_from.SetValue(from_str)
        self.txt_to.SetValue(self._s(mail.get("recipients")))
        self.txt_cc.SetValue(self._s(mail.get("cc")))
        self.txt_subject.SetValue(self._s(mail.get("subject"), "(kein Betreff)"))
        self.txt_date.SetValue(self._format_date(self._s(mail.get("date"))))

        attach_str = "Ja" if mail.get("has_attach") else "Nein"
        self.txt_attach.SetValue(attach_str)

        body = self._s(mail.get("body_text")) or self._s(mail.get("body_html"))
        self.txt_body.SetValue(body)
        self.txt_body.SetInsertionPoint(0)

        # Accessible Announcement
        self.txt_subject.SetName(f"Betreff: {self._s(mail.get('subject'))}")

    def clear(self):
        """Leert alle Felder."""
        self._current_mail = None
        for ctrl in (
            self.txt_from, self.txt_to, self.txt_cc,
            self.txt_subject, self.txt_date, self.txt_attach, self.txt_body
        ):
            ctrl.SetValue("")

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_date(date_str: str) -> str:
        if not date_str:
            return ""
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%A, %d. %B %Y, %H:%M Uhr")
        except ValueError:
            return date_str
