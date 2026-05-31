"""
Addon: BackupRestore  v1.0
Backups auflisten, erkennen, wiederherstellen und ins aktuelle Speicherformat konvertieren.

Ablauf beim Einspielen:
  1. Backup-Format automatisch erkennen (sqlite_one / sqlite_per_account / files / mbox)
  2. Aktuelle Daten mit create_backup() sichern (Sicherheitsnetz)
  3. Backup-Dateien ins data_dir kopieren
  4. Falls Backup-Format ≠ aktuellem Format: migrate_storage() aufrufen
  5. Anwendung neu starten

Erkennungslogik:
  - structure.db ohne mailstore_*.db  → sqlite_one
  - structure.db + mailstore_N.db     → sqlite_per_account
  - structure.db + mailstore/         → files
  - structure.db + mbox/              → mbox
"""

import os
import sys
import shutil
import sqlite3
import threading
import subprocess
from datetime import datetime

import wx

from core.addon_manager import AddonBase
from core.i18n import tr


# ------------------------------------------------------------------ #
#  Hilfsfunktionen                                                    #
# ------------------------------------------------------------------ #

def _detect_backup_format(backup_dir: str) -> str | None:
    """
    Erkennt das Speicherformat eines Backup-Ordners.
    Gibt einen STORAGE_*-String zurück oder None wenn nicht erkennbar.
    """
    if not os.path.isdir(backup_dir):
        return None

    has_structure  = os.path.isfile(os.path.join(backup_dir, "structure.db"))
    has_mbox       = os.path.isdir( os.path.join(backup_dir, "mbox"))
    has_mailstore  = os.path.isdir( os.path.join(backup_dir, "mailstore"))
    has_per_acc    = any(
        f.startswith("mailstore_") and f.endswith(".db")
        for f in os.listdir(backup_dir)
        if os.path.isfile(os.path.join(backup_dir, f))
    )

    if not has_structure:
        return None
    if has_mbox:
        return "mbox"
    if has_mailstore:
        return "files"
    if has_per_acc:
        return "sqlite_per_account"
    return "sqlite_one"


def _backup_mail_count(backup_dir: str, fmt: str) -> int:
    """Zählt die Mails in einem Backup (schnell, ohne alles zu laden)."""
    try:
        if fmt == "sqlite_one":
            conn = sqlite3.connect(os.path.join(backup_dir, "structure.db"))
            r    = conn.execute("SELECT COUNT(*) FROM mails").fetchone()
            conn.close()
            return r[0] if r else 0

        elif fmt == "sqlite_per_account":
            total = 0
            for fn in os.listdir(backup_dir):
                if fn.startswith("mailstore_") and fn.endswith(".db"):
                    conn = sqlite3.connect(os.path.join(backup_dir, fn))
                    r    = conn.execute("SELECT COUNT(*) FROM mails").fetchone()
                    conn.close()
                    total += r[0] if r else 0
            return total

        elif fmt == "files":
            total = 0
            store = os.path.join(backup_dir, "mailstore")
            for _, _, files in os.walk(store):
                total += sum(1 for f in files if f.endswith(".json"))
            return total

        elif fmt == "mbox":
            idx_path = os.path.join(backup_dir, "mbox", "index.db")
            if os.path.isfile(idx_path):
                conn = sqlite3.connect(idx_path)
                r    = conn.execute("SELECT COUNT(*) FROM mbox_index").fetchone()
                conn.close()
                return r[0] if r else 0
            # Fallback: .mbox-Dateien zählen (keine exakten Mailzahlen)
            return sum(1 for f in os.listdir(os.path.join(backup_dir, "mbox"))
                       if f.endswith(".mbox"))
    except Exception:
        return -1


def _dir_size_bytes(path: str) -> int:
    """Berechnet die Gesamtgröße eines Verzeichnisses in Bytes."""
    total = 0
    try:
        for root, _, files in os.walk(path):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
    except Exception:
        pass
    return total


def _format_size(n: int) -> str:
    if n < 0:           return "?"
    if n < 1024:        return tr("br_size_b",  n=n)
    if n < 1024**2:     return tr("br_size_kb", n=round(n/1024, 1))
    return              tr("br_size_mb", n=round(n/1024**2, 1))


def _format_datetime(ts_str: str) -> str:
    """
    Wandelt "2026-05-31 19-34-02" oder "2026-05-31 19:34:02"
    in "Sonntag, 31.05.2026 um 19:34 Uhr" um.
    """
    DAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
               "Freitag", "Samstag", "Sonntag"]
    try:
        clean = ts_str.replace("-", " ", 2).replace(" ", "T", 1)
        # "2026 05 31T19-34-02" → normalisieren
        clean = ts_str.strip()
        # Backup-Ordnernamen: "2026-05-31 19-34-02" (Bindestriche statt Doppelpunkte)
        if len(clean) == 19 and clean[10] == " ":
            date_part = clean[:10]           # 2026-05-31
            time_part = clean[11:].replace("-", ":")  # 19:34:02
            dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.fromisoformat(clean)
        weekday = DAYS_DE[dt.weekday()]
        return f"{weekday}, {dt.day:02d}.{dt.month:02d}.{dt.year} um {dt.hour:02d}:{dt.minute:02d} Uhr"
    except Exception:
        return ts_str


def _type_label(fmt: str) -> str:
    return {
        "sqlite_one":         tr("br_type_sqlite_one"),
        "sqlite_per_account": tr("br_type_sqlite_per_account"),
        "files":              tr("br_type_files"),
        "mbox":               tr("br_type_mbox"),
    }.get(fmt, tr("br_type_unknown"))


# ------------------------------------------------------------------ #
#  Addon-Klasse                                                       #
# ------------------------------------------------------------------ #

class Addon(AddonBase):

    NAME    = "BackupRestore"
    VERSION = "1.0.0"

    @property
    def DESCRIPTION(self):
        return tr("br_description")

    def on_load(self):
        pass

    def get_settings_panel(self, parent) -> wx.Panel:
        return BackupRestorePanel(parent, self.controller)

    def get_menu_items(self) -> list:
        return [{"label": tr("br_menu_open"), "handler": self._open_from_menu}]

    def _open_from_menu(self, mail_id=None):
        app   = wx.GetApp()
        frame = app.GetTopWindow() if app else None
        dlg   = BackupRestoreDialog(frame, self.controller)
        dlg.ShowModal()
        dlg.Destroy()


# ------------------------------------------------------------------ #
#  Haupt-Dialog                                                       #
# ------------------------------------------------------------------ #

class BackupRestoreDialog(wx.Dialog):
    """Vollständiger Backup-Wiederherstellungs-Dialog (auch als Standalone-Fenster nutzbar)."""

    def __init__(self, parent, controller):
        super().__init__(parent, title=tr("br_dlg_title"), size=(780, 540),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._ctrl    = controller
        self._backups = []          # [(backup_dir, fmt, date_str, mail_count, size), …]
        self._selected_dir  = None
        self._selected_fmt  = None
        self._build_ui()
        self._scan_backups()
        self.Centre()

    # ---- UI -------------------------------------------------------- #

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Überschrift
        lbl = wx.StaticText(panel, label=tr("br_section_list"))
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 8)

        # Backup-Liste
        self.list_ctrl = wx.ListCtrl(
            panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_ctrl.SetName(tr("br_section_list"))
        self.list_ctrl.InsertColumn(0, tr("br_col_date"),  width=260)
        self.list_ctrl.InsertColumn(1, tr("br_col_type"),  width=170)
        self.list_ctrl.InsertColumn(2, tr("br_col_mails"), width=60)
        self.list_ctrl.InsertColumn(3, tr("br_col_size"),  width=80)
        self.list_ctrl.InsertColumn(4, tr("br_col_path"),  width=180)
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # Fortschrittsanzeige
        self.gauge = wx.Gauge(panel, range=100, size=(-1, 20))
        self.gauge.SetName(tr("br_dlg_title"))
        self.lbl_status = wx.StaticText(panel, label=tr("br_hint_select"))
        sizer.Add(self.lbl_status, 0, wx.LEFT | wx.TOP, 8)
        sizer.Add(self.gauge,      0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)

        # Buttons
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_restore = wx.Button(panel, label=tr("br_btn_restore"))
        btn_browse       = wx.Button(panel, label=tr("br_btn_browse"))
        btn_refresh      = wx.Button(panel, label=tr("br_btn_refresh"))
        btn_close        = wx.Button(panel, wx.ID_CANCEL, label="Schließen")
        self.btn_restore.Enable(False)
        row.Add(self.btn_restore, 0, wx.RIGHT, 6)
        row.Add(btn_browse,       0, wx.RIGHT, 6)
        row.Add(btn_refresh,      0, wx.RIGHT, 6)
        row.AddStretchSpacer()
        row.Add(btn_close, 0)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(sizer)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED,   self._on_list_select)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_list_deselect)
        self.btn_restore.Bind(wx.EVT_BUTTON, self._on_restore)
        btn_browse.Bind(wx.EVT_BUTTON,       self._on_browse)
        btn_refresh.Bind(wx.EVT_BUTTON,      lambda e: self._scan_backups())
        self.Bind(wx.EVT_CLOSE, self._on_close)

    # ---- Backup-Liste scannen -------------------------------------- #

    def _scan_backups(self):
        self.list_ctrl.DeleteAllItems()
        self._backups.clear()
        self._selected_dir = None
        self._selected_fmt = None
        self.btn_restore.Enable(False)

        backups_root = os.path.join(self._ctrl.db.data_dir, "backups")
        if not os.path.isdir(backups_root):
            self.lbl_status.SetLabel(tr("br_no_backups_found"))
            return

        entries = []
        for entry in os.scandir(backups_root):
            if not entry.is_dir(): continue
            fmt = _detect_backup_format(entry.path)
            if not fmt:            continue
            entries.append((entry.path, fmt, entry.name))

        # Neueste zuerst
        entries.sort(key=lambda x: x[2], reverse=True)

        for backup_dir, fmt, date_str in entries:
            mail_count = _backup_mail_count(backup_dir, fmt)
            size       = _dir_size_bytes(backup_dir)
            self._backups.append((backup_dir, fmt, date_str, mail_count, size))

            idx = self.list_ctrl.InsertItem(
                self.list_ctrl.GetItemCount(), _format_datetime(date_str))
            self.list_ctrl.SetItem(idx, 1, _type_label(fmt))
            self.list_ctrl.SetItem(idx, 2, str(mail_count) if mail_count >= 0 else "?")
            self.list_ctrl.SetItem(idx, 3, _format_size(size))
            self.list_ctrl.SetItem(idx, 4, backup_dir)

        if not self._backups:
            self.lbl_status.SetLabel(tr("br_no_backups_found"))
        else:
            self.lbl_status.SetLabel(tr("br_hint_select"))

    # ---- Events ---------------------------------------------------- #

    def _on_list_select(self, event):
        idx = event.GetIndex()
        if 0 <= idx < len(self._backups):
            self._selected_dir, self._selected_fmt = (
                self._backups[idx][0], self._backups[idx][1])
            self.btn_restore.Enable(True)

    def _on_list_deselect(self, event):
        self._selected_dir = None
        self._selected_fmt = None
        self.btn_restore.Enable(False)

    def _on_browse(self, event):
        with wx.DirDialog(self, tr("br_btn_browse"),
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as d:
            if d.ShowModal() != wx.ID_OK:
                return
        chosen = d.GetPath()
        fmt    = _detect_backup_format(chosen)
        if not fmt:
            wx.MessageBox(tr("br_backup_not_valid"), tr("br_dlg_title"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        # Auswahl setzen + in Liste hervorheben (Eintrag hinzufügen wenn nicht vorhanden)
        self._selected_dir = chosen
        self._selected_fmt = fmt
        self.btn_restore.Enable(True)
        date_str   = os.path.basename(chosen)
        mail_count = _backup_mail_count(chosen, fmt)
        size       = _dir_size_bytes(chosen)
        # Prüfen ob bereits in Liste
        for row in range(self.list_ctrl.GetItemCount()):
            if self.list_ctrl.GetItemText(row, 4) == chosen:
                self.list_ctrl.Select(row)
                self.list_ctrl.EnsureVisible(row)
                return
        # Neuer Eintrag (manuell gewählt, außerhalb backups/)
        idx = self.list_ctrl.InsertItem(0, _format_datetime(date_str))
        self.list_ctrl.SetItem(idx, 1, _type_label(fmt))
        self.list_ctrl.SetItem(idx, 2, str(mail_count) if mail_count >= 0 else "?")
        self.list_ctrl.SetItem(idx, 3, _format_size(size))
        self.list_ctrl.SetItem(idx, 4, chosen)
        self.list_ctrl.Select(idx)
        self.list_ctrl.EnsureVisible(idx)
        self.lbl_status.SetLabel(tr("br_hint_select"))

    def _on_restore(self, event):
        if not self._selected_dir or not self._selected_fmt:
            wx.MessageBox(tr("br_no_backup_selected"), tr("br_dlg_title"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return

        date_label = _format_datetime(os.path.basename(self._selected_dir))
        msg = tr("br_confirm_msg",
                 date=date_label,
                 format=_type_label(self._selected_fmt))
        if wx.MessageBox(msg, tr("br_confirm_title"),
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) != wx.YES:
            return

        self.btn_restore.Enable(False)
        self.gauge.SetValue(0)
        self.lbl_status.SetLabel(tr("br_progress_backup_current"))

        def _run():
            try:
                self._do_restore(self._selected_dir, self._selected_fmt)
            except Exception as e:
                wx.CallAfter(self._on_error, str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _on_error(self, error: str):
        self.btn_restore.Enable(True)
        self.gauge.SetValue(0)
        self.lbl_status.SetLabel("")
        wx.MessageBox(tr("br_error_restore", error=error),
                      tr("br_dlg_title"), wx.OK | wx.ICON_ERROR, self)

    def _on_close(self, event):
        event.Skip()

    # ---- Wiederherstellungs-Logik ---------------------------------- #

    def _progress(self, pct: int, msg: str):
        """Thread-sicheres UI-Update."""
        wx.CallAfter(self._update_ui, pct, msg)

    def _update_ui(self, pct: int, msg: str):
        try:
            self.gauge.SetValue(min(pct, 100))
            self.lbl_status.SetLabel(msg)
            self.gauge.SetName(f"{tr('br_dlg_title')}: {pct}%")
        except RuntimeError:
            pass

    def _do_restore(self, backup_dir: str, backup_fmt: str):
        """
        Vollständiger Wiederherstellungs-Ablauf (läuft im Worker-Thread).

        1. Aktuelle Daten sichern
        2. Backup-Dateien ins data_dir kopieren
        3. Falls backup_fmt ≠ aktuellem Format → migrate_storage()
        4. Neustart
        """
        from core.protocol_runner import log
        db       = self._ctrl.db
        data_dir = db.data_dir
        cur_mode = db.get_setting("mail_storage", "sqlite_one")

        # ---- Schritt 1: Aktuelle Daten sichern -------------------- #
        self._progress(5, tr("br_progress_backup_current"))
        log("info", f"BackupRestore: Sichere aktuelle Daten vor Restore…")
        try:
            db.create_backup(
                progress_cb=lambda s, t, m: self._progress(5 + int(s/max(t,1)*15), m)
            )
        except Exception as e:
            log("warning", f"BackupRestore: Vorsicherung fehlgeschlagen: {e}")
            # Kein harter Abbruch – wir warnen nur

        # ---- Schritt 2: Alle DB-Verbindungen schließen ------------ #
        self._progress(22, tr("br_progress_restore"))
        log("info", f"BackupRestore: Schließe DB-Verbindungen…")
        self._close_all_connections(db)

        # ---- Schritt 3: Backup-Dateien kopieren ------------------- #
        self._progress(25, tr("br_progress_restore"))
        log("info", f"BackupRestore: Kopiere Backup {backup_dir!r} → {data_dir!r}")
        self._copy_backup_to_datadir(backup_dir, backup_fmt, data_dir)
        self._progress(60, tr("br_progress_restore"))

        # ---- Schritt 4: Speicherformat-Einstellung setzen --------- #
        db.set_setting("mail_storage", backup_fmt)
        log("info", f"BackupRestore: mail_storage gesetzt auf {backup_fmt!r}")

        # ---- Schritt 5: Falls Konvertierung nötig ----------------- #
        if backup_fmt != cur_mode:
            self._progress(65, tr("br_progress_convert", mode=cur_mode))
            log("info", f"BackupRestore: Konvertiere {backup_fmt!r} → {cur_mode!r}")
            try:
                db.migrate_storage(
                    cur_mode,
                    progress_cb=lambda s, t, m: self._progress(
                        65 + int(s/max(t,1)*30), m)
                )
            except Exception as e:
                log("error", f"BackupRestore: Konvertierung fehlgeschlagen: {e}")
                # Backup-Format beibehalten wenn Konvertierung scheitert
                db.set_setting("mail_storage", backup_fmt)

        # ---- Schritt 6: Neustart ---------------------------------- #
        self._progress(100, tr("br_progress_done"))
        log("info", "BackupRestore: Starte Anwendung neu…")
        wx.CallAfter(self._restart)

    def _close_all_connections(self, db):
        """Schließt alle offenen SQLite-Verbindungen sicher."""
        for attr in ("_structure_conn", "_accounts_conn"):
            conn = getattr(db, attr, None)
            if conn:
                try: conn.close()
                except Exception: pass
                setattr(db, attr, None)
        for conn in getattr(db, "_per_account_conns", {}).values():
            try: conn.close()
            except Exception: pass
        db._per_account_conns = {}
        mbox_conn = getattr(db, "_mbox_idx_conn", None)
        if mbox_conn:
            try: mbox_conn.close()
            except Exception: pass
            db._mbox_idx_conn = None

    def _copy_backup_to_datadir(self, backup_dir: str, fmt: str, data_dir: str):
        """
        Kopiert die relevanten Backup-Dateien ins data_dir.
        Überschreibt bestehende Dateien/Ordner.
        """
        # structure.db immer
        src_struct = os.path.join(backup_dir, "structure.db")
        dst_struct = os.path.join(data_dir,   "structure.db")
        if os.path.isfile(src_struct):
            shutil.copy2(src_struct, dst_struct)

        if fmt == "sqlite_one":
            pass  # mails sind in structure.db

        elif fmt == "sqlite_per_account":
            for fn in os.listdir(backup_dir):
                if fn.startswith("mailstore_") and fn.endswith(".db"):
                    shutil.copy2(
                        os.path.join(backup_dir, fn),
                        os.path.join(data_dir,   fn))

        elif fmt == "files":
            src = os.path.join(backup_dir, "mailstore")
            dst = os.path.join(data_dir,   "mailstore")
            if os.path.isdir(src):
                if os.path.isdir(dst): shutil.rmtree(dst)
                shutil.copytree(src, dst)

        elif fmt == "mbox":
            src = os.path.join(backup_dir, "mbox")
            dst = os.path.join(data_dir,   "mbox")
            if os.path.isdir(src):
                if os.path.isdir(dst): shutil.rmtree(dst)
                shutil.copytree(src, dst)

    def _restart(self):
        """Startet die Anwendung neu und schließt den Dialog."""
        try:
            self.EndModal(wx.ID_OK)
        except RuntimeError:
            pass
        python = sys.executable
        script = os.path.abspath(sys.argv[0])
        subprocess.Popen([python, script])
        app = wx.GetApp()
        if app:
            top = app.GetTopWindow()
            if top: top.Close(force=True)


# ------------------------------------------------------------------ #
#  Einstellungs-Panel (für AddonSettingsDialog)                      #
# ------------------------------------------------------------------ #

class BackupRestorePanel(wx.Panel):
    """
    Einstellungs-Panel: zeigt dieselbe Backup-Liste wie der Haupt-Dialog,
    aber als eingebetteter Panel innerhalb des AddonSettingsDialog.
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self._ctrl    = controller
        self._backups = []
        self._selected_dir = None
        self._selected_fmt = None
        self._build()
        self._scan()

    def _build(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(self, label=tr("br_section_list"))
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 6)

        self.list_ctrl = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_ctrl.SetName(tr("br_section_list"))
        self.list_ctrl.InsertColumn(0, tr("br_col_date"),  width=240)
        self.list_ctrl.InsertColumn(1, tr("br_col_type"),  width=150)
        self.list_ctrl.InsertColumn(2, tr("br_col_mails"), width=55)
        self.list_ctrl.InsertColumn(3, tr("br_col_size"),  width=70)
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_restore = wx.Button(self, label=tr("br_btn_restore"))
        btn_browse       = wx.Button(self, label=tr("br_btn_browse"))
        btn_refresh      = wx.Button(self, label=tr("br_btn_refresh"))
        self.btn_restore.Enable(False)
        row.Add(self.btn_restore, 0, wx.RIGHT, 6)
        row.Add(btn_browse,       0, wx.RIGHT, 6)
        row.Add(btn_refresh,      0)
        sizer.Add(row, 0, wx.LEFT | wx.BOTTOM, 6)

        self.lbl_info = wx.StaticText(self, label=tr("br_hint_select"))
        self.lbl_info.SetForegroundColour(wx.Colour(100, 100, 100))
        sizer.Add(self.lbl_info, 0, wx.LEFT | wx.BOTTOM, 6)

        self.SetSizer(sizer)

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED,   self._on_sel)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_desel)
        self.btn_restore.Bind(wx.EVT_BUTTON, self._on_restore)
        btn_browse.Bind(wx.EVT_BUTTON,       self._on_browse)
        btn_refresh.Bind(wx.EVT_BUTTON,      lambda e: self._scan())

    def save(self):
        pass  # Keine persistenten Einstellungen – Restore passiert sofort

    def _scan(self):
        self.list_ctrl.DeleteAllItems()
        self._backups.clear()
        backups_root = os.path.join(self._ctrl.db.data_dir, "backups")
        if not os.path.isdir(backups_root):
            self.lbl_info.SetLabel(tr("br_no_backups_found"))
            return
        entries = []
        for entry in os.scandir(backups_root):
            if not entry.is_dir(): continue
            fmt = _detect_backup_format(entry.path)
            if fmt: entries.append((entry.path, fmt, entry.name))
        entries.sort(key=lambda x: x[2], reverse=True)
        for backup_dir, fmt, date_str in entries:
            mc   = _backup_mail_count(backup_dir, fmt)
            size = _dir_size_bytes(backup_dir)
            self._backups.append((backup_dir, fmt, date_str, mc, size))
            idx = self.list_ctrl.InsertItem(
                self.list_ctrl.GetItemCount(), _format_datetime(date_str))
            self.list_ctrl.SetItem(idx, 1, _type_label(fmt))
            self.list_ctrl.SetItem(idx, 2, str(mc) if mc >= 0 else "?")
            self.list_ctrl.SetItem(idx, 3, _format_size(size))
        if not self._backups:
            self.lbl_info.SetLabel(tr("br_no_backups_found"))

    def _on_sel(self, event):
        idx = event.GetIndex()
        if 0 <= idx < len(self._backups):
            self._selected_dir = self._backups[idx][0]
            self._selected_fmt = self._backups[idx][1]
            self.btn_restore.Enable(True)

    def _on_desel(self, event):
        self._selected_dir = None
        self.btn_restore.Enable(False)

    def _on_browse(self, event):
        with wx.DirDialog(self, tr("br_btn_browse"),
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as d:
            if d.ShowModal() != wx.ID_OK: return
        chosen = d.GetPath()
        fmt    = _detect_backup_format(chosen)
        if not fmt:
            wx.MessageBox(tr("br_backup_not_valid"), tr("br_dlg_title"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        self._selected_dir = chosen
        self._selected_fmt = fmt
        self.btn_restore.Enable(True)
        date_str = os.path.basename(chosen)
        mc       = _backup_mail_count(chosen, fmt)
        idx      = self.list_ctrl.InsertItem(0, _format_datetime(date_str))
        self.list_ctrl.SetItem(idx, 1, _type_label(fmt))
        self.list_ctrl.SetItem(idx, 2, str(mc) if mc >= 0 else "?")
        self.list_ctrl.SetItem(idx, 3, _format_size(_dir_size_bytes(chosen)))
        self.list_ctrl.Select(idx)
        self.lbl_info.SetLabel(tr("br_hint_select"))

    def _on_restore(self, event):
        if not self._selected_dir or not self._selected_fmt:
            wx.MessageBox(tr("br_no_backup_selected"), tr("br_dlg_title"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        # Hauptdialog öffnen (zeigt Fortschrittsbalken)
        frame = wx.GetApp().GetTopWindow()
        dlg   = BackupRestoreDialog(frame, self._ctrl)
        # Eintrag vorauswählen
        for row in range(dlg.list_ctrl.GetItemCount()):
            if dlg.list_ctrl.GetItemText(row, 4) == self._selected_dir:
                dlg.list_ctrl.Select(row)
                dlg.list_ctrl.EnsureVisible(row)
                break
        dlg.ShowModal()
        dlg.Destroy()
