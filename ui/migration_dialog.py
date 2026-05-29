"""
MigrationDialog – Fortschrittsfenster für Mail-Storage-Migration.

Läuft die Migration in einem Worker-Thread, aktualisiert die
Fortschrittsleiste über wx.CallAfter (thread-safe).
Nach Abschluss startet die Anwendung automatisch neu.
"""

import wx
import threading
import sys
import os
import subprocess
from core.i18n import tr


class MigrationDialog(wx.Dialog):
    """
    Fortschrittsfenster für die Mail-Storage-Migration.

    Verwendung:
        dlg = MigrationDialog(parent, controller, new_mode="sqlite_per_account")
        dlg.ShowModal()   # blockiert bis fertig oder Fehler
    """

    def __init__(self, parent, controller, new_mode: str):
        super().__init__(
            parent,
            title=tr("migration_title"),
            size=(480, 220),
            style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP
        )
        self.controller = controller
        self.new_mode   = new_mode
        self._error     = None
        self._finished  = False

        self._build_ui()
        self.Centre()
        # Migration startet sobald das Fenster sichtbar ist
        wx.CallAfter(self._start_migration)

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.lbl_title = wx.StaticText(panel, label=tr("migration_title"))
        self.lbl_title.SetFont(self.lbl_title.GetFont().Bold())
        sizer.Add(self.lbl_title, 0, wx.ALL, 10)

        self.lbl_status = wx.StaticText(panel, label=tr("migration_preparing"))
        sizer.Add(self.lbl_status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.gauge = wx.Gauge(panel, range=100, size=(-1, 24))
        self.gauge.SetName(tr("migration_title"))
        sizer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.lbl_detail = wx.StaticText(panel, label="")
        self.lbl_detail.SetForegroundColour(wx.Colour(80, 80, 80))
        sizer.Add(self.lbl_detail, 0, wx.LEFT | wx.RIGHT, 10)

        panel.SetSizer(sizer)
        # Schließen per X verhindern während laufender Migration
        self.Bind(wx.EVT_CLOSE, self._on_close_attempt)

    # ------------------------------------------------------------------ #
    #  Migration                                                          #
    # ------------------------------------------------------------------ #

    def _start_migration(self):
        """Startet die Migration in einem Hintergrund-Thread."""
        self._update(0, tr("migration_starting"))
        t = threading.Thread(target=self._run_migration, daemon=True)
        t.start()

    def _run_migration(self):
        """Läuft im Worker-Thread."""
        try:
            self.controller.db.migrate_storage(
                self.new_mode,
                progress_cb=self._progress_cb
            )
        except Exception as e:
            self._error = str(e)
            wx.CallAfter(self._on_error, str(e))
            return
        wx.CallAfter(self._on_done)

    def _progress_cb(self, step: int, total: int, message: str):
        """Wird aus dem Worker-Thread aufgerufen – muss thread-safe sein."""
        pct = int(step / max(total, 1) * 100)
        wx.CallAfter(self._update, pct, message)

    def _update(self, pct: int, message: str):
        """Aktualisiert UI (läuft im Main-Thread via CallAfter)."""
        try:
            self.gauge.SetValue(min(pct, 100))
            self.lbl_detail.SetLabel(message)
            # Screenreader: Statustext aktualisieren
            self.gauge.SetName(f"{tr('migration_title')}: {pct}%")
            self.Layout()
        except RuntimeError:
            pass

    def _on_done(self):
        """Migration erfolgreich – kurze Meldung, dann Neustart."""
        self._finished = True
        self._update(100, tr("migration_done"))
        self.lbl_status.SetLabel(tr("migration_restarting"))
        self.Layout()
        wx.CallLater(1500, self._restart)

    def _on_error(self, error: str):
        self._finished = True
        self._update(0, "")
        self.lbl_status.SetLabel(tr("migration_error"))
        wx.MessageBox(
            f"{tr('settings_migration_error', error=error)}",
            tr("error_title"),
            wx.OK | wx.ICON_ERROR,
            self
        )
        self.EndModal(wx.ID_CANCEL)

    def _on_close_attempt(self, event):
        if not self._finished:
            # Migration läuft noch – nicht schließen
            wx.Bell()
        else:
            event.Skip()

    def _restart(self):
        self.EndModal(wx.ID_OK)
        python = sys.executable
        script = os.path.abspath(sys.argv[0])
        subprocess.Popen([python, script])
        wx.GetApp().GetTopWindow().Close()
