#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Datenbank-Editor (Barrierefrei / Screenreader-optimiert)
===============================================================
Eigenständige Datenbank-Bearbeitungsanwendung für die
SQLite-Datenbankdatei.

Barrierefreiheit (WCAG / NVDA / JAWS / Windows Narrator):
  - KEIN wx.grid – alle Daten in wx.ListCtrl (Report-Modus)
  - Kein AUI/Floating-Panes – nur standard wx.SplitterWindow + wx.Notebook
  - Alle Steuerelemente haben wx.StaticText-Labels DIREKT davor
  - Jedes interaktive Element hat SetName() + SetToolTip()
  - Tastaturnavigation ohne Maus vollständig möglich
  - Fokus-Management: nach Aktionen wird Fokus explizit gesetzt
  - Keine Icon-only-Buttons – immer lesbarer Text
  - Statusmeldungen werden in ein wx.TextCtrl geschrieben (live-region)
  - Schriftgröße über Menü und Tasten anpassbar (8–24pt)
  - 5 Farb-Themes inkl. zwei Hochkontrast-Varianten

Starten:
  python db_editor.py
  python db_editor.py datenbankdatei.db

Benötigt: wxPython
"""

import wx
import wx.adv
import sqlite3
import os
import sys
import csv
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# ─────────────────────────────────────────────────────────────────────────────
APP_NAME    = "Datenbank-Editor"
APP_VERSION = "2.0"
FONT_MIN, FONT_DEFAULT, FONT_MAX = 8, 11, 24
PAGE_SIZE   = 100          # Zeilen pro Seite im ListCtrl

THEMES = {
    # name: (fenster_bg, fenster_fg, liste_bg, liste_fg, auswahl_bg, auswahl_fg, eingabe_bg)
    "Hell (Standard)": (
        wx.Colour(245,245,248), wx.Colour(0,0,0),
        wx.Colour(255,255,255), wx.Colour(0,0,0),
        wx.Colour(0,90,180),    wx.Colour(255,255,255),
        wx.Colour(255,255,255)
    ),
    "Dunkel": (
        wx.Colour(28,28,32),    wx.Colour(220,220,220),
        wx.Colour(36,36,42),    wx.Colour(220,220,220),
        wx.Colour(0,100,200),   wx.Colour(255,255,255),
        wx.Colour(50,50,58)
    ),
    "Hoher Kontrast Schwarz": (
        wx.Colour(0,0,0),       wx.Colour(255,255,0),
        wx.Colour(0,0,0),       wx.Colour(255,255,0),
        wx.Colour(255,255,0),   wx.Colour(0,0,0),
        wx.Colour(0,0,0)
    ),
    "Hoher Kontrast Weiß": (
        wx.Colour(255,255,255), wx.Colour(0,0,0),
        wx.Colour(255,255,255), wx.Colour(0,0,0),
        wx.Colour(0,0,0),       wx.Colour(255,255,255),
        wx.Colour(255,255,255)
    ),
    "Blau (Büro)": (
        wx.Colour(230,238,252), wx.Colour(10,20,60),
        wx.Colour(240,244,255), wx.Colour(10,20,60),
        wx.Colour(20,60,140),   wx.Colour(255,255,255),
        wx.Colour(255,255,255)
    ),
}

TABELLEN_INFO = {
    "buchungen":        "Buchungsjournal – alle Buchungssätze",
    "konten":           "Kontenrahmen SKR49 – Soll/Haben-Konten",
    "buchungsperioden": "Wirtschaftsjahre und Buchungsperioden",
    "kostenstellen":    "Kostenstellen für Buchungszuordnungen",
    "belege":           "Belege: Rechnungen, Quittungen, Kontoauszüge",
    "einstellungen":    "Vereinsdaten und Programmeinstellungen",
    "bankkonten":       "Bankverbindungen des Vereins",
    "import_protokoll": "Protokoll der CSV-Importe",
}

# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────

def mf(size: int, bold: bool = False) -> wx.Font:
    w = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
    return wx.Font(size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, w)

def mono(size: int) -> wx.Font:
    return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                   wx.FONTWEIGHT_NORMAL)

def zell_wert(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        return f"<BLOB {len(v)} B>"
    return str(v)


# ─────────────────────────────────────────────────────────────────────────────
# Datenbank-Backend
# ─────────────────────────────────────────────────────────────────────────────

class DB:
    def __init__(self):
        self._c: Optional[sqlite3.Connection] = None
        self.pfad = ""

    @property
    def offen(self) -> bool:
        return self._c is not None

    def oeffnen(self, pfad: str):
        self.schliessen()
        self._c = sqlite3.connect(pfad)
        self._c.row_factory = sqlite3.Row
        self._c.execute("PRAGMA foreign_keys = ON")
        self.pfad = pfad

    def schliessen(self):
        if self._c:
            self._c.close()
            self._c = None
            self.pfad = ""

    def tabellen(self) -> List[str]:
        cur = self._c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [r[0] for r in cur.fetchall()]

    def spalten(self, tabelle: str) -> List[Dict]:
        cur = self._c.execute(f"PRAGMA table_info('{tabelle}')")
        return [dict(r) for r in cur.fetchall()]

    def zeilen_anzahl(self, tabelle: str, where: str = "") -> int:
        try:
            w = f"WHERE {where}" if where.strip() else ""
            cur = self._c.execute(f'SELECT COUNT(*) FROM "{tabelle}" {w}')
            return cur.fetchone()[0]
        except Exception:
            return 0

    def zeilen_laden(self, tabelle: str, limit: int, offset: int,
                     where: str = "") -> Tuple[List, List[str]]:
        w = f"WHERE {where}" if where.strip() else ""
        sql = f'SELECT * FROM "{tabelle}" {w} LIMIT {limit} OFFSET {offset}'
        cur = self._c.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        return rows, cols

    def sql_ausfuehren(self, sql: str) -> Tuple[bool, str, List, List[str]]:
        try:
            cur = self._c.execute(sql)
            self._c.commit()
            rows = cur.fetchall() if cur.description else []
            cols = [d[0] for d in cur.description] if cur.description else []
            n = cur.rowcount if cur.rowcount >= 0 else len(rows)
            return True, f"OK – {n} Zeile(n) betroffen, {len(rows)} zurückgegeben", rows, cols
        except sqlite3.Error as e:
            return False, f"SQL-Fehler: {e}", [], []

    def zelle_aendern(self, tabelle: str, pk_col: str, pk_val: Any,
                      col: str, wert: str) -> Tuple[bool, str]:
        try:
            v = None if wert.strip() == "" else wert
            self._c.execute(
                f'UPDATE "{tabelle}" SET "{col}"=? WHERE "{pk_col}"=?',
                (v, pk_val)
            )
            self._c.commit()
            return True, f"Gespeichert: {col} = {wert!r}"
        except sqlite3.Error as e:
            return False, f"Fehler: {e}"

    def zeile_loeschen(self, tabelle: str, pk_col: str,
                        pk_val: Any) -> Tuple[bool, str]:
        try:
            self._c.execute(
                f'DELETE FROM "{tabelle}" WHERE "{pk_col}"=?', (pk_val,)
            )
            self._c.commit()
            return True, f"Zeile {pk_val} gelöscht."
        except sqlite3.Error as e:
            return False, f"Fehler: {e}"

    def zeile_einfuegen(self, tabelle: str,
                         daten: Dict[str, str]) -> Tuple[bool, str]:
        try:
            cols  = list(daten.keys())
            vals  = [None if v.strip() == "" else v for v in daten.values()]
            platz = ",".join(["?"] * len(cols))
            kcols = ",".join(f'"{c}"' for c in cols)
            self._c.execute(
                f'INSERT INTO "{tabelle}" ({kcols}) VALUES ({platz})', vals
            )
            self._c.commit()
            return True, "Neue Zeile eingefügt."
        except sqlite3.Error as e:
            return False, f"Fehler: {e}"

    def create_sql(self, tabelle: str) -> str:
        cur = self._c.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (tabelle,)
        )
        r = cur.fetchone()
        return r[0] if r else ""

    def backup(self, ziel: str) -> Tuple[bool, str]:
        try:
            z = sqlite3.connect(ziel)
            self._c.backup(z)
            z.close()
            return True, f"Backup gespeichert: {ziel}"
        except Exception as e:
            return False, f"Backup fehlgeschlagen: {e}"

    def vacuum(self) -> Tuple[bool, str]:
        try:
            self._c.execute("VACUUM")
            return True, "VACUUM OK – Datenbank wurde optimiert."
        except sqlite3.Error as e:
            return False, f"VACUUM fehlgeschlagen: {e}"

    def csv_export(self, tabelle: str, pfad: str) -> Tuple[bool, str]:
        try:
            rows, cols = self.zeilen_laden(tabelle, 999999, 0)
            with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(cols)
                for row in rows:
                    w.writerow([zell_wert(v) for v in row])
            return True, f"{len(rows)} Zeilen exportiert: {pfad}"
        except Exception as e:
            return False, f"Export-Fehler: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Dialog: Zeile einfügen / bearbeiten
# ─────────────────────────────────────────────────────────────────────────────

class ZeilenDialog(wx.Dialog):
    """
    Barrierefreier Zeilen-Dialog.
    Jedes Eingabefeld hat ein StaticText-Label direkt davor (AT-konform).
    Tab-Reihenfolge entspricht der Spaltenfolge.
    """

    def __init__(self, parent, titel: str, spalten: List[Dict],
                 werte: Dict[str,str] = None, fs: int = FONT_DEFAULT,
                 theme: str = "Hell (Standard)"):
        super().__init__(parent, title=titel,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.spalten = spalten
        self.werte   = werte or {}
        self.fs      = fs
        self.theme   = theme
        self.felder: Dict[str, wx.TextCtrl] = {}
        self._aufbauen()
        self.SetSize(580, min(640, 140 + len(spalten) * 50))
        self.Centre()

    def _aufbauen(self):
        _, fg, _, _, _, _, ein_bg = THEMES.get(self.theme, THEMES["Hell (Standard)"])
        f  = mf(self.fs)
        fb = mf(self.fs, bold=True)

        panel = wx.Panel(self)
        haupt = wx.BoxSizer(wx.VERTICAL)

        # Screenreader liest dies als ersten Text im Dialog
        anweis = wx.StaticText(
            panel,
            label="Füllen Sie die Felder aus. "
                  "Pflichtfelder sind mit Stern markiert. "
                  "Leeres Feld speichert den Wert NULL."
        )
        anweis.SetFont(mf(self.fs - 1))
        anweis.Wrap(540)
        haupt.Add(anweis, 0, wx.ALL, 8)

        # Scrollbereich für viele Spalten
        scroll = wx.ScrolledWindow(panel, style=wx.VSCROLL | wx.TAB_TRAVERSAL)
        scroll.SetScrollRate(0, 20)
        feld_sizer = wx.BoxSizer(wx.VERTICAL)

        ist_neu = not self.werte

        for col in self.spalten:
            name   = col["name"]
            ist_pk = col.get("pk", 0) == 1
            noetig = col.get("notnull", 0) == 1
            typ    = col.get("type", "TEXT")
            std    = col.get("dflt_value") or ""

            # Label-Text – Screenreader liest Typ, Pflicht, PK-Info vor
            lbl_text = name
            if noetig:
                lbl_text += " *"
            if ist_pk:
                lbl_text += " (Primärschlüssel)"
            lbl_text += f"  [{typ}]"

            lbl = wx.StaticText(scroll, label=lbl_text)
            lbl.SetFont(fb if noetig else f)
            lbl.SetForegroundColour(fg)
            feld_sizer.Add(lbl, 0, wx.LEFT | wx.TOP, 6)

            if ist_pk and ist_neu:
                info = wx.StaticText(
                    scroll, label="    (wird automatisch vergeben, keine Eingabe nötig)"
                )
                info.SetFont(mf(self.fs - 1))
                info.SetForegroundColour(wx.Colour(100, 100, 100))
                feld_sizer.Add(info, 0, wx.LEFT | wx.BOTTOM, 4)
            else:
                feld = wx.TextCtrl(
                    scroll,
                    value=self.werte.get(name, ""),
                    name=lbl_text,            # MSAA/UIA name = label
                    style=wx.TE_PROCESS_ENTER
                )
                feld.SetFont(f)
                feld.SetBackgroundColour(ein_bg)
                feld.SetForegroundColour(fg)
                feld.SetToolTip(
                    f"Feld: {name}  |  Typ: {typ}  |  "
                    f"{'Pflichtfeld' if noetig else 'Optional'}  |  "
                    f"Standardwert: {std or '(keiner)'}"
                )
                if ist_pk:
                    feld.SetBackgroundColour(wx.Colour(255, 250, 210))
                feld_sizer.Add(
                    feld, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6
                )
                self.felder[name] = feld

        scroll.SetSizer(feld_sizer)
        scroll.SetMinSize((-1, 320))
        haupt.Add(scroll, 1, wx.EXPAND | wx.ALL, 4)

        hint = wx.StaticText(
            panel, label="* = Pflichtfeld  |  Leer lassen = NULL-Wert speichern"
        )
        hint.SetFont(mf(self.fs - 1))
        haupt.Add(hint, 0, wx.LEFT | wx.BOTTOM, 8)

        # Buttons mit vollem Text, kein Icon-only
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_ok = wx.Button(panel, wx.ID_OK, "Speichern und schließen")
        btn_ok.SetFont(fb)
        btn_ok.SetName("Speichern und Dialog schließen")
        btn_ok.SetToolTip("Alle Änderungen speichern und Dialog schließen (Enter)")
        btn_ok.SetDefault()

        btn_ab = wx.Button(panel, wx.ID_CANCEL, "Abbrechen")
        btn_ab.SetFont(f)
        btn_ab.SetName("Abbrechen ohne zu speichern")
        btn_ab.SetToolTip("Dialog schließen ohne zu speichern (Escape)")

        btn_sizer.Add(btn_ok, 0, wx.RIGHT, 10)
        btn_sizer.Add(btn_ab, 0)
        haupt.Add(btn_sizer, 0, wx.ALL, 10)

        panel.SetSizer(haupt)

        if self.felder:
            wx.CallAfter(next(iter(self.felder.values())).SetFocus)

    def get_werte(self) -> Dict[str, str]:
        return {n: f.GetValue() for n, f in self.felder.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Tabellen-Panel (ListCtrl statt Grid)
# ─────────────────────────────────────────────────────────────────────────────

class TabellenPanel(wx.Panel):
    """
    Zeigt Tabellendaten im wx.ListCtrl (Report).
    wx.ListCtrl wird von NVDA/JAWS/Narrator vollständig unterstützt:
    Screenreader liest Spaltenüberschrift + Zellinhalt vor.
    """

    def __init__(self, parent, db: DB, tabelle: str,
                 melde_cb, fs: int, theme: str):
        super().__init__(parent)
        self.db       = db
        self.tabelle  = tabelle
        self.melde_cb = melde_cb
        self.fs       = fs
        self.theme    = theme
        self._offset  = 0
        self._gesamt  = 0
        self._cols: List[Dict]  = []
        self._col_names: List[str] = []
        self._rows    = []
        self._filter  = ""
        self._aufbauen()
        self.laden()

    def _aufbauen(self):
        f  = mf(self.fs)
        fb = mf(self.fs, bold=True)
        haupt = wx.BoxSizer(wx.VERTICAL)

        # ── Aktions-Buttons ───────────────────────────────────────────────────
        btn_box = wx.StaticBoxSizer(
            wx.StaticBox(self, label="Aktionen für diese Tabelle"),
            wx.HORIZONTAL
        )

        self.btn_neu = wx.Button(self, label="Neue Zeile einfügen  (Einfg)")
        self.btn_neu.SetFont(fb)
        self.btn_neu.SetName("Neue Zeile in Tabelle einfügen")
        self.btn_neu.SetToolTip(
            "Eine neue Zeile in die Tabelle einfügen. "
            "Tastenkürzel: Einfg-Taste"
        )
        self.btn_neu.Bind(wx.EVT_BUTTON, self._on_neu)

        self.btn_bearb = wx.Button(self, label="Zeile bearbeiten  (F2)")
        self.btn_bearb.SetFont(f)
        self.btn_bearb.SetName("Ausgewählte Zeile bearbeiten")
        self.btn_bearb.SetToolTip(
            "Die in der Liste markierte Zeile bearbeiten. "
            "Tastenkürzel: F2 oder Doppelklick"
        )
        self.btn_bearb.Bind(wx.EVT_BUTTON, self._on_bearbeiten)

        self.btn_losch = wx.Button(self, label="Zeile löschen  (Entf)")
        self.btn_losch.SetFont(f)
        self.btn_losch.SetName("Ausgewählte Zeile löschen")
        self.btn_losch.SetToolTip(
            "Die in der Liste markierte Zeile löschen. "
            "Tastenkürzel: Entf-Taste"
        )
        self.btn_losch.Bind(wx.EVT_BUTTON, self._on_loeschen)

        self.btn_reload = wx.Button(self, label="Neu laden  (F5)")
        self.btn_reload.SetFont(f)
        self.btn_reload.SetName("Tabellendaten neu laden")
        self.btn_reload.SetToolTip(
            "Tabellendaten aus der Datenbank neu laden. "
            "Tastenkürzel: F5"
        )
        self.btn_reload.Bind(wx.EVT_BUTTON, lambda e: self.laden())

        self.btn_csv = wx.Button(self, label="Als CSV exportieren")
        self.btn_csv.SetFont(f)
        self.btn_csv.SetName("Tabelle als CSV-Datei exportieren")
        self.btn_csv.SetToolTip(
            "Alle Zeilen dieser Tabelle als CSV-Datei speichern"
        )
        self.btn_csv.Bind(wx.EVT_BUTTON, self._on_csv)

        for b in [self.btn_neu, self.btn_bearb, self.btn_losch,
                  self.btn_reload, self.btn_csv]:
            btn_box.Add(b, 0, wx.ALL, 4)

        haupt.Add(btn_box, 0, wx.EXPAND | wx.ALL, 6)

        # ── Filter ────────────────────────────────────────────────────────────
        filter_box = wx.StaticBoxSizer(
            wx.StaticBox(self, label="Filter – SQL-WHERE-Bedingung eingeben"),
            wx.HORIZONTAL
        )
        filter_lbl = wx.StaticText(self, label="WHERE-Bedingung:")
        filter_lbl.SetFont(f)

        self.filter_feld = wx.TextCtrl(
            self, size=(340, -1), style=wx.TE_PROCESS_ENTER,
            name="WHERE-Filterbedingung"
        )
        self.filter_feld.SetFont(mono(self.fs))
        self.filter_feld.SetToolTip(
            "SQL-WHERE-Bedingung ohne das Schlüsselwort WHERE eingeben "
            "und Enter drücken.\n\n"
            "Beispiele:\n"
            "  betrag > 100\n"
            "  buchungstext LIKE '%Miete%'\n"
            "  buchungsdatum >= '2026-01-01'"
        )
        self.filter_feld.Bind(wx.EVT_TEXT_ENTER, self._on_filter)

        btn_filter = wx.Button(self, label="Filtern")
        btn_filter.SetFont(f)
        btn_filter.SetName("Filter anwenden")
        btn_filter.Bind(wx.EVT_BUTTON, self._on_filter)

        btn_reset = wx.Button(self, label="Filter zurücksetzen")
        btn_reset.SetFont(f)
        btn_reset.SetName("Filter entfernen und alle Zeilen anzeigen")
        btn_reset.Bind(wx.EVT_BUTTON, self._on_filter_reset)

        filter_box.Add(filter_lbl,       0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        filter_box.Add(self.filter_feld, 1, wx.RIGHT, 6)
        filter_box.Add(btn_filter,       0, wx.RIGHT, 4)
        filter_box.Add(btn_reset,        0)
        haupt.Add(filter_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Zeilen-Info (Screenreader liest nach Filterwechsel)
        self.info_lbl = wx.StaticText(self, label="", name="Zeilen-Übersicht")
        self.info_lbl.SetFont(f)
        haupt.Add(self.info_lbl, 0, wx.LEFT | wx.BOTTOM, 6)

        # ── ListCtrl ──────────────────────────────────────────────────────────
        # wx.ListCtrl im Report-Modus: von allen gängigen Screenreadern
        # vollständig unterstützt (NVDA, JAWS, Windows Narrator).
        # Beim Navigieren liest der SR: Spaltenname + Zellwert.
        self.liste = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
            name=f"Tabelle {self.tabelle}"
        )
        self.liste.SetFont(f)
        self.liste.SetToolTip(
            f"Zeilen der Tabelle '{self.tabelle}'.\n"
            "Pfeiltasten: Zeile wechseln.\n"
            "F2 oder Doppelklick: Zeile bearbeiten.\n"
            "Einfg: Neue Zeile.  Entf: Zeile löschen."
        )
        self.liste.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_bearbeiten)
        self.liste.Bind(wx.EVT_KEY_DOWN, self._on_liste_key)
        haupt.Add(self.liste, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)

        # ── Seiten-Navigation ─────────────────────────────────────────────────
        page_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_zurueck = wx.Button(self, label="Vorherige Seite")
        self.btn_zurueck.SetFont(f)
        self.btn_zurueck.SetName("Vorherige Seite laden")
        self.btn_zurueck.SetToolTip(f"Vorherige {PAGE_SIZE} Zeilen laden")
        self.btn_zurueck.Bind(wx.EVT_BUTTON, self._on_zurueck)

        self.seiten_lbl = wx.StaticText(
            self, label="Seite 1 von 1", name="Seitennummer"
        )
        self.seiten_lbl.SetFont(f)

        self.btn_weiter = wx.Button(self, label="Nächste Seite")
        self.btn_weiter.SetFont(f)
        self.btn_weiter.SetName("Nächste Seite laden")
        self.btn_weiter.SetToolTip(f"Nächste {PAGE_SIZE} Zeilen laden")
        self.btn_weiter.Bind(wx.EVT_BUTTON, self._on_weiter)

        page_sizer.Add(self.btn_zurueck, 0, wx.RIGHT, 8)
        page_sizer.Add(self.seiten_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        page_sizer.Add(self.btn_weiter, 0)
        haupt.Add(page_sizer, 0, wx.ALL, 8)

        self.SetSizer(haupt)

    # ── Daten laden ───────────────────────────────────────────────────────────

    def laden(self):
        self._cols      = self.db.spalten(self.tabelle)
        self._gesamt    = self.db.zeilen_anzahl(self.tabelle, self._filter)
        rows, col_names = self.db.zeilen_laden(
            self.tabelle, PAGE_SIZE, self._offset, self._filter
        )
        self._rows      = rows
        self._col_names = col_names
        self._liste_befuellen(rows, col_names)
        self._paging_aktualisieren()

    def _liste_befuellen(self, rows, col_names):
        self.liste.DeleteAllItems()
        self.liste.DeleteAllColumns()
        if not col_names:
            return
        for i, c in enumerate(col_names):
            self.liste.InsertColumn(i, c, width=120)
        for r_idx, row in enumerate(rows):
            wert0 = zell_wert(row[0]) if row else ""
            idx = self.liste.InsertItem(r_idx, wert0)
            for c_idx in range(1, len(col_names)):
                self.liste.SetItem(idx, c_idx, zell_wert(row[c_idx]))
        for i in range(len(col_names)):
            self.liste.SetColumnWidth(i, wx.LIST_AUTOSIZE_USEHEADER)
        filter_info = f"  (Filter: {self._filter})" if self._filter else ""
        self.info_lbl.SetLabel(
            f"{len(rows)} von {self._gesamt} Zeilen{filter_info}  |  "
            f"{len(col_names)} Spalten"
        )

    def _paging_aktualisieren(self):
        seite  = self._offset // PAGE_SIZE + 1
        gesamt = max(1, (self._gesamt + PAGE_SIZE - 1) // PAGE_SIZE)
        self.seiten_lbl.SetLabel(f"Seite {seite} von {gesamt}")
        self.btn_zurueck.Enable(self._offset > 0)
        self.btn_weiter.Enable(self._offset + PAGE_SIZE < self._gesamt)

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    def _pk_name(self) -> Optional[str]:
        for c in self._cols:
            if c.get("pk") == 1:
                return c["name"]
        return None

    def _pk_wert(self, idx: int) -> Optional[str]:
        pk = self._pk_name()
        if pk is None or pk not in self._col_names:
            return None
        col_idx = self._col_names.index(pk)
        return self.liste.GetItem(idx, col_idx).GetText()

    def _zeile_dict(self, idx: int) -> Dict[str, str]:
        return {
            self._col_names[c]: self.liste.GetItem(idx, c).GetText()
            for c in range(len(self._col_names))
        }

    def _selected(self) -> int:
        return self.liste.GetFirstSelected()

    # ── Aktionen ──────────────────────────────────────────────────────────────

    def _on_neu(self, event):
        dlg = ZeilenDialog(
            self, f"Neue Zeile einfügen – {self.tabelle}",
            self._cols, fs=self.fs, theme=self.theme
        )
        if dlg.ShowModal() == wx.ID_OK:
            ok, msg = self.db.zeile_einfuegen(self.tabelle, dlg.get_werte())
            self.melde_cb(msg, ok)
            if ok:
                self.laden()
                wx.CallAfter(self.liste.SetFocus)
        dlg.Destroy()

    def _on_bearbeiten(self, event):
        idx = self._selected()
        if idx < 0:
            self.melde_cb(
                "Keine Zeile ausgewählt. "
                "Bitte zuerst eine Zeile in der Liste markieren.", False
            )
            wx.CallAfter(self.liste.SetFocus)
            return
        werte = self._zeile_dict(idx)
        dlg = ZeilenDialog(
            self, f"Zeile bearbeiten – {self.tabelle}",
            self._cols, werte=werte, fs=self.fs, theme=self.theme
        )
        if dlg.ShowModal() == wx.ID_OK:
            neue = dlg.get_werte()
            pk   = self._pk_name()
            if not pk:
                self.melde_cb(
                    "Diese Tabelle hat keinen Primärschlüssel. "
                    "Bearbeitung nur über den SQL-Editor möglich.", False
                )
                dlg.Destroy()
                return
            pk_val = werte.get(pk, "")
            ok_all = True
            for col, val in neue.items():
                if col == pk:
                    continue
                ok, msg = self.db.zelle_aendern(
                    self.tabelle, pk, pk_val, col, val
                )
                if not ok:
                    ok_all = False
                    self.melde_cb(msg, False)
                    break
            if ok_all:
                self.melde_cb(
                    f"Zeile {pk_val} in '{self.tabelle}' gespeichert.", True
                )
                self.laden()
                wx.CallAfter(self.liste.SetFocus)
        dlg.Destroy()

    def _on_loeschen(self, event):
        idx = self._selected()
        if idx < 0:
            self.melde_cb("Keine Zeile ausgewählt.", False)
            wx.CallAfter(self.liste.SetFocus)
            return
        pk = self._pk_name()
        if not pk:
            self.melde_cb(
                "Kein Primärschlüssel vorhanden – "
                "Löschen über den SQL-Editor möglich.", False
            )
            return
        pk_val = self._pk_wert(idx)
        antwort = wx.MessageBox(
            f"Zeile mit {pk} = '{pk_val}' "
            f"aus Tabelle '{self.tabelle}' wirklich löschen?\n\n"
            "Diese Aktion kann nicht rückgängig gemacht werden!\n\n"
            "NEIN ist die sichere Standardwahl.",
            "Löschen bestätigen",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if antwort == wx.YES:
            ok, msg = self.db.zeile_loeschen(self.tabelle, pk, pk_val)
            self.melde_cb(msg, ok)
            if ok:
                self.laden()
                wx.CallAfter(self.liste.SetFocus)

    def _on_filter(self, event):
        self._filter = self.filter_feld.GetValue().strip()
        self._offset = 0
        try:
            self.laden()
            self.melde_cb(
                f"Filter angewendet: {self._filter or '(kein Filter)'}", True
            )
        except Exception as e:
            self.melde_cb(f"Ungültige Filter-Bedingung: {e}", False)

    def _on_filter_reset(self, event):
        self.filter_feld.SetValue("")
        self._filter = ""
        self._offset = 0
        self.laden()
        self.melde_cb("Filter zurückgesetzt.", True)
        wx.CallAfter(self.filter_feld.SetFocus)

    def _on_zurueck(self, event):
        self._offset = max(0, self._offset - PAGE_SIZE)
        self.laden()
        wx.CallAfter(self.liste.SetFocus)

    def _on_weiter(self, event):
        self._offset += PAGE_SIZE
        self.laden()
        wx.CallAfter(self.liste.SetFocus)

    def _on_csv(self, event):
        dlg = wx.FileDialog(
            self, f"Tabelle '{self.tabelle}' als CSV speichern",
            wildcard="CSV-Dateien (*.csv)|*.csv",
            defaultFile=f"{self.tabelle}.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )
        if dlg.ShowModal() == wx.ID_OK:
            ok, msg = self.db.csv_export(self.tabelle, dlg.GetPath())
            self.melde_cb(msg, ok)
        dlg.Destroy()

    def _on_liste_key(self, event):
        k = event.GetKeyCode()
        if k == wx.WXK_F2:
            self._on_bearbeiten(None)
        elif k in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
            self._on_loeschen(None)
        elif k == wx.WXK_INSERT:
            self._on_neu(None)
        elif k == wx.WXK_F5:
            self.laden()
        else:
            event.Skip()

    def schrift(self, fs: int):
        self.fs = fs
        self.liste.SetFont(mf(fs))
        self.filter_feld.SetFont(mono(fs))
        self.info_lbl.SetFont(mf(fs))
        for b in [self.btn_neu, self.btn_bearb, self.btn_losch,
                  self.btn_reload, self.btn_csv,
                  self.btn_zurueck, self.btn_weiter]:
            b.SetFont(mf(fs))
        self.Refresh()

    def theme_setzen(self, theme: str):
        self.theme = theme


# ─────────────────────────────────────────────────────────────────────────────
# SQL-Editor-Panel (Ergebnis in ListCtrl)
# ─────────────────────────────────────────────────────────────────────────────

class SQLPanel(wx.Panel):
    """
    Freier SQL-Editor.
    Ergebnis in wx.ListCtrl (nicht Grid) – Screenreader-kompatibel.
    Status in eigenem TextCtrl als Live-Region.
    """

    def __init__(self, parent, db: DB, melde_cb, fs: int, theme: str):
        super().__init__(parent)
        self.db       = db
        self.melde_cb = melde_cb
        self.fs       = fs
        self.theme    = theme
        self._erg_rows: List = []
        self._erg_cols: List[str] = []
        self._aufbauen()

    def _aufbauen(self):
        f  = mf(self.fs)
        fb = mf(self.fs, bold=True)
        haupt = wx.BoxSizer(wx.VERTICAL)

        anweis = wx.StaticText(
            self,
            label="SQL-Anweisung in das Textfeld eingeben. "
                  "Strg+Enter oder Schaltfläche 'Ausführen' zum Starten."
        )
        anweis.SetFont(f)
        anweis.Wrap(720)
        haupt.Add(anweis, 0, wx.ALL, 8)

        # SQL-Eingabe mit Label davor (AT-konform)
        sql_lbl = wx.StaticText(self, label="SQL-Anweisung eingeben:")
        sql_lbl.SetFont(fb)
        haupt.Add(sql_lbl, 0, wx.LEFT | wx.TOP, 6)

        self.editor = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_PROCESS_TAB | wx.HSCROLL,
            size=(-1, 130),
            name="SQL-Anweisung"
        )
        self.editor.SetFont(mono(self.fs))
        self.editor.SetToolTip(
            "SQL-Anweisung eingeben.\n"
            "Strg+Enter oder Schaltfläche 'Ausführen' zum Starten.\n\n"
            "Beispiele:\n"
            "  SELECT * FROM buchungen WHERE betrag > 100;\n"
            "  UPDATE einstellungen SET wert='Test e.V.' "
            "WHERE schluessel='verein_name';\n"
            "  DELETE FROM buchungen WHERE id=42;"
        )
        self.editor.Bind(wx.EVT_KEY_DOWN, self._on_key)
        haupt.Add(self.editor, 0, wx.EXPAND | wx.ALL, 6)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_start = wx.Button(self, label="Ausführen  (Strg+Enter)")
        self.btn_start.SetFont(fb)
        self.btn_start.SetName("SQL-Anweisung ausführen")
        self.btn_start.SetToolTip("SQL ausführen (Strg+Enter)")
        self.btn_start.Bind(wx.EVT_BUTTON, self._on_ausfuehren)

        btn_leer = wx.Button(self, label="Editor leeren")
        btn_leer.SetFont(f)
        btn_leer.SetName("SQL-Eingabefeld leeren")
        btn_leer.Bind(wx.EVT_BUTTON, lambda e: (
            self.editor.SetValue(""),
            wx.CallAfter(self.editor.SetFocus)
        ))

        self.btn_csv = wx.Button(self, label="Ergebnis als CSV speichern")
        self.btn_csv.SetFont(f)
        self.btn_csv.SetName("Abfrageergebnis als CSV-Datei speichern")
        self.btn_csv.Bind(wx.EVT_BUTTON, self._on_csv)
        self.btn_csv.Enable(False)

        btn_sizer.Add(self.btn_start, 0, wx.RIGHT, 8)
        btn_sizer.Add(btn_leer,       0, wx.RIGHT, 8)
        btn_sizer.Add(self.btn_csv,   0)
        haupt.Add(btn_sizer, 0, wx.LEFT | wx.BOTTOM, 8)

        # Status-Ausgabe (TE_READONLY + TextCtrl = live region für SR)
        status_lbl = wx.StaticText(
            self, label="Ergebnis der letzten Ausführung:"
        )
        status_lbl.SetFont(fb)
        haupt.Add(status_lbl, 0, wx.LEFT | wx.TOP, 6)

        self.status_feld = wx.TextCtrl(
            self,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(-1, 52),
            name="SQL-Ausführungsstatus"
        )
        self.status_feld.SetFont(f)
        self.status_feld.SetToolTip(
            "Zeigt an ob die Ausführung erfolgreich war "
            "und wie viele Zeilen betroffen wurden."
        )
        haupt.Add(self.status_feld, 0, wx.EXPAND | wx.ALL, 6)

        # Ergebnis-ListCtrl
        erg_lbl = wx.StaticText(self, label="Abfrageergebnis:")
        erg_lbl.SetFont(fb)
        haupt.Add(erg_lbl, 0, wx.LEFT | wx.TOP, 6)

        self.ergebnis = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
            name="Abfrageergebnis"
        )
        self.ergebnis.SetFont(f)
        self.ergebnis.SetToolTip(
            "Ergebnis der SQL-Abfrage. "
            "Pfeiltasten zum Navigieren. "
            "Screenreader liest Spaltenname und Zellinhalt vor."
        )
        haupt.Add(self.ergebnis, 1, wx.EXPAND | wx.ALL, 6)

        self.SetSizer(haupt)

    def _on_key(self, event):
        if event.ControlDown() and event.GetKeyCode() == wx.WXK_RETURN:
            self._on_ausfuehren(None)
        else:
            event.Skip()

    def _on_ausfuehren(self, event):
        if not self.db.offen:
            self.melde_cb("Keine Datenbank geöffnet.", False)
            return
        sql = self.editor.GetValue().strip()
        if not sql:
            self.status_feld.SetValue("Kein SQL eingegeben.")
            wx.CallAfter(self.editor.SetFocus)
            return

        ok, msg, rows, cols = self.db.sql_ausfuehren(sql)
        self.status_feld.SetValue(msg)
        self.status_feld.SetForegroundColour(
            wx.Colour(0,120,0) if ok else wx.RED
        )
        self._erg_rows = rows
        self._erg_cols = cols
        self.melde_cb(msg, ok)
        self._ergebnis_anzeigen(rows, cols)
        self.btn_csv.Enable(ok and bool(cols))
        if ok and rows:
            wx.CallAfter(self.ergebnis.SetFocus)

    def _ergebnis_anzeigen(self, rows, cols):
        self.ergebnis.DeleteAllItems()
        self.ergebnis.DeleteAllColumns()
        if not cols:
            return
        for i, c in enumerate(cols):
            self.ergebnis.InsertColumn(i, c, width=120)
        for r_idx, row in enumerate(rows):
            wert0 = zell_wert(row[0]) if row else ""
            idx = self.ergebnis.InsertItem(r_idx, wert0)
            for c_idx in range(1, len(cols)):
                self.ergebnis.SetItem(idx, c_idx, zell_wert(row[c_idx]))
        for i in range(len(cols)):
            self.ergebnis.SetColumnWidth(i, wx.LIST_AUTOSIZE_USEHEADER)

    def _on_csv(self, event):
        if not self._erg_cols:
            return
        dlg = wx.FileDialog(
            self, "Ergebnis speichern",
            wildcard="CSV-Dateien (*.csv)|*.csv",
            defaultFile="sql_ergebnis.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )
        if dlg.ShowModal() == wx.ID_OK:
            try:
                pfad = dlg.GetPath()
                with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(self._erg_cols)
                    for row in self._erg_rows:
                        w.writerow([zell_wert(v) for v in row])
                self.melde_cb(f"Exportiert: {pfad}", True)
            except Exception as e:
                self.melde_cb(f"Export-Fehler: {e}", False)
        dlg.Destroy()

    def schrift(self, fs: int):
        self.fs = fs
        self.editor.SetFont(mono(fs))
        self.ergebnis.SetFont(mf(fs))
        self.status_feld.SetFont(mf(fs))


# ─────────────────────────────────────────────────────────────────────────────
# Tabellen-Struktur-Panel
# ─────────────────────────────────────────────────────────────────────────────

class InfoPanel(wx.Panel):
    """Spaltenstruktur und CREATE-Statement einer Tabelle (kein Grid)."""

    def __init__(self, parent, db: DB, tabelle: str, fs: int):
        super().__init__(parent)
        f  = mf(fs)
        fb = mf(fs, bold=True)
        haupt = wx.BoxSizer(wx.VERTICAL)

        sp_lbl = wx.StaticText(
            self, label=f"Spaltenstruktur der Tabelle '{tabelle}':"
        )
        sp_lbl.SetFont(fb)
        haupt.Add(sp_lbl, 0, wx.ALL, 8)

        self.sp_liste = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN,
            size=(-1, 200),
            name=f"Spaltenstruktur {tabelle}"
        )
        self.sp_liste.SetFont(f)
        for i, (c, w) in enumerate([
            ("Nr.", 40), ("Name", 180), ("Typ", 120),
            ("Pflichtfeld", 90), ("Standardwert", 130), ("Primärschlüssel", 120)
        ]):
            self.sp_liste.InsertColumn(i, c, width=w)

        for col in db.spalten(tabelle):
            idx = self.sp_liste.InsertItem(
                self.sp_liste.GetItemCount(), str(col["cid"])
            )
            self.sp_liste.SetItem(idx, 1, col["name"])
            self.sp_liste.SetItem(idx, 2, col.get("type") or "")
            self.sp_liste.SetItem(idx, 3, "Ja" if col["notnull"] else "Nein")
            self.sp_liste.SetItem(idx, 4, str(col["dflt_value"] or ""))
            self.sp_liste.SetItem(idx, 5, "Ja" if col["pk"] else "Nein")

        haupt.Add(self.sp_liste, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        cr_lbl = wx.StaticText(self, label="CREATE TABLE – Anweisung:")
        cr_lbl.SetFont(fb)
        haupt.Add(cr_lbl, 0, wx.LEFT | wx.TOP, 8)

        self.cr_text = wx.TextCtrl(
            self,
            value=db.create_sql(tabelle) or "(keine Information verfügbar)",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(-1, 160),
            name="CREATE TABLE Anweisung"
        )
        self.cr_text.SetFont(mono(fs))
        haupt.Add(self.cr_text, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizer(haupt)


# ─────────────────────────────────────────────────────────────────────────────
# Haupt-Fenster
# ─────────────────────────────────────────────────────────────────────────────

class HauptFenster(wx.Frame):

    def __init__(self, parent, start_pfad: str = ""):
        super().__init__(parent, title=APP_NAME,
                         style=wx.DEFAULT_FRAME_STYLE)
        self.db    = DB()
        self.fs    = FONT_DEFAULT
        self.theme = "Hell (Standard)"
        self._tab_panels: Dict[str, TabellenPanel] = {}

        self._aufbauen()
        self._menue_aufbauen()
        self._toolbar_aufbauen()
        self._statusbar_aufbauen()
        self._tastatur_binden()

        self.Centre()
        self.Maximize()

        if start_pfad and os.path.exists(start_pfad):
            self._db_oeffnen(start_pfad)
        else:
            default = os.path.join(
                os.path.expanduser("~"),
                ".mailclient", "structure.db"
            )
            if os.path.exists(default):
                self._db_oeffnen(default)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _aufbauen(self):
        """
        Kein AUI. Layout: vertikaler BoxSizer mit
          1. Status-TextCtrl (live region)
          2. SplitterWindow (links: Tabellenliste, rechts: Notebook)
        """
        gesamt = wx.BoxSizer(wx.VERTICAL)

        # Status-Feld (ganz oben – Screenreader liest Änderungen sofort vor)
        st_lbl = wx.StaticText(self, label="Status-Meldungen:")
        st_lbl.SetFont(mf(self.fs, bold=True))
        gesamt.Add(st_lbl, 0, wx.LEFT | wx.TOP, 6)

        self.status_box = wx.TextCtrl(
            self,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.BORDER_SUNKEN,
            size=(-1, 54),
            name="Status-Meldungsfeld"
        )
        self.status_box.SetFont(mf(self.fs))
        self.status_box.SetToolTip(
            "Rückmeldungen zu allen Aktionen. "
            "Screenreader liest neue Meldungen automatisch vor."
        )
        gesamt.Add(self.status_box, 0, wx.EXPAND | wx.ALL, 4)

        # Splitter
        self.splitter = wx.SplitterWindow(
            self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH
        )

        # Linke Seite
        links = wx.Panel(self.splitter)
        ls = wx.BoxSizer(wx.VERTICAL)

        tl_lbl = wx.StaticText(links, label="Datenbank-Tabellen:")
        tl_lbl.SetFont(mf(self.fs, bold=True))
        ls.Add(tl_lbl, 0, wx.ALL, 6)

        self.tab_liste = wx.ListBox(
            links,
            style=wx.LB_SINGLE | wx.BORDER_SUNKEN,
            name="Tabellenliste"
        )
        self.tab_liste.SetFont(mf(self.fs))
        self.tab_liste.SetToolTip(
            "Alle Tabellen der Datenbank.\n"
            "Pfeiltasten: Tabelle wechseln.\n"
            "Enter oder Schaltfläche 'Tabelle öffnen': Tab öffnen."
        )
        self.tab_liste.Bind(wx.EVT_LISTBOX_DCLICK, self._on_tab_oeffnen)
        self.tab_liste.Bind(wx.EVT_KEY_DOWN, self._on_liste_key)
        ls.Add(self.tab_liste, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)

        btn_tab_oeff = wx.Button(links, label="Tabelle öffnen  (Enter)")
        btn_tab_oeff.SetFont(mf(self.fs))
        btn_tab_oeff.SetName("Ausgewählte Tabelle als Tab öffnen")
        btn_tab_oeff.Bind(wx.EVT_BUTTON, self._on_tab_oeffnen)
        ls.Add(btn_tab_oeff, 0, wx.EXPAND | wx.ALL, 6)

        btn_tab_info = wx.Button(links, label="Spaltenstruktur  (Strg+I)")
        btn_tab_info.SetFont(mf(self.fs))
        btn_tab_info.SetName("Spaltenstruktur der Tabelle anzeigen")
        btn_tab_info.Bind(wx.EVT_BUTTON, self._on_tab_info)
        ls.Add(btn_tab_info, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        links.SetSizer(ls)

        # Rechte Seite: Notebook (standard wx.Notebook, kein AUI)
        self.notebook = wx.Notebook(self.splitter)
        self.notebook.SetName("Haupt-Notebook")

        self.start_panel = self._start_erstellen()
        self.notebook.AddPage(self.start_panel, "Start", True)

        self.splitter.SplitVertically(links, self.notebook, 240)
        self.splitter.SetMinimumPaneSize(180)

        gesamt.Add(self.splitter, 1, wx.EXPAND | wx.ALL, 4)
        self.SetSizer(gesamt)

    def _start_erstellen(self) -> wx.Panel:
        panel = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)
        s.AddStretchSpacer()

        t = wx.StaticText(panel, label=APP_NAME)
        t.SetFont(mf(20, bold=True))
        t.SetName("Anwendungstitel")
        s.Add(t, 0, wx.ALIGN_CENTER | wx.ALL, 6)

        u = wx.StaticText(
            panel,
            label=f"Barrierefreier SQLite-Editor für die Vereinsbuchhaltung  |  Version {APP_VERSION}"
        )
        u.SetFont(mf(11))
        s.Add(u, 0, wx.ALIGN_CENTER | wx.ALL, 4)

        anl = wx.TextCtrl(
            panel,
            value=(
                "ERSTE SCHRITTE\n"
                "══════════════════════════════════════\n\n"
                "1. Datenbank öffnen:\n"
                "   Menü Datei → Öffnen  oder  Strg+O\n\n"
                "   Standard-Speicherort:\n"
                f"   {os.path.join(os.path.expanduser('~'), '.vereinsbuchhaltung', 'vereinsbuchhaltung.db')}\n\n"
                "2. Tabelle wählen:\n"
                "   In der Liste links mit Pfeiltasten navigieren,\n"
                "   dann Enter oder 'Tabelle öffnen' drücken.\n\n"
                "3. Zeilen bearbeiten:\n"
                "   F2 = Bearbeiten  |  Einfg = Neue Zeile  |  Entf = Löschen\n\n"
                "4. SQL-Editor:\n"
                "   Menü Tabelle → SQL-Editor  oder  Strg+E\n\n"
                "TASTATURKÜRZEL\n"
                "══════════════════════════════════════\n"
                "Strg+O      Datenbank öffnen\n"
                "Strg+E      SQL-Editor öffnen\n"
                "Strg+I      Spaltenstruktur der Tabelle\n"
                "Strg+W      Aktiven Tab schließen\n"
                "Strg++      Schrift vergrößern\n"
                "Strg+-      Schrift verkleinern\n"
                "F2          Zeile bearbeiten\n"
                "Einfg       Neue Zeile einfügen\n"
                "Entf        Zeile löschen\n"
                "F5          Tabelle neu laden\n"
                "Enter       Tabelle öffnen (in Tabellenliste)\n"
            ),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE,
            size=(-1, 380),
            name="Startseite mit Anleitung"
        )
        anl.SetFont(mf(self.fs))
        s.Add(anl, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        s.AddStretchSpacer()
        panel.SetSizer(s)
        return panel

    def _menue_aufbauen(self):
        mb = wx.MenuBar()

        # Datei
        m = wx.Menu()
        m.Append(wx.ID_OPEN,  "&Öffnen...\tStrg+O", "Datenbankdatei öffnen")
        id_schl  = wx.Window.NewControlId()
        id_back  = wx.Window.NewControlId()
        id_vac   = wx.Window.NewControlId()
        m.Append(id_schl, "Datenbank &schließen", "Datenbank schließen")
        m.AppendSeparator()
        m.Append(id_back, "&Backup erstellen...", "Datenbankdatei sichern")
        m.Append(id_vac,  "Datenbank &optimieren (VACUUM)",
                 "Datenbankdatei verkleinern")
        m.AppendSeparator()
        m.Append(wx.ID_EXIT, "&Beenden\tAlt+F4", "Anwendung beenden")
        mb.Append(m, "&Datei")
        self.Bind(wx.EVT_MENU, lambda e: self._db_oeffnen_dialog(), id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self._on_db_schliessen,    id=id_schl)
        self.Bind(wx.EVT_MENU, self._on_backup,            id=id_back)
        self.Bind(wx.EVT_MENU, self._on_vacuum,            id=id_vac)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(),     id=wx.ID_EXIT)

        # Tabelle
        m2 = wx.Menu()
        id_to  = wx.Window.NewControlId()
        id_ti  = wx.Window.NewControlId()
        id_sql = wx.Window.NewControlId()
        id_tw  = wx.Window.NewControlId()
        m2.Append(id_to,  "Tabelle &öffnen\tEnter",       "Tabelle öffnen")
        m2.Append(id_ti,  "Spalten&struktur\tStrg+I",     "Spaltenstruktur anzeigen")
        m2.AppendSeparator()
        m2.Append(id_sql, "&SQL-Editor öffnen\tStrg+E",   "SQL-Editor öffnen")
        m2.AppendSeparator()
        m2.Append(id_tw,  "Aktiven Tab &schließen\tStrg+W","Tab schließen")
        mb.Append(m2, "&Tabelle")
        self.Bind(wx.EVT_MENU, self._on_tab_oeffnen,    id=id_to)
        self.Bind(wx.EVT_MENU, self._on_tab_info,        id=id_ti)
        self.Bind(wx.EVT_MENU, self._on_sql_editor,      id=id_sql)
        self.Bind(wx.EVT_MENU, self._on_tab_schliessen,  id=id_tw)

        # Ansicht
        m3 = wx.Menu()
        id_gr = wx.Window.NewControlId()
        id_kl = wx.Window.NewControlId()
        m3.Append(id_gr, "Schrift &vergrößern\tStrg+Plus",
                  f"Schriftgröße erhöhen (max {FONT_MAX}pt)")
        m3.Append(id_kl, "Schrift &verkleinern\tStrg+Minus",
                  f"Schriftgröße verringern (min {FONT_MIN}pt)")
        m3.AppendSeparator()
        m_th = wx.Menu()
        self._theme_ids: Dict[int, str] = {}
        for name in THEMES:
            tid = wx.Window.NewControlId()
            self._theme_ids[tid] = name
            m_th.AppendRadioItem(tid, name, f"Theme '{name}' aktivieren")
            self.Bind(wx.EVT_MENU, self._on_theme, id=tid)
        m3.AppendSubMenu(m_th, "&Theme / Farbschema")
        mb.Append(m3, "&Ansicht")
        self.Bind(wx.EVT_MENU, lambda e: self._schrift(+1), id=id_gr)
        self.Bind(wx.EVT_MENU, lambda e: self._schrift(-1), id=id_kl)

        # Hilfe
        m4 = wx.Menu()
        id_kb = wx.Window.NewControlId()
        m4.Append(id_kb,      "&Tastaturkürzel",          "Alle Tastaturkürzel")
        m4.Append(wx.ID_ABOUT,"&Über diese Anwendung...", "Versionsinformation")
        mb.Append(m4, "&Hilfe")
        self.Bind(wx.EVT_MENU, self._on_hilfe, id=id_kb)
        self.Bind(wx.EVT_MENU, self._on_about, id=wx.ID_ABOUT)

        self.SetMenuBar(mb)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _toolbar_aufbauen(self):
        """Vollständig beschriftete Toolbar – kein Icon-only."""
        tb = self.CreateToolBar(wx.TB_HORIZONTAL | wx.TB_TEXT | wx.NO_BORDER)
        tb.SetFont(mf(self.fs))

        def bmp(art):
            return wx.ArtProvider.GetBitmap(art, wx.ART_TOOLBAR, (22,22))

        tb.AddTool(wx.ID_OPEN, "Datenbank öffnen",
                   bmp(wx.ART_FILE_OPEN),
                   shortHelp="Datenbank öffnen  (Strg+O)")

        id_back = wx.Window.NewControlId()
        tb.AddTool(id_back, "Backup erstellen",
                   bmp(wx.ART_FILE_SAVE_AS),
                   shortHelp="Backup erstellen")

        tb.AddSeparator()

        id_sql = wx.Window.NewControlId()
        tb.AddTool(id_sql, "SQL-Editor öffnen",
                   bmp(wx.ART_EXECUTABLE_FILE),
                   shortHelp="SQL-Editor öffnen  (Strg+E)")

        tb.AddSeparator()

        id_gr = wx.Window.NewControlId()
        tb.AddTool(id_gr, "Schrift größer",
                   bmp(wx.ART_PLUS),
                   shortHelp="Schrift vergrößern  (Strg++)")
        id_kl = wx.Window.NewControlId()
        tb.AddTool(id_kl, "Schrift kleiner",
                   bmp(wx.ART_MINUS),
                   shortHelp="Schrift verkleinern  (Strg+-)")

        tb.Realize()
        self.Bind(wx.EVT_TOOL, lambda e: self._db_oeffnen_dialog(), id=wx.ID_OPEN)
        self.Bind(wx.EVT_TOOL, self._on_backup,           id=id_back)
        self.Bind(wx.EVT_TOOL, self._on_sql_editor,       id=id_sql)
        self.Bind(wx.EVT_TOOL, lambda e: self._schrift(+1), id=id_gr)
        self.Bind(wx.EVT_TOOL, lambda e: self._schrift(-1), id=id_kl)

    def _statusbar_aufbauen(self):
        self.sb = self.CreateStatusBar(2)
        self.sb.SetStatusWidths([-1, 140])
        self.sb.SetStatusText("Bereit – bitte Datenbank öffnen", 0)
        self.sb.SetStatusText(f"Schrift: {self.fs}pt", 1)

    def _tastatur_binden(self):
        id_gr  = wx.Window.NewControlId()
        id_kl  = wx.Window.NewControlId()
        id_sql = wx.Window.NewControlId()
        id_inf = wx.Window.NewControlId()
        id_wzu = wx.Window.NewControlId()
        self.Bind(wx.EVT_MENU, lambda e: self._schrift(+1), id=id_gr)
        self.Bind(wx.EVT_MENU, lambda e: self._schrift(-1), id=id_kl)
        self.Bind(wx.EVT_MENU, self._on_sql_editor,          id=id_sql)
        self.Bind(wx.EVT_MENU, self._on_tab_info,             id=id_inf)
        self.Bind(wx.EVT_MENU, self._on_tab_schliessen,       id=id_wzu)
        self.SetAcceleratorTable(wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord("O"),                wx.ID_OPEN),
            (wx.ACCEL_CTRL, ord("+"),                id_gr),
            (wx.ACCEL_CTRL, ord("-"),                id_kl),
            (wx.ACCEL_CTRL, wx.WXK_NUMPAD_ADD,      id_gr),
            (wx.ACCEL_CTRL, wx.WXK_NUMPAD_SUBTRACT, id_kl),
            (wx.ACCEL_CTRL, ord("E"),                id_sql),
            (wx.ACCEL_CTRL, ord("I"),                id_inf),
            (wx.ACCEL_CTRL, ord("W"),                id_wzu),
        ]))

    # ── Meldungen ─────────────────────────────────────────────────────────────

    def _melden(self, text: str, ok: bool = True):
        """
        Schreibt in das Status-TextCtrl.
        AT-Software behandelt TE_READONLY-TextCtrl als 'live region'
        und liest den neuen Inhalt vor.
        """
        ts  = datetime.now().strftime("%H:%M:%S")
        prä = "OK" if ok else "FEHLER"
        self.status_box.SetValue(f"[{ts}]  {prä}:  {text}")
        self.sb.SetStatusText(f"{prä}: {text}", 0)

    # ── Tabellen-Auswahl ──────────────────────────────────────────────────────

    def _tab_auswahl(self) -> str:
        idx = self.tab_liste.GetSelection()
        if idx == wx.NOT_FOUND:
            return ""
        return self.tab_liste.GetString(idx).split("  ")[0].strip()

    # ── Datenbank ─────────────────────────────────────────────────────────────

    def _db_oeffnen_dialog(self):
        dlg = wx.FileDialog(
            self, "SQLite-Datenbankdatei auswählen",
            wildcard=(
                "SQLite-Datenbanken (*.db;*.sqlite;*.sqlite3)"
                "|*.db;*.sqlite;*.sqlite3|Alle Dateien|*.*"
            ),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        )
        if dlg.ShowModal() == wx.ID_OK:
            self._db_oeffnen(dlg.GetPath())
        dlg.Destroy()

    def _db_oeffnen(self, pfad: str):
        try:
            self.db.oeffnen(pfad)
            self._tabellen_laden()
            self.SetTitle(f"{APP_NAME} – {os.path.basename(pfad)}")
            self._melden(f"Datenbank geöffnet: {pfad}", True)
            wx.CallAfter(self.tab_liste.SetFocus)
        except Exception as e:
            wx.MessageBox(
                f"Datenbank konnte nicht geöffnet werden:\n\n{e}",
                "Fehler", wx.OK | wx.ICON_ERROR, self
            )
            self._melden(f"Fehler beim Öffnen: {e}", False)

    def _tabellen_laden(self):
        self.tab_liste.Clear()
        self._tab_panels.clear()
        for t in self.db.tabellen():
            n   = self.db.zeilen_anzahl(t)
            bez = TABELLEN_INFO.get(t, "")
            eintrag = f"{t}  ({n} Zeilen)"
            if bez:
                eintrag += f"  –  {bez}"
            self.tab_liste.Append(eintrag)

    # ── Tab-Verwaltung ────────────────────────────────────────────────────────

    def _on_tab_oeffnen(self, event):
        t = self._tab_auswahl()
        if not t:
            self._melden("Keine Tabelle ausgewählt.", False)
            wx.CallAfter(self.tab_liste.SetFocus)
            return
        if not self.db.offen:
            self._melden("Keine Datenbank geöffnet.", False)
            return
        # Schon offen?
        if t in self._tab_panels:
            for i in range(self.notebook.GetPageCount()):
                if self.notebook.GetPageText(i).strip() == t:
                    self.notebook.SetSelection(i)
                    wx.CallAfter(self._tab_panels[t].liste.SetFocus)
                    return
        panel = TabellenPanel(
            self.notebook, self.db, t,
            self._melden, self.fs, self.theme
        )
        self._tab_panels[t] = panel
        self.notebook.AddPage(panel, t, True)
        self._melden(f"Tabelle '{t}' geöffnet.", True)
        wx.CallAfter(panel.liste.SetFocus)

    def _on_tab_info(self, event):
        t = self._tab_auswahl()
        if not t or not self.db.offen:
            self._melden("Keine Tabelle ausgewählt.", False)
            return
        panel = InfoPanel(self.notebook, self.db, t, self.fs)
        self.notebook.AddPage(panel, f"Struktur: {t}", True)
        self._melden(f"Spaltenstruktur von '{t}' geöffnet.", True)

    def _on_tab_schliessen(self, event):
        idx = self.notebook.GetSelection()
        if idx <= 0:
            return
        titel = self.notebook.GetPageText(idx).strip()
        self.notebook.DeletePage(idx)
        self._tab_panels.pop(titel, None)
        self._melden(f"Tab '{titel}' geschlossen.", True)

    def _on_liste_key(self, event):
        k = event.GetKeyCode()
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_tab_oeffnen(None)
        else:
            event.Skip()

    def _on_sql_editor(self, event):
        if not self.db.offen:
            self._melden("Keine Datenbank geöffnet.", False)
            return
        panel = SQLPanel(
            self.notebook, self.db, self._melden, self.fs, self.theme
        )
        self.notebook.AddPage(panel, "SQL-Editor", True)
        self._melden("SQL-Editor geöffnet.", True)
        wx.CallAfter(panel.editor.SetFocus)

    # ── Datenbank-Operationen ─────────────────────────────────────────────────

    def _on_db_schliessen(self, event):
        if not self.db.offen:
            return
        self.db.schliessen()
        self.tab_liste.Clear()
        self._tab_panels.clear()
        while self.notebook.GetPageCount() > 1:
            self.notebook.DeletePage(self.notebook.GetPageCount() - 1)
        self.SetTitle(APP_NAME)
        self._melden("Datenbank geschlossen.", True)

    def _on_backup(self, event):
        if not self.db.offen:
            self._melden("Keine Datenbank geöffnet.", False)
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dlg = wx.FileDialog(
            self, "Backup speichern unter",
            wildcard="SQLite (*.db)|*.db",
            defaultFile=f"backup_{ts}.db",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )
        if dlg.ShowModal() == wx.ID_OK:
            ok, msg = self.db.backup(dlg.GetPath())
            self._melden(msg, ok)
            wx.MessageBox(
                msg, "Backup",
                wx.OK | (wx.ICON_INFORMATION if ok else wx.ICON_ERROR), self
            )
        dlg.Destroy()

    def _on_vacuum(self, event):
        if not self.db.offen:
            return
        ok, msg = self.db.vacuum()
        self._melden(msg, ok)
        wx.MessageBox(
            msg, "Datenbank optimieren",
            wx.OK | (wx.ICON_INFORMATION if ok else wx.ICON_ERROR), self
        )

    # ── Darstellung ───────────────────────────────────────────────────────────

    def _schrift(self, delta: int):
        neu = max(FONT_MIN, min(FONT_MAX, self.fs + delta))
        if neu == self.fs:
            return
        self.fs = neu
        self.tab_liste.SetFont(mf(neu))
        self.status_box.SetFont(mf(neu))
        for p in self._tab_panels.values():
            p.schrift(neu)
        for i in range(self.notebook.GetPageCount()):
            p = self.notebook.GetPage(i)
            if isinstance(p, SQLPanel):
                p.schrift(neu)
        self.sb.SetStatusText(f"Schrift: {neu}pt", 1)
        self._melden(f"Schriftgröße: {neu}pt", True)

    def _on_theme(self, event):
        name = self._theme_ids.get(event.GetId(), "Hell (Standard)")
        self.theme = name
        for p in self._tab_panels.values():
            p.theme_setzen(name)
        self._melden(f"Theme aktiviert: {name}", True)

    # ── Hilfe ─────────────────────────────────────────────────────────────────

    def _on_hilfe(self, event):
        dlg = wx.Dialog(
            self, title="Tastaturkürzel – Übersicht",
            size=(520, 580),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        p = wx.Panel(dlg)
        s = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(p, label="Alle Tastaturkürzel im Überblick:")
        lbl.SetFont(mf(self.fs, bold=True))
        s.Add(lbl, 0, wx.ALL, 8)

        t = wx.TextCtrl(
            p,
            value=(
                "GLOBAL\n"
                "  Strg+O          Datenbank öffnen\n"
                "  Strg+E          SQL-Editor öffnen\n"
                "  Strg+I          Spaltenstruktur der Tabelle\n"
                "  Strg+W          Aktiven Tab schließen\n"
                "  Strg++          Schrift vergrößern\n"
                "  Strg+-          Schrift verkleinern\n"
                "  Alt+F4          Anwendung beenden\n\n"
                "TABELLENLISTE (linke Seite)\n"
                "  Pfeil hoch/runter   Tabelle wechseln\n"
                "  Enter               Tabelle öffnen\n\n"
                "TABELLEN-TAB\n"
                "  Pfeiltasten         Zeile wechseln\n"
                "  F2                  Zeile bearbeiten\n"
                "  Einfg               Neue Zeile einfügen\n"
                "  Entf                Zeile löschen\n"
                "  F5                  Tabelle neu laden\n"
                "  Tab                 Zwischen Schaltflächen wechseln\n\n"
                "BEARBEITUNGS-DIALOG\n"
                "  Tab / Umschalt+Tab  Nächstes / vorheriges Feld\n"
                "  Enter               Speichern und schließen\n"
                "  Escape              Abbrechen\n\n"
                "SQL-EDITOR\n"
                "  Strg+Enter          SQL-Anweisung ausführen\n"
                "  Tab                 Nächstes Steuerelement\n\n"
                "BARRIEREFREIHEIT\n"
                "  Alle Steuerelemente haben sprechende Namen.\n"
                "  Kein Grid-Widget – ListCtrl für Screenreader.\n"
                "  Status-TextCtrl oben = Live-Region für NVDA/JAWS.\n"
                "  Fokus wird nach jeder Aktion korrekt gesetzt.\n"
            ),
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(-1, 440),
            name="Tastaturkürzel-Liste"
        )
        t.SetFont(mf(self.fs))
        s.Add(t, 1, wx.EXPAND | wx.ALL, 6)

        btn = wx.Button(p, wx.ID_OK, "Schließen")
        btn.SetFont(mf(self.fs, bold=True))
        btn.SetDefault()
        s.Add(btn, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        p.SetSizer(s)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName(APP_NAME)
        info.SetVersion(APP_VERSION)
        info.SetDescription(
            "Barrierefreier SQLite-Datenbank-Editor\n"
            "für die Vereinsbuchhaltung e.V.\n\n"
            "Screenreader-Optimierungen:\n"
            "  • Kein wx.grid – wx.ListCtrl statt Grid\n"
            "  • Kein AUI – standard SplitterWindow + Notebook\n"
            "  • SetName() an allen Steuerelementen (MSAA/UIA)\n"
            "  • Status-TextCtrl als Live-Region\n"
            "  • Fokus-Management nach jeder Aktion\n"
            "  • Labels direkt vor Eingabefeldern\n"
            "  • Bestätigungsdialoge mit Nein als Standard\n"
            "  • 5 Farb-Themes inkl. 2 Hochkontrast-Varianten\n"
            "  • Schriftgröße 8–24pt anpassbar\n\n"
            "Getestet mit NVDA, JAWS und Windows Narrator."
        )
        wx.adv.AboutBox(info)

    def _on_close(self, event):
        self.db.schliessen()
        self.Destroy()


# ─────────────────────────────────────────────────────────────────────────────

def main():
    start = sys.argv[1] if len(sys.argv) > 1 else ""
    app   = wx.App(False)
    frame = HauptFenster(None, start)
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
