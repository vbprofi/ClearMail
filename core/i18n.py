"""
i18n – Internationalisierung / Mehrsprachigkeit

Sprachdateien: locale/<lang_code>/messages.json
Addons können eigene Sprachdateien mitbringen:
  addons/<addon_name>/locale/<lang_code>/messages.json

Verwendung:
    from core.i18n import tr, set_language, get_available_languages
    tr("menu_file")           → "Datei" (aktuell gewählte Sprache)
    tr("status_messages", count=5) → "5 Nachricht(en)"
"""

from __future__ import annotations
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_DIR = os.path.join(BASE_DIR, "locale")

_current_lang: str = "de"
_strings: dict = {}
_fallback: dict = {}


def _load_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _load_language(lang: str) -> dict:
    """Lädt messages.json für die gewünschte Sprache."""
    path = os.path.join(LOCALE_DIR, lang, "messages.json")
    return _load_file(path)


def set_language(lang: str):
    """Setzt die aktive Sprache. Lädt Fallback (de) zuerst, dann Zielsprache."""
    global _current_lang, _strings, _fallback
    _current_lang = lang
    _fallback = _load_language("de")
    _strings  = _load_language(lang) if lang != "de" else _fallback.copy()


def load_addon_translations(addon_dir: str, lang: str):
    """
    Lädt addon-eigene Übersetzungen und fügt sie in _strings ein.
    Addon-Sprachdatei: <addon_dir>/locale/<lang>/messages.json
    """
    path = os.path.join(addon_dir, "locale", lang, "messages.json")
    extra = _load_file(path)
    if extra:
        _strings.update(extra)
        # Fallback mit DE-Datei des Addons ergänzen
        fb_path = os.path.join(addon_dir, "locale", "de", "messages.json")
        fb = _load_file(fb_path)
        for k, v in fb.items():
            _fallback.setdefault(k, v)


def tr(key: str, **kwargs) -> str:
    """
    Gibt den übersetzten String zurück.
    Platzhalter werden via str.format(**kwargs) ersetzt.
    Fallback: DE-Wert, dann key selbst.
    """
    text = _strings.get(key) or _fallback.get(key) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def get_available_languages() -> list[tuple[str, str]]:
    """
    Gibt alle verfügbaren Sprachen zurück: [(code, display_name), ...]
    Erkennt automatisch alle Unterverzeichnisse in locale/.
    """
    result = []
    if not os.path.isdir(LOCALE_DIR):
        return [("de", "Deutsch")]
    for entry in sorted(os.scandir(LOCALE_DIR), key=lambda e: e.name):
        if entry.is_dir():
            msg_file = os.path.join(entry.path, "messages.json")
            if os.path.exists(msg_file):
                # Anzeigename aus Datei lesen (Schlüssel "lang_name"), Fallback = Code
                data = _load_file(msg_file)
                name = data.get("lang_name", entry.name)
                result.append((entry.name, name))
    return result if result else [("de", "Deutsch")]


def current_language() -> str:
    return _current_lang


# Beim Import direkt Deutsch laden als Standard
set_language("de")
