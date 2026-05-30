"""
date_utils.py – Datums-/Uhrzeitformatierung nach Systemgebietsschema.

Nutzt babel (falls installiert) oder Windows-API (GetLocaleInfoEx)
als Fallback auf strftime mit gesetztem Locale.
Niemals explizites locale.setlocale() – das ist nicht threadsicher.
"""
from __future__ import annotations
from datetime import datetime
import sys


def _get_system_locale() -> str:
    """Ermittelt das Systemgebietsschema ohne locale.setlocale()."""
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)
            return buf.value  # z.B. "de-DE", "en-US"
        except Exception:
            pass
    # POSIX: aus Umgebungsvariablen lesen
    import os
    for var in ("LC_TIME", "LC_ALL", "LANG"):
        v = os.environ.get(var, "")
        if v and v != "C":
            return v.split(".")[0]  # "de_DE.UTF-8" → "de_DE"
    return ""


_LOCALE_CODE: str | None = None


def _locale_code() -> str:
    global _LOCALE_CODE
    if _LOCALE_CODE is None:
        _LOCALE_CODE = _get_system_locale()
    return _LOCALE_CODE


def _try_babel(dt: datetime, fmt: str) -> str | None:
    """Formatiert mit babel falls installiert."""
    try:
        from babel.dates import format_datetime, format_date, format_time
        lc = _locale_code() or "de_DE"
        if fmt == "time":
            return format_time(dt, format="short", locale=lc)
        elif fmt == "date_short":
            return format_date(dt, format="short", locale=lc)
        elif fmt == "date_medium":
            return format_date(dt, format="medium", locale=lc)
        elif fmt == "datetime_medium":
            return format_datetime(dt, format="medium", locale=lc)
        elif fmt == "date_full":
            return format_date(dt, format="full", locale=lc)
    except ImportError:
        pass
    except Exception:
        pass
    return None


def _strftime_locale(dt: datetime, fmt_str: str) -> str:
    """Nutzt strftime mit temporär gesetzter Locale (threadsicher auf Windows via ctypes)."""
    try:
        if sys.platform == "win32":
            # Windows: _strftime nutzt die Thread-Locale über SetThreadLocale
            import ctypes, locale
            lc = _locale_code()
            if lc:
                # LCID aus Locale-Name
                lcid = ctypes.windll.kernel32.LocaleNameToLCID(lc, 0)
                if lcid:
                    ctypes.windll.kernel32.SetThreadLocale(lcid)
            return dt.strftime(fmt_str)
        else:
            import locale
            lc = _locale_code()
            if lc:
                saved = locale.getlocale(locale.LC_TIME)
                try:
                    locale.setlocale(locale.LC_TIME, lc)
                    return dt.strftime(fmt_str)
                finally:
                    try: locale.setlocale(locale.LC_TIME, saved)
                    except Exception: pass
    except Exception:
        pass
    return dt.strftime(fmt_str)


def format_date_list(date_str: str) -> str:
    """
    Datum für die Mailliste (kompakt).
    Heute: nur Uhrzeit, dieses Jahr: Tag+Mon+Uhr, sonst: volles Datum
    """
    if not date_str:
        return ""
    try:
        dt  = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()

        if dt.date() == now.date():
            return _try_babel(dt, "time") or _strftime_locale(dt, "%H:%M")
        elif dt.year == now.year:
            r = _try_babel(dt, "date_medium")
            if r: return r
            return _strftime_locale(dt, "%d. %b %H:%M")
        else:
            return _try_babel(dt, "date_short") or _strftime_locale(dt, "%x")
    except ValueError:
        return date_str[:16]


def format_date_preview(date_str: str) -> str:
    """Datum für die Vorschau (ausführlich mit Wochentag)."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        r  = _try_babel(dt, "datetime_medium")
        if r: return r
        return _strftime_locale(dt, "%A, %x %X")
    except ValueError:
        return date_str
