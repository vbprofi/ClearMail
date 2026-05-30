"""
version_info.py – Liest die App-Version zuverlässig in allen Umgebungen.

Strategie:
  1. Frozen EXE + win32api → GetFileVersionInfo() (StringFileInfo)
  2. Frozen EXE + win32api → GetFileVersionInfo() (FixedFileInfo Bit-Arithmetik)
  3. version.txt im _MEIPASS-Verzeichnis (PyInstaller bundelt es via datas)
  4. version.txt im Skript-Verzeichnis (Entwicklungsumgebung)
  5. Fallback "0.0.0.1"
"""

from __future__ import annotations
import os, sys, re


def get_version() -> str:

    # ---- 1+2: Kompilierte EXE (win32api) ----
    if getattr(sys, "frozen", False):
        exe = sys.executable
        # Versuch 1: StringFileInfo (bevorzugt – gibt "0.0.0.3" zurück)
        for codepage in ("040904B0", "040904E4", "04090000", "000004B0"):
            try:
                import win32api  # type: ignore
                v = win32api.GetFileVersionInfo(
                    exe, f"\\StringFileInfo\\{codepage}\\ProductVersion")
                if v and str(v).strip():
                    return str(v).strip()
            except Exception:
                pass

        # Versuch 2: FixedFileInfo Bit-Arithmetik
        try:
            import win32api  # type: ignore
            info = win32api.GetFileVersionInfo(exe, "\\")
            ms, ls = info["ProductVersionMS"], info["ProductVersionLS"]
            parts = [(ms >> 16) & 0xFFFF, ms & 0xFFFF,
                     (ls >> 16) & 0xFFFF, ls & 0xFFFF]
            if any(p > 0 for p in parts):
                return ".".join(str(p) for p in parts)
        except Exception:
            pass

    # ---- 3+4: version.txt lesen ----
    search_dirs = []
    if getattr(sys, "_MEIPASS", None):
        search_dirs.append(sys._MEIPASS)          # PyInstaller _MEIPASS
    search_dirs.append(os.path.dirname(os.path.abspath(__file__)))  # Skript-Dir

    for base in search_dirs:
        vfile = os.path.join(base, "version.txt")
        if not os.path.exists(vfile):
            continue
        try:
            content = open(vfile, encoding="utf-8").read()

            # Format: StringStruct(u'ProductVersion', u'0.0.0.3')
            m = re.search(
                r"ProductVersion['\"\s,u]*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
                content
            )
            if m:
                return m.group(1)

            # Format: prodvers=(0, 0, 0, 3)
            m2 = re.search(
                r"prodvers\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
                content
            )
            if m2:
                return ".".join(m2.groups())

            # Format: FileVersion=0.0.0.3
            m3 = re.search(r"FileVersion['\"\s=:,u]*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", content)
            if m3:
                return m3.group(1)
        except Exception:
            pass

    return "0.0.0.1"


APP_VERSION = get_version()
