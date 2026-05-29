"""
version_info.py – Liest die App-Version aus version.txt (PyInstaller-Format).

PyInstaller bettet version.txt als Windows-VERSIONINFO ein. Nach dem
Kompilieren ist die Datei NICHT mehr im Dateisystem vorhanden.
Stattdessen steht die Version in sys.frozen-Umgebung im EXE-Metadaten.

Strategie (in dieser Reihenfolge):
  1. Laufende .exe → win32api.GetFileVersionInfo()
  2. Entwicklungsumgebung → version.txt parsen (Regex auf ProductVersion)
  3. Fallback → "0.0.0.1"
"""

from __future__ import annotations
import os
import sys
import re


def get_version() -> str:
    """Gibt die Versionszeichenkette zurück, z.B. '0.0.0.1'."""

    # --- 1. Kompilierte EXE (PyInstaller frozen) ---
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        try:
            import win32api  # type: ignore
            info = win32api.GetFileVersionInfo(exe_path, "\\StringFileInfo\\040904B0\\ProductVersion")
            if info:
                return str(info).strip()
        except Exception:
            pass
        # Fallback: FixedFileInfo direkt lesen
        try:
            import win32api  # type: ignore
            info = win32api.GetFileVersionInfo(exe_path, "\\")
            ms   = info["ProductVersionMS"]
            ls   = info["ProductVersionLS"]
            major = (ms >> 16) & 0xFFFF
            minor = ms & 0xFFFF
            patch = (ls >> 16) & 0xFFFF
            build = ls & 0xFFFF
            return f"{major}.{minor}.{patch}.{build}"
        except Exception:
            pass

    # --- 2. Entwicklungsumgebung: version.txt parsen ---
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    version_file = os.path.join(base, "version.txt")

    if os.path.exists(version_file):
        try:
            content = open(version_file, encoding="utf-8").read()
            # Sucht: StringStruct(u'ProductVersion', u'1.2.3.4')
            m = re.search(r"ProductVersion['\"\s,u]+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", content)
            if m:
                return m.group(1)
            # Alternativ: prodvers=(1, 2, 3, 4)
            m2 = re.search(r"prodvers\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", content)
            if m2:
                return ".".join(m2.groups())
        except Exception:
            pass

    return "0.0.0.1"


APP_VERSION = get_version()
