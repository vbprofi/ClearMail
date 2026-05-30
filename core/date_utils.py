"""
date_utils.py – Einheitliche Datums-/Uhrzeitformatierung nach Sprachraum.

DE: Montag, 25.09.2025 um 12:01 Uhr  (Preview)
    25.09.25 12:01                     (Liste, dieses Jahr)
    12:01                              (Liste, heute)

EN: Monday, September 25, 2025 at 12:01 PM  (Preview)
    Sep 25, 2025 12:01 PM                    (Liste)
    12:01 PM                                 (Liste, heute)

Nutzt babel (bevorzugt) oder Windows-API + strftime als Fallback.
"""
from __future__ import annotations
from datetime import datetime
import sys
import os


# ------------------------------------------------------------------ #
#  Gebietsschema ermitteln                                            #
# ------------------------------------------------------------------ #

_LOCALE_CODE: str | None = None


def _detect_locale() -> str:
    """Ermittelt Systemgebietsschema ohne locale.setlocale()."""
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)
            lc = buf.value  # "de-DE", "en-US", ...
            if lc:
                return lc
        except Exception:
            pass
    for var in ("LC_TIME", "LC_ALL", "LANG", "LANGUAGE"):
        v = os.environ.get(var, "")
        if v and v not in ("C", "POSIX"):
            return v.split(".")[0].replace("_", "-")
    return "de-DE"


def locale_code() -> str:
    global _LOCALE_CODE
    if _LOCALE_CODE is None:
        _LOCALE_CODE = _detect_locale()
    return _LOCALE_CODE


def is_german() -> bool:
    lc = locale_code().lower()
    return lc.startswith("de") or lc.startswith("at") or lc.startswith("ch")


# ------------------------------------------------------------------ #
#  Babel-Formatierung                                                 #
# ------------------------------------------------------------------ #

def _babel_time(dt: datetime) -> str | None:
    try:
        from babel.dates import format_time
        return format_time(dt, format="short", locale=locale_code())
    except Exception:
        return None


def _babel_date_short(dt: datetime) -> str | None:
    try:
        from babel.dates import format_date
        return format_date(dt, format="short", locale=locale_code())
    except Exception:
        return None


def _babel_datetime_full(dt: datetime) -> str | None:
    """Vollständiges Datum mit Wochentag für Preview."""
    try:
        from babel.dates import format_datetime
        lc = locale_code()
        if is_german():
            # "Montag, 25.09.2025 um 12:01 Uhr"
            result = format_datetime(dt, format="EEEE, dd.MM.yyyy", locale=lc)
            time   = format_datetime(dt, format="HH:mm", locale=lc)
            return f"{result} um {time} Uhr"
        else:
            # "Monday, September 25, 2025 at 12:01 PM"
            return format_datetime(dt, format="full", locale=lc)
    except Exception:
        return None


# ------------------------------------------------------------------ #
#  Windows-API-Fallback                                               #
# ------------------------------------------------------------------ #

def _win_strftime(dt: datetime, fmt: str) -> str:
    """Setzt Thread-Locale temporär (threadsicher) dann strftime."""
    if sys.platform == "win32":
        try:
            import ctypes
            lc  = locale_code()
            if lc:
                lcid = ctypes.windll.kernel32.LocaleNameToLCID(lc, 0)
                if lcid:
                    ctypes.windll.kernel32.SetThreadLocale(lcid)
        except Exception:
            pass
    return dt.strftime(fmt)


# ------------------------------------------------------------------ #
#  Öffentliche Funktionen                                             #
# ------------------------------------------------------------------ #

def format_date_list(date_str: str) -> str:
    """
    Kompaktes Datum für die Mailliste.
    Heute → Uhrzeit | dieses Jahr → Kurzdatum + Uhr | älter → Kurzdatum
    """
    if not date_str:
        return ""
    try:
        dt  = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()

        if dt.date() == now.date():
            return _babel_time(dt) or _win_strftime(dt, "%H:%M")
        elif dt.year == now.year:
            d = _babel_date_short(dt) or _win_strftime(dt, "%d.%m.%y" if is_german() else "%b %d")
            t = _babel_time(dt)       or _win_strftime(dt, "%H:%M")
            return f"{d} {t}"
        else:
            return _babel_date_short(dt) or _win_strftime(dt, "%d.%m.%Y" if is_german() else "%m/%d/%Y")
    except ValueError:
        return date_str[:16]


def format_date_preview(date_str: str) -> str:
    """
    Ausführliches Datum für Vorschau und Nachrichtenfenster.
    DE: Montag, 25.09.2025 um 12:01 Uhr
    EN: Monday, September 25, 2025 at 12:01 PM
    """
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        r  = _babel_datetime_full(dt)
        if r:
            return r
        # Fallback ohne babel
        if is_german():
            wd = _win_strftime(dt, "%A")
            dm = _win_strftime(dt, "%d.%m.%Y")
            hm = _win_strftime(dt, "%H:%M")
            return f"{wd}, {dm} um {hm} Uhr"
        else:
            return _win_strftime(dt, "%A, %B %d, %Y at %I:%M %p")
    except ValueError:
        return date_str
