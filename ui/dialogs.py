"""
Dialoge des MailClients – Screenreader-optimiert (Windows UIA/MSAA konform).

WICHTIG für Windows-Screenreader (NVDA, JAWS, Narrator):
  Die Windows Accessibility API liest Labels anhand der HWND-Erstellungsreihenfolge.
  Regel: StaticText-Label MUSS als HWND vor dem zugehörigen TextCtrl erstellt werden.
  Deshalb: ERST wx.StaticText(...) aufrufen, DANN wx.TextCtrl(...).
  SetName() auf dem Control ist der zuverlässigste Fallback für alle Screenreader.
"""

import wx
import wx.adv
import os
import sys
import zipfile
import shutil
import subprocess


# ------------------------------------------------------------------ #
#  Hilfsfunktion – korrekte Erstellungsreihenfolge                   #
# ------------------------------------------------------------------ #

def add_labeled_field(parent, sizer, label_text: str, ctrl_factory,
                      name: str = None, full_row: bool = False):
    """
    Erzeugt ERST das StaticText-Label, DANN das Control (via Factory-Callable).
    Nur so ist die Windows-HWND-Reihenfolge korrekt für Screenreader.

    ctrl_factory: callable(parent) -> wx.Window
    Gibt das erzeugte Control zurück.
    """
    # 1. Label zuerst erzeugen (niedrigerer HWND-Index)
    lbl = wx.StaticText(parent, label=label_text)

    # 2. Control danach erzeugen (höherer HWND-Index → AT verknüpft mit vorherigem Label)
    ctrl = ctrl_factory(parent)

    # SetName = Label-Text → NVDA/JAWS/Narrator liest diesen als Beschriftung
    ctrl.SetName(name or label_text.rstrip(":").strip())

    # In Sizer einfügen
    if full_row:
        sizer.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(ctrl, 1, wx.EXPAND)
    else:
        sizer.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(ctrl, 1, wx.EXPAND)

    return ctrl


# ================================================================== #
#  AccountDialog                                                      #
# ================================================================== #

class AccountDialog(wx.Dialog):

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
        outer = wx.BoxSizer(wx.VERTICAL)
        nb = wx.Notebook(panel)

        # ---- Seite 1: Allgemein ----
        pg1 = wx.Panel(nb)
        gs1 = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs1.AddGrowableCol(1)

        # ERST Label, DANN Control erzeugen
        self.txt_name = add_labeled_field(
            pg1, gs1, "Anzeigename:",
            lambda p: wx.TextCtrl(p), "Anzeigename"
        )
        self.txt_email = add_labeled_field(
            pg1, gs1, "E-Mail-Adresse:",
            lambda p: wx.TextCtrl(p), "E-Mail-Adresse"
        )
        self.cho_proto = add_labeled_field(
            pg1, gs1, "Protokoll:",
            lambda p: wx.Choice(p, choices=self.PROTOCOLS), "Protokoll"
        )
        self.cho_proto.SetSelection(0)

        pg1.SetSizer(self._wrap(gs1))
        nb.AddPage(pg1, "Allgemein")

        # ---- Seite 2: Posteingang ----
        pg2 = wx.Panel(nb)
        gs2 = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs2.AddGrowableCol(1)

        self.txt_in_host = add_labeled_field(
            pg2, gs2, "Eingangsserver:",
            lambda p: wx.TextCtrl(p), "Eingangsserver"
        )
        self.txt_in_port = add_labeled_field(
            pg2, gs2, "Port:",
            lambda p: wx.SpinCtrl(p, min=1, max=65535, initial=993), "Eingangsport"
        )
        # Checkbox bekommt kein separates Label (label ist im CheckBox selbst)
        gs2.Add(wx.StaticText(pg2, label=""), 0)
        self.chk_in_ssl = wx.CheckBox(pg2, label="SSL/TLS verwenden")
        self.chk_in_ssl.SetName("SSL für Posteingang")
        self.chk_in_ssl.SetValue(True)
        gs2.Add(self.chk_in_ssl, 0)

        self.txt_user = add_labeled_field(
            pg2, gs2, "Benutzername:",
            lambda p: wx.TextCtrl(p), "Benutzername"
        )
        self.txt_pass = add_labeled_field(
            pg2, gs2, "Passwort:",
            lambda p: wx.TextCtrl(p, style=wx.TE_PASSWORD), "Passwort"
        )

        pg2.SetSizer(self._wrap(gs2))
        nb.AddPage(pg2, "Posteingang")

        # ---- Seite 3: SMTP ----
        pg3 = wx.Panel(nb)
        gs3 = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        gs3.AddGrowableCol(1)

        self.txt_out_host = add_labeled_field(
            pg3, gs3, "SMTP-Server:",
            lambda p: wx.TextCtrl(p), "SMTP-Server"
        )
        self.txt_out_port = add_labeled_field(
            pg3, gs3, "Port:",
            lambda p: wx.SpinCtrl(p, min=1, max=65535, initial=587), "SMTP-Port"
        )
        gs3.Add(wx.StaticText(pg3, label=""), 0)
        self.chk_out_ssl = wx.CheckBox(pg3, label="SSL/TLS verwenden")
        self.chk_out_ssl.SetName("SSL für Postausgang")
        self.chk_out_ssl.SetValue(True)
        gs3.Add(self.chk_out_ssl, 0)

        pg3.SetSizer(self._wrap(gs3))
        nb.AddPage(pg3, "Postausgang (SMTP)")

        outer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)

        btn_sizer = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Speichern")
        btn_cancel  = wx.Button(panel, wx.ID_CANCEL, "Abbrechen")
        self.btn_ok.SetDefault()
        self.btn_ok.SetName("Speichern")
        btn_cancel.SetName("Abbrechen")
        btn_sizer.AddButton(self.btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        outer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 6)

        panel.SetSizer(outer)
        self.btn_ok.Bind(wx.EVT_BUTTON, self._on_save)
        self.txt_name.SetFocus()

    @staticmethod
    def _wrap(grid):
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(grid, 1, wx.EXPAND | wx.ALL, 12)
        return s

    def _load_account(self, account_id):
        acc = self.controller.get_account(account_id)
        if not acc:
            return
        self.txt_name.SetValue(str(acc["name"] or ""))
        self.txt_email.SetValue(str(acc["email"] or ""))
        idx = self.PROTOCOLS.index(acc["protocol"]) if acc["protocol"] in self.PROTOCOLS else 0
        self.cho_proto.SetSelection(idx)
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

    def __init__(self, parent, controller):
        super().__init__(parent, title="Einstellungen", size=(460, 380),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._load()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)
        nb    = wx.Notebook(panel)

        # ---- Allgemein ----
        pg1 = wx.Panel(nb)
        gs1 = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs1.AddGrowableCol(1)

        # Checkboxen: volle Zeile
        gs1.Add(wx.StaticText(pg1, label=""), 0)
        self.chk_auto = wx.CheckBox(pg1, label="E-Mails automatisch abrufen")
        self.chk_auto.SetName("Automatischer Abruf")
        gs1.Add(self.chk_auto, 0)

        self.spn_interval = add_labeled_field(
            pg1, gs1, "Abrufintervall (Minuten):",
            lambda p: wx.SpinCtrl(p, min=1, max=60, initial=10), "Abrufintervall"
        )

        gs1.Add(wx.StaticText(pg1, label=""), 0)
        self.chk_html = wx.CheckBox(pg1, label="HTML-Mails rendern")
        self.chk_html.SetName("HTML-Darstellung")
        gs1.Add(self.chk_html, 0)

        gs1.Add(wx.StaticText(pg1, label=""), 0)
        self.chk_del = wx.CheckBox(pg1, label="Löschen bestätigen")
        self.chk_del.SetName("Löschbestätigung")
        gs1.Add(self.chk_del, 0)

        pg1.SetSizer(self._wrap(gs1))
        nb.AddPage(pg1, "Allgemein")

        # ---- Darstellung ----
        pg2 = wx.Panel(nb)
        gs2 = wx.FlexGridSizer(cols=2, vgap=10, hgap=8)
        gs2.AddGrowableCol(1)
        self.spn_font = add_labeled_field(
            pg2, gs2, "Schriftgröße Vorschau:",
            lambda p: wx.SpinCtrl(p, min=8, max=24, initial=10), "Schriftgröße"
        )
        pg2.SetSizer(self._wrap(gs2))
        nb.AddPage(pg2, "Darstellung")

        outer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok     = wx.Button(panel, wx.ID_OK,     "Speichern")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Abbrechen")
        btn_ok.SetDefault()
        btn_ok.SetName("Speichern")
        btn_cancel.SetName("Abbrechen")
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        outer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 6)

        panel.SetSizer(outer)
        btn_ok.Bind(wx.EVT_BUTTON, self._on_save)

    @staticmethod
    def _wrap(grid):
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(grid, 1, wx.EXPAND | wx.ALL, 12)
        return s

    def _load(self):
        g = self.controller.get_setting
        self.chk_auto.SetValue(g("auto_fetch",     "0") == "1")
        self.spn_interval.SetValue(int(g("fetch_interval", "10")))
        self.chk_html.SetValue(g("render_html",    "0") == "1")
        self.chk_del.SetValue(g("confirm_delete",  "1") == "1")
        self.spn_font.SetValue(int(g("font_size",  "10")))

    def _on_save(self, event):
        s = self.controller.set_setting
        s("auto_fetch",     "1" if self.chk_auto.GetValue() else "0")
        s("fetch_interval", str(self.spn_interval.GetValue()))
        s("render_html",    "1" if self.chk_html.GetValue() else "0")
        s("confirm_delete", "1" if self.chk_del.GetValue() else "0")
        s("font_size",      str(self.spn_font.GetValue()))
        self.EndModal(wx.ID_OK)


# ================================================================== #
#  PrintPreviewDialog                                                 #
# ================================================================== #

class PrintPreviewDialog(wx.Dialog):

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
        btn_sizer.Add(btn_close)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        btn_print.Bind(wx.EVT_BUTTON, lambda e: wx.MessageBox(
            "Druckfunktion noch nicht vollständig implementiert.\n"
            "Bitte Strg+A → Strg+C und aus einem Texteditor drucken.",
            "Drucken", wx.OK | wx.ICON_INFORMATION, self))
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        panel.SetSizer(sizer)
        txt.SetFocus()


# ================================================================== #
#  PGPDialog                                                          #
# ================================================================== #

class PGPDialog(wx.Dialog):

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
            "  • Verschlüsselte Mails entschlüsseln"
        ))
        sizer.Add(info, 0, wx.ALL, 14)

        self.list_keys = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list_keys.SetName("PGP-Schlüsselliste")
        self.list_keys.InsertColumn(0, "Name / E-Mail", width=250)
        self.list_keys.InsertColumn(1, "Schlüssel-ID",  width=130)
        self.list_keys.InsertColumn(2, "Gültig bis",    width=80)
        sizer.Add(self.list_keys, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        for label in ("&Importieren", "&Exportieren"):
            b = wx.Button(panel, label=label)
            b.SetName(label.replace("&", ""))
            b.Bind(wx.EVT_BUTTON, lambda e: wx.MessageBox(
                "Noch nicht implementiert.", "Hinweis", wx.OK, self))
            btn_sizer.Add(b, 0, wx.RIGHT, 6)
        btn_sizer.AddStretchSpacer()
        btn_close = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
        btn_close.SetName("Schließen")
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        btn_sizer.Add(btn_close)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)


# ================================================================== #
#  AddonManagerDialog                                                 #
# ================================================================== #

class AddonManagerDialog(wx.Dialog):
    """
    Addon-Verwaltung mit:
    - Aktivieren / Deaktivieren einzelner Addons
    - Install via ZIP-Datei (entpacken + Neustart)
    """

    def __init__(self, parent, controller):
        super().__init__(parent, title="Addon-Verwaltung", size=(580, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
        self._build_ui()
        self._load_addons()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label=(
            "Addons werden aus dem Addon-Verzeichnis geladen.\n"
            "Doppelklick oder Aktivieren/Deaktivieren schaltet ein Addon um."
        ))
        sizer.Add(lbl, 0, wx.ALL, 8)

        self.list_addons = wx.ListCtrl(
            panel,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL
        )
        self.list_addons.SetName("Addon-Liste")
        self.list_addons.InsertColumn(0, "Name",         width=160)
        self.list_addons.InsertColumn(1, "Version",      width=65)
        self.list_addons.InsertColumn(2, "Status",       width=85)
        self.list_addons.InsertColumn(3, "Beschreibung", width=230)
        sizer.Add(self.list_addons, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # Buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_toggle = wx.Button(panel, label="&Aktivieren / Deaktivieren")
        self.btn_toggle.SetName("Addon aktivieren oder deaktivieren")
        self.btn_toggle.Bind(wx.EVT_BUTTON, self._on_toggle)

        btn_install = wx.Button(panel, label="&Installieren (ZIP)...")
        btn_install.SetName("Addon aus ZIP-Datei installieren")
        btn_install.Bind(wx.EVT_BUTTON, self._on_install)

        btn_open_dir = wx.Button(panel, label="&Verzeichnis öffnen")
        btn_open_dir.SetName("Addon-Verzeichnis im Explorer öffnen")
        btn_open_dir.Bind(wx.EVT_BUTTON, self._on_open_dir)

        btn_close = wx.Button(panel, wx.ID_CLOSE, "&Schließen")
        btn_close.SetName("Schließen")
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))

        btn_row.Add(self.btn_toggle, 0, wx.RIGHT, 6)
        btn_row.Add(btn_install,    0, wx.RIGHT, 6)
        btn_row.Add(btn_open_dir,   0, wx.RIGHT, 6)
        btn_row.AddStretchSpacer()
        btn_row.Add(btn_close)
        sizer.Add(btn_row, 0, wx.EXPAND | wx.ALL, 8)

        # Addon-Verzeichnis-Info
        addon_dir = self.controller.addon_mgr.addon_dir
        lbl_dir = wx.StaticText(panel, label=f"Verzeichnis: {addon_dir}")
        lbl_dir.SetForegroundColour(wx.Colour(80, 80, 80))
        sizer.Add(lbl_dir, 0, wx.LEFT | wx.BOTTOM, 8)

        panel.SetSizer(sizer)
        self.list_addons.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_toggle)

    def _load_addons(self):
        self.list_addons.DeleteAllItems()
        mgr       = self.controller.addon_mgr
        loaded    = mgr.get_loaded_addons()   # {name: AddonBase}
        available = mgr.scan_addon_dir()       # [name, ...]

        if not available:
            idx = self.list_addons.InsertItem(0, "(Keine Addons gefunden)")
            self.list_addons.SetItem(idx, 2, "–")
            return

        for name in sorted(available):
            addon   = loaded.get(name)
            version = addon.VERSION     if addon else "–"
            status  = "Aktiv"           if addon else "Inaktiv"
            desc    = addon.DESCRIPTION if addon else ""

            idx = self.list_addons.InsertItem(self.list_addons.GetItemCount(), name)
            self.list_addons.SetItem(idx, 1, version)
            self.list_addons.SetItem(idx, 2, status)
            self.list_addons.SetItem(idx, 3, desc)

            # Aktive Addons farblich hervorheben
            if addon:
                self.list_addons.SetItemTextColour(idx, wx.Colour(0, 100, 0))

    def _on_toggle(self, event):
        """Aktiviert oder deaktiviert das ausgewählte Addon."""
        idx = self.list_addons.GetFirstSelected()
        if idx < 0:
            wx.MessageBox("Bitte zuerst ein Addon in der Liste auswählen.",
                          "Kein Addon ausgewählt", wx.OK | wx.ICON_INFORMATION, self)
            return

        name   = self.list_addons.GetItemText(idx, 0)
        status = self.list_addons.GetItemText(idx, 2)
        mgr    = self.controller.addon_mgr

        if status == "Aktiv":
            # Deaktivieren
            mgr.unload_addon(name)
            wx.MessageBox(f"Addon '{name}' wurde deaktiviert.\n"
                          "Die Änderung gilt bis zum nächsten Neustart.",
                          "Addon deaktiviert", wx.OK | wx.ICON_INFORMATION, self)
        else:
            # Aktivieren
            ok = mgr.load_addon(name, self.controller)
            if ok:
                wx.MessageBox(f"Addon '{name}' wurde aktiviert.",
                              "Addon aktiviert", wx.OK | wx.ICON_INFORMATION, self)
            else:
                wx.MessageBox(
                    f"Addon '{name}' konnte nicht geladen werden.\n"
                    "Prüfen Sie die Konsole auf Fehlermeldungen.",
                    "Fehler", wx.OK | wx.ICON_ERROR, self)

        self._load_addons()  # Liste aktualisieren

    def _on_install(self, event):
        """
        Installiert ein Addon aus einer ZIP-Datei.
        ZIP muss einen Ordner mit __init__.py enthalten.
        Danach: Neustart der Anwendung.
        """
        with wx.FileDialog(
            self, "Addon-ZIP auswählen",
            wildcard="ZIP-Datei (*.zip)|*.zip",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            zip_path = dlg.GetPath()

        # ZIP prüfen
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
        except zipfile.BadZipFile:
            wx.MessageBox("Die Datei ist keine gültige ZIP-Datei.",
                          "Fehler", wx.OK | wx.ICON_ERROR, self)
            return

        # Addon-Verzeichnis ermitteln (erstes Verzeichnis in der ZIP mit __init__.py)
        addon_name = None
        for n in names:
            parts = n.replace("\\", "/").split("/")
            if len(parts) == 2 and parts[1] == "__init__.py" and parts[0]:
                addon_name = parts[0]
                break

        if not addon_name:
            wx.MessageBox(
                "Kein gültiges Addon in der ZIP gefunden.\n\n"
                "Die ZIP muss einen Ordner mit __init__.py enthalten:\n"
                "  mein_addon/__init__.py",
                "Ungültiges Addon", wx.OK | wx.ICON_WARNING, self
            )
            return

        addon_dir  = self.controller.addon_mgr.addon_dir
        target_dir = os.path.join(addon_dir, addon_name)

        # Bestehende Version fragen
        if os.path.exists(target_dir):
            if wx.MessageBox(
                f"Addon '{addon_name}' ist bereits installiert.\nÜberschreiben?",
                "Addon überschreiben",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
            ) != wx.YES:
                return
            shutil.rmtree(target_dir, ignore_errors=True)

        # Entpacken
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(addon_dir)
        except Exception as e:
            wx.MessageBox(f"Fehler beim Entpacken:\n{e}",
                          "Fehler", wx.OK | wx.ICON_ERROR, self)
            return

        wx.MessageBox(
            f"Addon '{addon_name}' wurde erfolgreich installiert.\n\n"
            "Die Anwendung wird jetzt neu gestartet.",
            "Addon installiert", wx.OK | wx.ICON_INFORMATION, self
        )
        self._restart_app()

    def _on_open_dir(self, event):
        """Öffnet das Addon-Verzeichnis im Windows-Explorer."""
        addon_dir = self.controller.addon_mgr.addon_dir
        os.makedirs(addon_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(addon_dir)
        else:
            subprocess.Popen(["xdg-open", addon_dir])

    @staticmethod
    def _restart_app():
        """Startet die Anwendung neu."""
        python = sys.executable
        script = os.path.abspath(sys.argv[0])
        subprocess.Popen([python, script])
        wx.GetApp().GetTopWindow().Close()


# ================================================================== #
#  AboutDialog                                                        #
# ================================================================== #

class AboutDialog(wx.Dialog):

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

    def __init__(self, parent, controller, reply_to: dict = None,
                 reply_all: bool = False, forward: dict = None):
        title = "Antworten" if reply_to else ("Weiterleiten" if forward else "Neue E-Mail")
        super().__init__(parent, title=title, size=(640, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller = controller
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

        self.cho_from = add_labeled_field(
            panel, gs, "Von:",
            lambda p: wx.Choice(p, choices=from_choices), "Von"
        )
        self.cho_from.SetSelection(0)

        self.txt_to = add_labeled_field(
            panel, gs, "An:",
            lambda p: wx.TextCtrl(p), "An"
        )
        self.txt_cc = add_labeled_field(
            panel, gs, "CC:",
            lambda p: wx.TextCtrl(p), "CC"
        )
        self.txt_subject = add_labeled_field(
            panel, gs, "Betreff:",
            lambda p: wx.TextCtrl(p), "Betreff"
        )

        sizer.Add(gs, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        lbl_body = wx.StaticText(panel, label="Nachrichtentext:")
        sizer.Add(lbl_body, 0, wx.LEFT | wx.TOP, 8)

        self.txt_body = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.BORDER_SUNKEN)
        self.txt_body.SetName("Nachrichtentext")
        self.txt_body.SetMinSize((-1, 200))
        sizer.Add(self.txt_body, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_send   = wx.Button(panel, label="&Senden")
        btn_send.SetName("E-Mail senden")
        btn_attach = wx.Button(panel, label="&Anhang hinzufügen")
        btn_attach.SetName("Anhang hinzufügen")
        btn_disc   = wx.Button(panel, wx.ID_CANCEL, "Verwerfen")
        btn_disc.SetName("Verwerfen und schließen")

        btn_sizer.Add(btn_send,   0, wx.RIGHT, 8)
        btn_sizer.Add(btn_attach, 0, wx.RIGHT, 8)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_disc)
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
            self.txt_subject.SetValue(subj if subj.startswith("Re:") else "Re: " + subj)
            orig = (
                f"\n\n──────────────────────────────\n"
                f"Von: {reply_to.get('sender_name','') or ''}"
                f" <{reply_to.get('sender','') or ''}>\n"
                f"Datum: {reply_to.get('date','') or ''}\n\n"
                f"{reply_to.get('body_text','') or ''}"
            )
            self.txt_body.SetValue(orig)
            self.txt_body.SetInsertionPoint(0)
        elif forward:
            subj = str(forward.get("subject") or "")
            self.txt_subject.SetValue(subj if subj.startswith("Fwd:") else "Fwd: " + subj)
            orig = (
                f"\n\n──────────────────────────────\n"
                f"Von: {forward.get('sender_name','') or ''}"
                f" <{forward.get('sender','') or ''}>\n"
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
