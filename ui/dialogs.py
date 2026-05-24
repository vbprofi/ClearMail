"""
Dialoge des MailClients:
  - AccountDialog        – Konto anlegen/bearbeiten
  - SettingsDialog       – Anwendungseinstellungen
  - PrintPreviewDialog   – Druckansicht einer Mail
  - PGPDialog            – OpenPGP-Schlüsselverwaltung
  - AddonManagerDialog   – Addon-Verwaltung
  - AboutDialog          – Über das Programm
  - ComposeDialog        – Neue Mail verfassen / Antworten / Weiterleiten
"""

import wx
import wx.adv


# ================================================================== #
#  AccountDialog                                                      #
# ================================================================== #

class AccountDialog(wx.Dialog):
    """Dialog zum Anlegen und Bearbeiten eines E-Mail-Kontos."""

    PROTOCOLS = ["IMAP", "POP3"]

    def __init__(self, parent, controller, account_id: int = None):
        title = "Konto bearbeiten" if account_id else "Neues Konto"
        super().__init__(parent, title=title, size=(480, 520),
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

        # Seite 1: Allgemein
        page_gen = wx.Panel(nb)
        gs = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        gs.AddGrowableCol(1)

        def add_row(label, ctrl):
            gs.Add(wx.StaticText(page_gen, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            gs.Add(ctrl, 1, wx.EXPAND)

        self.txt_name    = wx.TextCtrl(page_gen)
        self.txt_name.SetName("Anzeigename")
        self.txt_email   = wx.TextCtrl(page_gen)
        self.txt_email.SetName("E-Mail-Adresse")
        self.cho_proto   = wx.Choice(page_gen, choices=self.PROTOCOLS)
        self.cho_proto.SetName("Protokoll")
        self.cho_proto.SetSelection(0)

        add_row("Anzeigename:", self.txt_name)
        add_row("E-Mail-Adresse:", self.txt_email)
        add_row("Protokoll:", self.cho_proto)

        page_gen.SetSizer(wx.BoxSizer(wx.VERTICAL))
        page_gen.GetSizer().Add(gs, 1, wx.EXPAND | wx.ALL, 10)
        nb.AddPage(page_gen, "Allgemein")

        # Seite 2: Posteingang
        page_in = wx.Panel(nb)
        gs2 = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        gs2.AddGrowableCol(1)

        def add_row2(label, ctrl):
            gs2.Add(wx.StaticText(page_in, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            gs2.Add(ctrl, 1, wx.EXPAND)

        self.txt_in_host = wx.TextCtrl(page_in)
        self.txt_in_host.SetName("Eingangsserver")
        self.txt_in_port = wx.SpinCtrl(page_in, min=1, max=65535, initial=993)
        self.txt_in_port.SetName("Eingangsport")
        self.chk_in_ssl  = wx.CheckBox(page_in, label="SSL/TLS verwenden")
        self.chk_in_ssl.SetName("SSL für Eingang")
        self.chk_in_ssl.SetValue(True)
        self.txt_user    = wx.TextCtrl(page_in)
        self.txt_user.SetName("Benutzername")
        self.txt_pass    = wx.TextCtrl(page_in, style=wx.TE_PASSWORD)
        self.txt_pass.SetName("Passwort")

        add_row2("Eingangsserver:", self.txt_in_host)
        add_row2("Port:", self.txt_in_port)
        gs2.Add(wx.StaticText(page_in, label=""), 0)
        gs2.Add(self.chk_in_ssl, 0)
        add_row2("Benutzername:", self.txt_user)
        add_row2("Passwort:", self.txt_pass)

        page_in.SetSizer(wx.BoxSizer(wx.VERTICAL))
        page_in.GetSizer().Add(gs2, 1, wx.EXPAND | wx.ALL, 10)
        nb.AddPage(page_in, "Posteingang")

        # Seite 3: Postausgang SMTP
        page_out = wx.Panel(nb)
        gs3 = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        gs3.AddGrowableCol(1)

        def add_row3(label, ctrl):
            gs3.Add(wx.StaticText(page_out, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            gs3.Add(ctrl, 1, wx.EXPAND)

        self.txt_out_host= wx.TextCtrl(page_out)
        self.txt_out_host.SetName("SMTP-Server")
        self.txt_out_port= wx.SpinCtrl(page_out, min=1, max=65535, initial=587)
        self.txt_out_port.SetName("SMTP-Port")
        self.chk_out_ssl = wx.CheckBox(page_out, label="SSL/TLS verwenden")
        self.chk_out_ssl.SetName("SSL für Ausgang")
        self.chk_out_ssl.SetValue(True)

        add_row3("SMTP-Server:", self.txt_out_host)
        add_row3("Port:", self.txt_out_port)
        gs3.Add(wx.StaticText(page_out, label=""), 0)
        gs3.Add(self.chk_out_ssl, 0)

        page_out.SetSizer(wx.BoxSizer(wx.VERTICAL))
        page_out.GetSizer().Add(gs3, 1, wx.EXPAND | wx.ALL, 10)
        nb.AddPage(page_out, "Postausgang (SMTP)")

        sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)

        # Buttons
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok     = wx.Button(panel, wx.ID_OK,     "Speichern")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Abbrechen")
        btn_ok.SetDefault()
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 6)

        panel.SetSizer(sizer)
        btn_ok.Bind(wx.EVT_BUTTON, self._on_save)

    def _load_account(self, account_id: int):
        acc = self.controller.get_account(account_id)
        if not acc:
            return
        self.txt_name.SetValue(acc["name"] or "")
        self.txt_email.SetValue(acc["email"] or "")
        proto_idx = self.PROTOCOLS.index(acc["protocol"]) if acc["protocol"] in self.PROTOCOLS else 0
        self.cho_proto.SetSelection(proto_idx)
        self.txt_in_host.SetValue(acc["in_host"] or "")
        self.txt_in_port.SetValue(acc["in_port"] or 993)
        self.chk_in_ssl.SetValue(bool(acc["in_ssl"]))
        self.txt_out_host.SetValue(acc["out_host"] or "")
        self.txt_out_port.SetValue(acc["out_port"] or 587)
        self.chk_out_ssl.SetValue(bool(acc["out_ssl"]))
        self.txt_user.SetValue(acc["username"] or "")
        self.txt_pass.SetValue(acc["password"] or "")

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
            wx.MessageBox("Bitte Name und E-Mail-Adresse angeben.", "Pflichtfelder", wx.OK | wx.ICON_WARNING, self)
            return
        self.controller.save_account(data)
        self.EndModal(wx.ID_OK)


# ================================================================== #
#  SettingsDialog                                                     #
# ================================================================== #

class SettingsDialog(wx.Dialog):
    """Dialog für Anwendungseinstellungen."""

    def __init__(self, parent, controller):
        super().__init__(parent, title="Einstellungen", size=(440, 380),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._load_settings()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        nb    = wx.Notebook(panel)

        # Allgemein
        pg = wx.Panel(nb)
        gs = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs.AddGrowableCol(1)

        self.chk_auto_fetch = wx.CheckBox(pg, label="E-Mails automatisch abrufen")
        self.chk_auto_fetch.SetName("Automatischer Abruf")
        self.spn_interval   = wx.SpinCtrl(pg, min=1, max=60, initial=10)
        self.spn_interval.SetName("Abrufintervall in Minuten")
        self.chk_html       = wx.CheckBox(pg, label="HTML-Mails rendern")
        self.chk_html.SetName("HTML-Darstellung")
        self.chk_confirm_del = wx.CheckBox(pg, label="Löschen bestätigen")
        self.chk_confirm_del.SetName("Löschbestätigung")

        gs.Add(self.chk_auto_fetch, 0, wx.ALIGN_CENTER_VERTICAL)
        gs.Add(wx.StaticText(pg, label=""), 0)
        gs.Add(wx.StaticText(pg, label="Intervall (Minuten):"), 0, wx.ALIGN_CENTER_VERTICAL)
        gs.Add(self.spn_interval, 1, wx.EXPAND)
        gs.Add(self.chk_html, 0)
        gs.Add(wx.StaticText(pg, label=""), 0)
        gs.Add(self.chk_confirm_del, 0)
        gs.Add(wx.StaticText(pg, label=""), 0)

        pg.SetSizer(wx.BoxSizer(wx.VERTICAL))
        pg.GetSizer().Add(gs, 1, wx.EXPAND | wx.ALL, 10)
        nb.AddPage(pg, "Allgemein")

        # Darstellung
        pg2  = wx.Panel(nb)
        gs2  = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs2.AddGrowableCol(1)
        self.spn_font_size = wx.SpinCtrl(pg2, min=8, max=24, initial=10)
        self.spn_font_size.SetName("Schriftgröße")
        gs2.Add(wx.StaticText(pg2, label="Schriftgröße:"), 0, wx.ALIGN_CENTER_VERTICAL)
        gs2.Add(self.spn_font_size, 1, wx.EXPAND)
        pg2.SetSizer(wx.BoxSizer(wx.VERTICAL))
        pg2.GetSizer().Add(gs2, 1, wx.EXPAND | wx.ALL, 10)
        nb.AddPage(pg2, "Darstellung")

        sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok     = wx.Button(panel, wx.ID_OK,     "Speichern")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Abbrechen")
        btn_ok.SetDefault()
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 6)
        panel.SetSizer(sizer)
        btn_ok.Bind(wx.EVT_BUTTON, self._on_save)

    def _load_settings(self):
        self.chk_auto_fetch.SetValue(self.controller.get_setting("auto_fetch", "0") == "1")
        self.spn_interval.SetValue(int(self.controller.get_setting("fetch_interval", "10")))
        self.chk_html.SetValue(self.controller.get_setting("render_html", "0") == "1")
        self.chk_confirm_del.SetValue(self.controller.get_setting("confirm_delete", "1") == "1")
        self.spn_font_size.SetValue(int(self.controller.get_setting("font_size", "10")))

    def _on_save(self, event):
        self.controller.set_setting("auto_fetch",      "1" if self.chk_auto_fetch.GetValue() else "0")
        self.controller.set_setting("fetch_interval",  str(self.spn_interval.GetValue()))
        self.controller.set_setting("render_html",     "1" if self.chk_html.GetValue() else "0")
        self.controller.set_setting("confirm_delete",  "1" if self.chk_confirm_del.GetValue() else "0")
        self.controller.set_setting("font_size",       str(self.spn_font_size.GetValue()))
        self.EndModal(wx.ID_OK)


# ================================================================== #
#  PrintPreviewDialog                                                 #
# ================================================================== #

class PrintPreviewDialog(wx.Dialog):
    """Einfache Druckansicht einer E-Mail."""

    def __init__(self, parent, mail: dict):
        super().__init__(parent, title="Druckansicht", size=(600, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.mail = mail
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label="Druckansicht (Vorschau)")
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 8)

        txt = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN)
        txt.SetName("Druckvorschau")

        content = (
            f"Von:     {self.mail.get('sender_name', '')} <{self.mail.get('sender', '')}>\n"
            f"An:      {self.mail.get('recipients', '')}\n"
            f"Betreff: {self.mail.get('subject', '')}\n"
            f"Datum:   {self.mail.get('date', '')}\n"
            f"\n{'─'*60}\n\n"
            f"{self.mail.get('body_text', '')}"
        )
        txt.SetValue(content)
        sizer.Add(txt, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_print = wx.Button(panel, label="&Drucken")
        btn_print.SetName("Drucken")
        btn_close = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
        btn_sizer.Add(btn_print, 0, wx.RIGHT, 8)
        btn_sizer.Add(btn_close, 0)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        btn_print.Bind(wx.EVT_BUTTON, self._on_print)
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        panel.SetSizer(sizer)

    def _on_print(self, event):
        # TODO: wx.Printer / wx.PrintData integrieren
        wx.MessageBox(
            "Druckfunktion noch nicht vollständig implementiert.\n"
            "Bitte nutzen Sie Strg+A, Strg+C zum Kopieren und drucken Sie aus einem Texteditor.",
            "Drucken",
            wx.OK | wx.ICON_INFORMATION,
            self
        )


# ================================================================== #
#  PGPDialog                                                          #
# ================================================================== #

class PGPDialog(wx.Dialog):
    """OpenPGP-Schlüsselverwaltung (Platzhalter)."""

    def __init__(self, parent):
        super().__init__(parent, title="OpenPGP-Schlüsselverwaltung", size=(500, 380),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(panel,
            label=(
                "OpenPGP-Integration (Platzhalter)\n\n"
                "Geplante Funktionen:\n"
                "  • Schlüsselpaar generieren\n"
                "  • Öffentlichen Schlüssel importieren/exportieren\n"
                "  • Schlüsselserver durchsuchen\n"
                "  • Signierte Mails verifizieren\n"
                "  • Verschlüsselte Mails entschlüsseln\n\n"
                "Implementierung erfolgt über das Addon-System\n"
                "oder eine direkte python-gnupg-Integration."
            )
        )
        sizer.Add(info, 1, wx.EXPAND | wx.ALL, 16)

        # Schlüsselliste (leer)
        self.list_keys = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list_keys.SetName("PGP-Schlüsselliste")
        self.list_keys.InsertColumn(0, "Name/E-Mail", width=250)
        self.list_keys.InsertColumn(1, "Schlüssel-ID",  width=130)
        self.list_keys.InsertColumn(2, "Gültig bis",   width=80)
        sizer.Add(self.list_keys, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_import = wx.Button(panel, label="Importieren")
        btn_import.SetName("Schlüssel importieren")
        btn_export = wx.Button(panel, label="Exportieren")
        btn_export.SetName("Schlüssel exportieren")
        btn_close  = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
        btn_sizer.Add(btn_import, 0, wx.RIGHT, 6)
        btn_sizer.Add(btn_export, 0, wx.RIGHT, 6)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_close)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        for btn in (btn_import, btn_export):
            btn.Bind(wx.EVT_BUTTON, lambda e: wx.MessageBox(
                "Noch nicht implementiert.", "Hinweis", wx.OK, self))
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        panel.SetSizer(sizer)


# ================================================================== #
#  AddonManagerDialog                                                 #
# ================================================================== #

class AddonManagerDialog(wx.Dialog):
    """Addon-Verwaltung."""

    def __init__(self, parent, controller):
        super().__init__(parent, title="Addon-Verwaltung", size=(520, 400),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._load_addons()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label=(
            "Installierte Addons. Addons werden aus\n"
            "~/.mailclient/addons/ geladen.\n"
            "Jedes Addon-Verzeichnis braucht eine __init__.py\n"
            "mit einer Klasse 'Addon(AddonBase)'."
        ))
        sizer.Add(lbl, 0, wx.ALL, 8)

        self.list_addons = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_addons.SetName("Addon-Liste")
        self.list_addons.InsertColumn(0, "Name",       width=180)
        self.list_addons.InsertColumn(1, "Version",    width=70)
        self.list_addons.InsertColumn(2, "Status",     width=80)
        self.list_addons.InsertColumn(3, "Beschreibung", width=160)
        sizer.Add(self.list_addons, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_enable  = wx.Button(panel, label="Aktivieren")
        self.btn_disable = wx.Button(panel, label="Deaktivieren")
        btn_install      = wx.Button(panel, label="Installieren...")
        btn_close        = wx.Button(panel, wx.ID_CLOSE, "&Schließen")

        for b in (self.btn_enable, self.btn_disable, btn_install):
            btn_sizer.Add(b, 0, wx.RIGHT, 6)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_close)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        btn_install.Bind(wx.EVT_BUTTON, self._on_install)
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        panel.SetSizer(sizer)

    def _load_addons(self):
        self.list_addons.DeleteAllItems()
        loaded = self.controller.addon_mgr.get_loaded_addons()
        available = self.controller.addon_mgr.scan_addon_dir()

        for name in available:
            addon = loaded.get(name)
            version = addon.VERSION if addon else "–"
            status  = "Aktiv" if addon else "Inaktiv"
            desc    = addon.DESCRIPTION if addon else ""
            idx = self.list_addons.InsertItem(self.list_addons.GetItemCount(), name)
            self.list_addons.SetItem(idx, 1, version)
            self.list_addons.SetItem(idx, 2, status)
            self.list_addons.SetItem(idx, 3, desc)

        if not available:
            idx = self.list_addons.InsertItem(0, "(Keine Addons gefunden)")

    def _on_install(self, event):
        with wx.DirDialog(self, "Addon-Verzeichnis auswählen") as d:
            if d.ShowModal() == wx.ID_OK:
                wx.MessageBox(
                    f"Addon-Installation aus:\n{d.GetPath()}\n\n"
                    "Kopieren Sie das Addon-Verzeichnis nach\n"
                    "~/.mailclient/addons/ und starten Sie die Anwendung neu.",
                    "Addon installieren",
                    wx.OK | wx.ICON_INFORMATION,
                    self
                )


# ================================================================== #
#  AboutDialog                                                        #
# ================================================================== #

class AboutDialog(wx.Dialog):
    """Über-Dialog."""

    def __init__(self, parent):
        super().__init__(parent, title="Über MailClient", size=(380, 280),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, label="MailClient")
        title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        sizer.Add(title, 0, wx.ALIGN_CENTER | wx.TOP, 20)

        info = wx.StaticText(panel, label=(
            "Version 1.0.0 (Entwicklungsversion)\n\n"
            "Screenreader-optimierter E-Mail-Client\n"
            "Python 3.12 + wxPython\n\n"
            "Protokolle: IMAP, POP3, SMTP (vorbereitet)\n"
            "Datenbank: SQLite\n"
            "Erweiterbar durch Addons"
        ), style=wx.ALIGN_CENTER)
        sizer.Add(info, 1, wx.ALIGN_CENTER | wx.ALL, 16)

        btn_close = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
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
        title = "Neue E-Mail"
        if reply_to:
            title = "Antworten"
        elif forward:
            title = "Weiterleiten"

        super().__init__(parent, title=title, size=(620, 500),
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

        def add_field(label, ctrl):
            gs.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            gs.Add(ctrl, 1, wx.EXPAND)

        accounts = self.controller.get_accounts()
        from_choices = [f"{a['name']} <{a['email']}>" for a in accounts] or ["(Kein Konto)"]
        self.cho_from   = wx.Choice(panel, choices=from_choices)
        self.cho_from.SetName("Von")
        self.cho_from.SetSelection(0)
        self.txt_to     = wx.TextCtrl(panel)
        self.txt_to.SetName("An")
        self.txt_cc     = wx.TextCtrl(panel)
        self.txt_cc.SetName("CC")
        self.txt_subject = wx.TextCtrl(panel)
        self.txt_subject.SetName("Betreff")

        add_field("Von:",     self.cho_from)
        add_field("An:",      self.txt_to)
        add_field("CC:",      self.txt_cc)
        add_field("Betreff:", self.txt_subject)

        sizer.Add(gs, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.txt_body = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.BORDER_SUNKEN)
        self.txt_body.SetName("Nachrichtentext")
        self.txt_body.SetMinSize((-1, 200))
        sizer.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_send     = wx.Button(panel, label="&Senden")
        btn_send.SetName("E-Mail senden")
        btn_attach   = wx.Button(panel, label="&Anhang hinzufügen")
        btn_attach.SetName("Anhang hinzufügen")
        btn_discard  = wx.Button(panel, wx.ID_CANCEL, "Verwerfen")

        btn_sizer.Add(btn_send,   0, wx.RIGHT, 8)
        btn_sizer.Add(btn_attach, 0, wx.RIGHT, 8)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_discard)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        btn_send.Bind(wx.EVT_BUTTON,   self._on_send)
        btn_attach.Bind(wx.EVT_BUTTON, self._on_attach)
        panel.SetSizer(sizer)

        self.txt_to.SetFocus()

    def _prefill(self, reply_to: dict, reply_all: bool, forward: dict):
        if reply_to:
            self.txt_to.SetValue(reply_to.get("sender", ""))
            subj = reply_to.get("subject", "")
            if not subj.startswith("Re:"):
                subj = "Re: " + subj
            self.txt_subject.SetValue(subj)
            orig = (
                f"\n\n──────────────────────────────\n"
                f"Von: {reply_to.get('sender_name', '')} <{reply_to.get('sender', '')}>\n"
                f"Datum: {reply_to.get('date', '')}\n\n"
                f"{reply_to.get('body_text', '')}"
            )
            self.txt_body.SetValue(orig)
            self.txt_body.SetInsertionPoint(0)

        elif forward:
            subj = forward.get("subject", "")
            if not subj.startswith("Fwd:"):
                subj = "Fwd: " + subj
            self.txt_subject.SetValue(subj)
            orig = (
                f"\n\n──────────────────────────────\n"
                f"Von: {forward.get('sender_name', '')} <{forward.get('sender', '')}>\n"
                f"An: {forward.get('recipients', '')}\n"
                f"Datum: {forward.get('date', '')}\n\n"
                f"{forward.get('body_text', '')}"
            )
            self.txt_body.SetValue(orig)

    def _on_send(self, event):
        to_addr = self.txt_to.GetValue().strip()
        subject = self.txt_subject.GetValue().strip()
        if not to_addr:
            wx.MessageBox("Bitte eine Empfängeradresse angeben.", "Pflichtfeld", wx.OK | wx.ICON_WARNING, self)
            return
        # TODO: SMTP-Versand über controller.send_mail()
        wx.MessageBox(
            "SMTP-Versand noch nicht implementiert.\n\n"
            "Das SMTP-Protokollmodul kann in protocols/smtp_handler.py ergänzt werden.",
            "Nicht implementiert",
            wx.OK | wx.ICON_INFORMATION,
            self
        )

    def _on_attach(self, event):
        with wx.FileDialog(self, "Anhang auswählen",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as d:
            if d.ShowModal() == wx.ID_OK:
                paths = d.GetPaths()
                wx.MessageBox(
                    f"{len(paths)} Datei(en) ausgewählt.\n\n"
                    "Anhang-Unterstützung wird mit dem SMTP-Modul implementiert.",
                    "Anhang",
                    wx.OK | wx.ICON_INFORMATION,
                    self
                )
