"""
Dialoge des MailClients – alle Screenreader-optimiert.

Screenreader-Regel: Jedes Eingabefeld wird durch ein StaticText-Label
DIREKT davor im Tab-Order beschriftet. Zusätzlich wird SetName() auf dem
Control mit dem Label-Text gesetzt, damit NVDA/JAWS/Narrator ihn vorlesen.

Hilfsfunktion make_labeled_row() erzeugt konsequent:
  StaticText | Control  (in FlexGridSizer-Zeile)
und setzt SetName() auf dem Control.
"""

import wx
import wx.adv


# ------------------------------------------------------------------ #
#  Gemeinsame Hilfsfunktion                                           #
# ------------------------------------------------------------------ #

def make_labeled_row(parent, sizer: wx.FlexGridSizer,
                     label_text: str, ctrl: wx.Window,
                     ctrl_name: str = None):
    """
    Fügt eine Label+Control-Zeile in einen FlexGridSizer(cols=2) ein.
    Setzt SetName() auf ctrl, damit Screenreader den Label-Text vorlesen.
    """
    lbl = wx.StaticText(parent, label=label_text)
    sizer.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
    sizer.Add(ctrl, 1, wx.EXPAND)
    # Name = Label → AT liest "Label-Text: aktueller Wert"
    ctrl.SetName(ctrl_name or label_text.rstrip(":"))
    return ctrl


# ================================================================== #
#  AccountDialog                                                      #
# ================================================================== #

class AccountDialog(wx.Dialog):
    """Dialog zum Anlegen und Bearbeiten eines E-Mail-Kontos."""

    PROTOCOLS = ["IMAP", "POP3"]

    def __init__(self, parent, controller, account_id: int = None):
        title = "Konto bearbeiten" if account_id else "Neues Konto"
        super().__init__(parent, title=title, size=(500, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self.account_id = account_id
        self._build_ui()
        if account_id:
            self._load_account(account_id)
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        nb = wx.Notebook(panel)

        # ---- Seite 1: Allgemein ----
        page_gen = wx.Panel(nb)
        gs = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs.AddGrowableCol(1)

        self.txt_name  = wx.TextCtrl(page_gen)
        self.txt_email = wx.TextCtrl(page_gen)
        self.cho_proto = wx.Choice(page_gen, choices=self.PROTOCOLS)
        self.cho_proto.SetSelection(0)

        make_labeled_row(page_gen, gs, "Anzeigename:",    self.txt_name,  "Anzeigename")
        make_labeled_row(page_gen, gs, "E-Mail-Adresse:", self.txt_email, "E-Mail-Adresse")
        make_labeled_row(page_gen, gs, "Protokoll:",      self.cho_proto, "Protokoll")

        pg_sizer = wx.BoxSizer(wx.VERTICAL)
        pg_sizer.Add(gs, 1, wx.EXPAND | wx.ALL, 12)
        page_gen.SetSizer(pg_sizer)
        nb.AddPage(page_gen, "Allgemein")

        # ---- Seite 2: Posteingang ----
        page_in = wx.Panel(nb)
        gs2 = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs2.AddGrowableCol(1)

        self.txt_in_host = wx.TextCtrl(page_in)
        self.txt_in_port = wx.SpinCtrl(page_in, min=1, max=65535, initial=993)
        self.chk_in_ssl  = wx.CheckBox(page_in, label="SSL/TLS verwenden")
        self.chk_in_ssl.SetValue(True)
        self.txt_user    = wx.TextCtrl(page_in)
        self.txt_pass    = wx.TextCtrl(page_in, style=wx.TE_PASSWORD)

        make_labeled_row(page_in, gs2, "Eingangsserver:", self.txt_in_host, "Eingangsserver")
        make_labeled_row(page_in, gs2, "Port:",           self.txt_in_port, "Eingangsport")
        # Checkbox: volle Breite
        gs2.Add(wx.StaticText(page_in, label=""), 0)
        gs2.Add(self.chk_in_ssl, 0)
        self.chk_in_ssl.SetName("SSL für Eingang")
        make_labeled_row(page_in, gs2, "Benutzername:", self.txt_user, "Benutzername")
        make_labeled_row(page_in, gs2, "Passwort:",     self.txt_pass, "Passwort")

        pg2_sizer = wx.BoxSizer(wx.VERTICAL)
        pg2_sizer.Add(gs2, 1, wx.EXPAND | wx.ALL, 12)
        page_in.SetSizer(pg2_sizer)
        nb.AddPage(page_in, "Posteingang")

        # ---- Seite 3: SMTP ----
        page_out = wx.Panel(nb)
        gs3 = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs3.AddGrowableCol(1)

        self.txt_out_host = wx.TextCtrl(page_out)
        self.txt_out_port = wx.SpinCtrl(page_out, min=1, max=65535, initial=587)
        self.chk_out_ssl  = wx.CheckBox(page_out, label="SSL/TLS verwenden")
        self.chk_out_ssl.SetValue(True)

        make_labeled_row(page_out, gs3, "SMTP-Server:", self.txt_out_host, "SMTP-Server")
        make_labeled_row(page_out, gs3, "Port:",        self.txt_out_port, "SMTP-Port")
        gs3.Add(wx.StaticText(page_out, label=""), 0)
        gs3.Add(self.chk_out_ssl, 0)
        self.chk_out_ssl.SetName("SSL für Ausgang")

        pg3_sizer = wx.BoxSizer(wx.VERTICAL)
        pg3_sizer.Add(gs3, 1, wx.EXPAND | wx.ALL, 12)
        page_out.SetSizer(pg3_sizer)
        nb.AddPage(page_out, "Postausgang (SMTP)")

        sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)

        btn_sizer = wx.StdDialogButtonSizer()
        self.btn_ok     = wx.Button(panel, wx.ID_OK,     "Speichern")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Abbrechen")
        self.btn_ok.SetDefault()
        btn_sizer.AddButton(self.btn_ok)
        btn_sizer.AddButton(self.btn_cancel)
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 6)

        panel.SetSizer(sizer)
        self.btn_ok.Bind(wx.EVT_BUTTON, self._on_save)

        # Erster Fokus: Anzeigename
        self.txt_name.SetFocus()

    def _load_account(self, account_id: int):
        acc = self.controller.get_account(account_id)
        if not acc:
            return
        self.txt_name.SetValue(str(acc["name"] or ""))
        self.txt_email.SetValue(str(acc["email"] or ""))
        proto_idx = self.PROTOCOLS.index(acc["protocol"]) if acc["protocol"] in self.PROTOCOLS else 0
        self.cho_proto.SetSelection(proto_idx)
        self.txt_in_host.SetValue(str(acc["in_host"] or ""))
        self.txt_in_port.SetValue(acc["in_port"] or 993)
        self.chk_in_ssl.SetValue(bool(acc["in_ssl"]))
        self.txt_out_host.SetValue(str(acc["out_host"] or ""))
        self.txt_out_port.SetValue(acc["out_port"] or 587)
        self.chk_out_ssl.SetValue(bool(acc["out_ssl"]))
        self.txt_user.SetValue(str(acc["username"] or ""))
        self.txt_pass.SetValue(str(acc["password"] or ""))

    def _on_save(self, event):
        data = {
            "id":       self.account_id,
            "name":     self.txt_name.GetValue().strip(),
            "email":    self.txt_email.GetValue().strip(),
            "protocol": self.PROTOCOLS[self.cho_proto.GetSelection()],
            "in_host":  self.txt_in_host.GetValue().strip(),
            "in_port":  self.txt_in_port.GetValue(),
            "in_ssl":   1 if self.chk_in_ssl.GetValue() else 0,
            "out_host": self.txt_out_host.GetValue().strip(),
            "out_port": self.txt_out_port.GetValue(),
            "out_ssl":  1 if self.chk_out_ssl.GetValue() else 0,
            "username": self.txt_user.GetValue().strip(),
            "password": self.txt_pass.GetValue(),
        }
        if not data["name"] or not data["email"]:
            wx.MessageBox("Bitte Anzeigename und E-Mail-Adresse angeben.",
                          "Pflichtfelder", wx.OK | wx.ICON_WARNING, self)
            return
        self.controller.save_account(data)
        self.EndModal(wx.ID_OK)


# ================================================================== #
#  SettingsDialog                                                     #
# ================================================================== #

class SettingsDialog(wx.Dialog):
    """Dialog für Anwendungseinstellungen."""

    def __init__(self, parent, controller):
        super().__init__(parent, title="Einstellungen", size=(460, 400),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._load_settings()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        nb    = wx.Notebook(panel)

        # ---- Allgemein ----
        pg = wx.Panel(nb)
        gs = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs.AddGrowableCol(1)

        self.chk_auto_fetch  = wx.CheckBox(pg, label="E-Mails automatisch abrufen")
        self.chk_auto_fetch.SetName("Automatischer Abruf")
        self.spn_interval    = wx.SpinCtrl(pg, min=1, max=60, initial=10)
        self.chk_html        = wx.CheckBox(pg, label="HTML-Mails rendern")
        self.chk_html.SetName("HTML-Darstellung")
        self.chk_confirm_del = wx.CheckBox(pg, label="Löschen bestätigen")
        self.chk_confirm_del.SetName("Löschbestätigung")

        gs.Add(self.chk_auto_fetch, 0, wx.ALIGN_CENTER_VERTICAL)
        gs.Add(wx.StaticText(pg, label=""), 0)
        make_labeled_row(pg, gs, "Abrufintervall (Minuten):", self.spn_interval, "Abrufintervall")
        gs.Add(self.chk_html, 0)
        gs.Add(wx.StaticText(pg, label=""), 0)
        gs.Add(self.chk_confirm_del, 0)
        gs.Add(wx.StaticText(pg, label=""), 0)

        pg_s = wx.BoxSizer(wx.VERTICAL)
        pg_s.Add(gs, 1, wx.EXPAND | wx.ALL, 12)
        pg.SetSizer(pg_s)
        nb.AddPage(pg, "Allgemein")

        # ---- Darstellung ----
        pg2 = wx.Panel(nb)
        gs2 = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs2.AddGrowableCol(1)
        self.spn_font_size = wx.SpinCtrl(pg2, min=8, max=24, initial=10)
        make_labeled_row(pg2, gs2, "Schriftgröße (Vorschau):", self.spn_font_size, "Schriftgröße")
        pg2_s = wx.BoxSizer(wx.VERTICAL)
        pg2_s.Add(gs2, 1, wx.EXPAND | wx.ALL, 12)
        pg2.SetSizer(pg2_s)
        nb.AddPage(pg2, "Darstellung")

        sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok     = wx.Button(panel, wx.ID_OK,     "Speichern")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Abbrechen")
        btn_ok.SetDefault()
        btn_ok.SetName("Speichern")
        btn_cancel.SetName("Abbrechen")
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 6)
        panel.SetSizer(sizer)
        btn_ok.Bind(wx.EVT_BUTTON, self._on_save)

    def _load_settings(self):
        self.chk_auto_fetch.SetValue(self.controller.get_setting("auto_fetch",     "0") == "1")
        self.spn_interval.SetValue(int(self.controller.get_setting("fetch_interval", "10")))
        self.chk_html.SetValue(self.controller.get_setting("render_html",          "0") == "1")
        self.chk_confirm_del.SetValue(self.controller.get_setting("confirm_delete", "1") == "1")
        self.spn_font_size.SetValue(int(self.controller.get_setting("font_size",    "10")))

    def _on_save(self, event):
        self.controller.set_setting("auto_fetch",     "1" if self.chk_auto_fetch.GetValue() else "0")
        self.controller.set_setting("fetch_interval", str(self.spn_interval.GetValue()))
        self.controller.set_setting("render_html",    "1" if self.chk_html.GetValue() else "0")
        self.controller.set_setting("confirm_delete", "1" if self.chk_confirm_del.GetValue() else "0")
        self.controller.set_setting("font_size",      str(self.spn_font_size.GetValue()))
        self.EndModal(wx.ID_OK)


# ================================================================== #
#  PrintPreviewDialog                                                 #
# ================================================================== #

class PrintPreviewDialog(wx.Dialog):
    """Einfache Druckansicht einer E-Mail."""

    def __init__(self, parent, mail: dict):
        super().__init__(parent, title="Druckansicht", size=(620, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.mail = mail
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label="Druckansicht")
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 8)

        txt = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN)
        txt.SetName("Druckvorschau, schreibgeschützt")
        s = self.mail
        content = (
            f"Von:     {s.get('sender_name','') or ''} <{s.get('sender','') or ''}>\n"
            f"An:      {s.get('recipients','') or ''}\n"
            f"Betreff: {s.get('subject','') or ''}\n"
            f"Datum:   {s.get('date','') or ''}\n"
            f"\n{'─'*60}\n\n"
            f"{s.get('body_text','') or ''}"
        )
        txt.SetValue(content)
        sizer.Add(txt, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_print = wx.Button(panel, label="&Drucken")
        btn_print.SetName("Drucken")
        btn_close = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
        btn_close.SetName("Schließen")
        btn_sizer.Add(btn_print, 0, wx.RIGHT, 8)
        btn_sizer.Add(btn_close, 0)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        btn_print.Bind(wx.EVT_BUTTON, self._on_print)
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        panel.SetSizer(sizer)
        txt.SetFocus()

    def _on_print(self, event):
        wx.MessageBox(
            "Druckfunktion noch nicht vollständig implementiert.\n"
            "Bitte Strg+A → Strg+C und aus einem Texteditor drucken.",
            "Drucken", wx.OK | wx.ICON_INFORMATION, self
        )


# ================================================================== #
#  PGPDialog                                                          #
# ================================================================== #

class PGPDialog(wx.Dialog):
    """OpenPGP-Schlüsselverwaltung (Platzhalter)."""

    def __init__(self, parent):
        super().__init__(parent, title="OpenPGP-Schlüsselverwaltung", size=(520, 400),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(panel, label=(
            "OpenPGP-Integration (Platzhalter)\n\n"
            "Geplante Funktionen:\n"
            "  • Schlüsselpaar generieren\n"
            "  • Öffentlichen Schlüssel importieren/exportieren\n"
            "  • Schlüsselserver durchsuchen\n"
            "  • Signierte Mails verifizieren\n"
            "  • Verschlüsselte Mails entschlüsseln\n\n"
            "Implementierung über Addon-System oder python-gnupg."
        ))
        sizer.Add(info, 0, wx.ALL, 14)

        self.list_keys = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list_keys.SetName("PGP-Schlüsselliste")
        self.list_keys.InsertColumn(0, "Name / E-Mail", width=250)
        self.list_keys.InsertColumn(1, "Schlüssel-ID",   width=130)
        self.list_keys.InsertColumn(2, "Gültig bis",    width=80)
        sizer.Add(self.list_keys, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_import = wx.Button(panel, label="&Importieren")
        btn_import.SetName("Schlüssel importieren")
        btn_export = wx.Button(panel, label="&Exportieren")
        btn_export.SetName("Schlüssel exportieren")
        btn_close  = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
        btn_close.SetName("Schließen")
        btn_sizer.Add(btn_import, 0, wx.RIGHT, 6)
        btn_sizer.Add(btn_export, 0, wx.RIGHT, 6)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_close)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        for b in (btn_import, btn_export):
            b.Bind(wx.EVT_BUTTON, lambda e: wx.MessageBox(
                "Noch nicht implementiert.", "Hinweis", wx.OK, self))
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        panel.SetSizer(sizer)


# ================================================================== #
#  AddonManagerDialog                                                 #
# ================================================================== #

class AddonManagerDialog(wx.Dialog):
    """Addon-Verwaltung."""

    def __init__(self, parent, controller):
        super().__init__(parent, title="Addon-Verwaltung", size=(540, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._load_addons()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label=(
            "Installierte Addons. Addons werden aus ~/.mailclient/addons/ geladen.\n"
            "Jedes Addon-Verzeichnis braucht eine __init__.py mit Klasse Addon(AddonBase)."
        ))
        sizer.Add(lbl, 0, wx.ALL, 8)

        self.list_addons = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_addons.SetName("Addon-Liste")
        self.list_addons.InsertColumn(0, "Name",          width=180)
        self.list_addons.InsertColumn(1, "Version",       width=70)
        self.list_addons.InsertColumn(2, "Status",        width=80)
        self.list_addons.InsertColumn(3, "Beschreibung",  width=180)
        sizer.Add(self.list_addons, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_install = wx.Button(panel, label="&Installieren...")
        btn_install.SetName("Addon installieren")
        btn_close   = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
        btn_close.SetName("Schließen")
        btn_sizer.Add(btn_install, 0, wx.RIGHT, 6)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_close)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        btn_install.Bind(wx.EVT_BUTTON, self._on_install)
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        panel.SetSizer(sizer)

    def _load_addons(self):
        self.list_addons.DeleteAllItems()
        loaded    = self.controller.addon_mgr.get_loaded_addons()
        available = self.controller.addon_mgr.scan_addon_dir()

        for name in available:
            addon   = loaded.get(name)
            version = addon.VERSION if addon else "–"
            status  = "Aktiv" if addon else "Inaktiv"
            desc    = addon.DESCRIPTION if addon else ""
            idx = self.list_addons.InsertItem(self.list_addons.GetItemCount(), name)
            self.list_addons.SetItem(idx, 1, version)
            self.list_addons.SetItem(idx, 2, status)
            self.list_addons.SetItem(idx, 3, desc)

        if not available:
            self.list_addons.InsertItem(0, "(Keine Addons gefunden)")

    def _on_install(self, event):
        wx.MessageBox(
            "Kopieren Sie das Addon-Verzeichnis nach\n"
            "~/.mailclient/addons/ und starten Sie MailClient neu.",
            "Addon installieren", wx.OK | wx.ICON_INFORMATION, self
        )


# ================================================================== #
#  AboutDialog                                                        #
# ================================================================== #

class AboutDialog(wx.Dialog):
    """Über-Dialog."""

    def __init__(self, parent):
        super().__init__(parent, title="Über MailClient", size=(400, 300),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, label="MailClient")
        title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT,
                              wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        sizer.Add(title, 0, wx.ALIGN_CENTER | wx.TOP, 20)

        info = wx.StaticText(panel, label=(
            "Version 1.0.0 (Entwicklungsversion)\n\n"
            "Screenreader-optimierter E-Mail-Client\n"
            "Python 3.12 + wxPython\n\n"
            "Protokolle: IMAP, POP3, SMTP (vorbereitet)\n"
            "Datenbank: SQLite | Erweiterbar durch Addons"
        ), style=wx.ALIGN_CENTER)
        sizer.Add(info, 1, wx.ALIGN_CENTER | wx.ALL, 16)

        btn_close = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
        btn_close.SetName("Schließen")
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        sizer.Add(btn_close, 0, wx.ALIGN_CENTER | wx.BOTTOM, 16)
        panel.SetSizer(sizer)


# ================================================================== #
#  ComposeDialog                                                      #
# ================================================================== #

class ComposeDialog(wx.Dialog):
    """Dialog zum Verfassen einer neuen E-Mail."""

    def __init__(self, parent, controller, reply_to: dict = None,
                 reply_all: bool = False, forward: dict = None):
        title = "Antworten" if reply_to else ("Weiterleiten" if forward else "Neue E-Mail")
        super().__init__(parent, title=title, size=(640, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self.reply_to   = reply_to
        self.forward    = forward

        self._build_ui()
        self._prefill(reply_to, reply_all, forward)
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        gs = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        gs.AddGrowableCol(1)

        accounts     = self.controller.get_accounts()
        from_choices = [f"{a['name']} <{a['email']}>" for a in accounts] or ["(Kein Konto)"]
        self.cho_from    = wx.Choice(panel, choices=from_choices)
        self.cho_from.SetSelection(0)
        self.txt_to      = wx.TextCtrl(panel)
        self.txt_cc      = wx.TextCtrl(panel)
        self.txt_subject = wx.TextCtrl(panel)

        make_labeled_row(panel, gs, "Von:",     self.cho_from,    "Von")
        make_labeled_row(panel, gs, "An:",      self.txt_to,      "An")
        make_labeled_row(panel, gs, "CC:",      self.txt_cc,      "CC")
        make_labeled_row(panel, gs, "Betreff:", self.txt_subject, "Betreff")

        sizer.Add(gs, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        lbl_body = wx.StaticText(panel, label="Nachrichtentext:")
        sizer.Add(lbl_body, 0, wx.LEFT | wx.TOP, 8)

        self.txt_body = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.BORDER_SUNKEN)
        self.txt_body.SetName("Nachrichtentext")
        self.txt_body.SetMinSize((-1, 200))
        sizer.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_send    = wx.Button(panel, label="&Senden")
        btn_send.SetName("E-Mail senden")
        btn_attach  = wx.Button(panel, label="&Anhang hinzufügen")
        btn_attach.SetName("Anhang hinzufügen")
        btn_discard = wx.Button(panel, wx.ID_CANCEL, "Verwerfen")
        btn_discard.SetName("Verwerfen und schließen")

        btn_sizer.Add(btn_send,   0, wx.RIGHT, 8)
        btn_sizer.Add(btn_attach, 0, wx.RIGHT, 8)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_discard)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        btn_send.Bind(wx.EVT_BUTTON,   self._on_send)
        btn_attach.Bind(wx.EVT_BUTTON, self._on_attach)
        panel.SetSizer(sizer)

        self.txt_to.SetFocus()

    def _prefill(self, reply_to, reply_all, forward):
        if reply_to:
            self.txt_to.SetValue(str(reply_to.get("sender") or ""))
            if reply_all:
                self.txt_cc.SetValue(str(reply_to.get("recipients") or ""))
            subj = str(reply_to.get("subject") or "")
            self.txt_subject.SetValue(("Re: " + subj) if not subj.startswith("Re:") else subj)
            orig = (
                f"\n\n──────────────────────────────\n"
                f"Von: {reply_to.get('sender_name','') or ''} <{reply_to.get('sender','') or ''}>\n"
                f"Datum: {reply_to.get('date','') or ''}\n\n"
                f"{reply_to.get('body_text','') or ''}"
            )
            self.txt_body.SetValue(orig)
            self.txt_body.SetInsertionPoint(0)

        elif forward:
            subj = str(forward.get("subject") or "")
            self.txt_subject.SetValue(("Fwd: " + subj) if not subj.startswith("Fwd:") else subj)
            orig = (
                f"\n\n──────────────────────────────\n"
                f"Von: {forward.get('sender_name','') or ''} <{forward.get('sender','') or ''}>\n"
                f"An: {forward.get('recipients','') or ''}\n"
                f"Datum: {forward.get('date','') or ''}\n\n"
                f"{forward.get('body_text','') or ''}"
            )
            self.txt_body.SetValue(orig)

    def _on_send(self, event):
        if not self.txt_to.GetValue().strip():
            wx.MessageBox("Bitte eine Empfängeradresse angeben.",
                          "Pflichtfeld", wx.OK | wx.ICON_WARNING, self)
            return
        wx.MessageBox(
            "SMTP-Versand noch nicht implementiert.\n\n"
            "Das SMTP-Modul kann in protocols/pop3_smtp_handler.py ergänzt werden.",
            "Nicht implementiert", wx.OK | wx.ICON_INFORMATION, self
        )

    def _on_attach(self, event):
        with wx.FileDialog(self, "Anhang auswählen",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as d:
            if d.ShowModal() == wx.ID_OK:
                wx.MessageBox(
                    f"{len(d.GetPaths())} Datei(en) ausgewählt.\n"
                    "Anhang-Unterstützung wird mit dem SMTP-Modul implementiert.",
                    "Anhang", wx.OK | wx.ICON_INFORMATION, self
                )
