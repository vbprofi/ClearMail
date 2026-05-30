"""
version_info.py – Liest die App-Version zuverlässig in allen Umgebungen.

Strategie (in dieser Reihenfolge):
  1. Frozen EXE: win32api.GetFileVersionInfo() – StringFileInfo (mehrere Codepages)
  2. Frozen EXE: win32api.GetFileVersionInfo() – FixedFileInfo Bit-Arithmetik
  3. Frozen EXE: struct-basiertes Lesen der PE-VERSIONINFO (kein win32api nötig)
  4. version.txt im _MEIPASS-Verzeichnis (PyInstaller datas)
  5. version.txt im Skript-Verzeichnis (Entwicklungsumgebung)
  6. Fallback "0.0.0.1"
"""

from __future__ import annotations
import os, sys, re


def _read_pe_version(exe_path: str) -> str | None:
    """
    Liest die ProductVersion direkt aus der PE-VERSIONINFO-Ressource der EXE.
    Funktioniert ohne win32api – nur mit stdlib struct + open().
    Gibt "Major.Minor.Patch.Build" zurück oder None.
    """
    try:
        import struct
        with open(exe_path, "rb") as f:
            data = f.read()
        # Suche nach VS_VERSION_INFO Magic (0xFEEF04BD als Little-Endian DWORD)
        magic = b"\xbd\x04\xef\xfe"
        idx = data.find(magic)
        if idx == -1:
            return None
        # FixedFileInfo-Struktur beginnt 4 Bytes vor dem Magic
        # Offset von magic: dwSignature(4) = das magic selbst
        # ProductVersionMS ist bei Offset +24, ProductVersionLS bei +28
        if idx + 32 > len(data):
            return None
        ms = struct.unpack_from("<I", data, idx + 16)[0]
        ls = struct.unpack_from("<I", data, idx + 20)[0]
        major = (ms >> 16) & 0xFFFF
        minor =  ms        & 0xFFFF
        patch = (ls >> 16) & 0xFFFF
        build =  ls        & 0xFFFF
        if any(p > 0 for p in (major, minor, patch, build)):
            return f"{major}.{minor}.{patch}.{build}"
    except Exception:
        pass
    return None


def get_version() -> str:
    """Gibt die Versionszeichenkette zurück, z.B. '0.0.0.3'."""

    # ---- 1+2+3: Kompilierte EXE ----
    if getattr(sys, "frozen", False):
        exe = sys.executable

        # Versuch 1: win32api StringFileInfo (mehrere Codepages)
        for codepage in ("040904B0", "040904E4", "04090000", "000004B0"):
            try:
                import win32api  # type: ignore
                v = win32api.GetFileVersionInfo(
                    exe, f"\\StringFileInfo\\{codepage}\\ProductVersion")
                if v and str(v).strip():
                    return str(v).strip()
            except Exception:
                pass

        # Versuch 2: win32api FixedFileInfo
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

        # Versuch 3: struct-basiertes PE-Lesen (kein win32api)
        v = _read_pe_version(exe)
        if v:
            return v

    # ---- 4+5: version.txt lesen ----
    search_dirs: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_dirs.append(meipass)
    # Skript-Verzeichnis (auch: Verzeichnis dieser Datei)
    for candidate in (
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv else "",
    ):
        if candidate and candidate not in search_dirs:
            search_dirs.append(candidate)

    for base in search_dirs:
        vfile = os.path.join(base, "version.txt")
        if not os.path.exists(vfile):
            continue
        try:
            content = open(vfile, encoding="utf-8").read()
            # Format: StringStruct(u'ProductVersion', u'0.0.0.3')
            m = re.search(
                r"ProductVersion['\"\s,u]+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
                content)
            if m: return m.group(1)
            # Format: prodvers=(0, 0, 0, 3)
            m2 = re.search(
                r"prodvers\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
                content)
            if m2: return ".".join(m2.groups())
            # Format: FileVersion=0.0.0.3
            m3 = re.search(
                r"FileVersion['\"\s=:,u]+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
                content)
            if m3: return m3.group(1)
        except Exception:
            pass

    return "0.0.0.1"


APP_VERSION = get_version()
