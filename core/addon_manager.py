"""
AddonManager – Plugin/Addon-System

Addon-Verzeichnisse (werden beide gescannt, in dieser Reihenfolge):
  1. <app_dir>/addons/          – mitgelieferte Addons im Programmverzeichnis
  2. ~/.mailclient/addons/      – benutzerdefinierte Addons
"""

from __future__ import annotations
import os
import sys
import importlib.util
from typing import Dict, List, Callable


class AddonBase:
    """Basisklasse für alle Addons."""

    NAME: str        = "UnnamedAddon"
    VERSION: str     = "0.0.1"
    DESCRIPTION: str = ""

    def __init__(self, controller):
        self.controller = controller

    # Lifecycle
    def on_load(self):   pass
    def on_unload(self): pass

    # Mail-Hooks
    def on_mail_read(self,     data: dict): pass
    def on_mail_deleted(self,  data: dict): pass
    def on_mail_moved(self,    data: dict): pass
    def on_mail_sent(self,     data: dict): pass
    def on_mail_received(self, data: dict): pass

    # UI-Hooks
    def get_menu_items(self) -> list:
        """Format: [{"label": str, "handler": callable}, ...]"""
        return []

    def get_folder_context_items(self, item_type: str, item_data: dict) -> list:
        """Format: [{"label": str, "handler": callable(item, data), "enabled": bool}, ...]"""
        return []

    def get_toolbar_items(self) -> list:
        return []

    def get_preview_panel(self):
        return None

    # PGP-Hooks
    def on_pgp_decrypt(self, mail_data: dict) -> dict: return mail_data
    def on_pgp_encrypt(self, mail_data: dict) -> dict: return mail_data


class AddonManager:
    """Verwaltet alle geladenen Addons aus mehreren Verzeichnissen."""

    def __init__(self, app_dir: str = None, user_dir: str = None):
        # App-Verzeichnis: <main.py-Ordner>/addons/
        if app_dir is None:
            app_dir = os.path.join(
                os.path.dirname(os.path.abspath(sys.argv[0])), "addons"
            )
        # Benutzer-Verzeichnis: ~/.mailclient/addons/
        if user_dir is None:
            user_dir = os.path.join(os.path.expanduser("~"), ".mailclient", "addons")

        self.app_dir  = app_dir
        self.user_dir = user_dir
        # Primäres Install-Ziel für neue Addons
        self.addon_dir = user_dir

        os.makedirs(app_dir,  exist_ok=True)
        os.makedirs(user_dir, exist_ok=True)

        self._addons: Dict[str, AddonBase]        = {}
        self._hooks:  Dict[str, List[Callable]]   = {}
        # Merkt sich den Pfad jedes Addons (für Reload)
        self._addon_paths: Dict[str, str]          = {}

    # ------------------------------------------------------------------ #
    #  Scan & Load                                                        #
    # ------------------------------------------------------------------ #

    def scan_addon_dir(self) -> List[str]:
        """
        Gibt alle verfügbaren Addon-Namen zurück (aus beiden Verzeichnissen).
        user_dir hat Vorrang bei Namenskollision.
        """
        found: Dict[str, str] = {}  # name -> directory

        for directory in (self.app_dir, self.user_dir):
            if not os.path.isdir(directory):
                continue
            for entry in sorted(os.scandir(directory), key=lambda e: e.name):
                if entry.is_dir():
                    init = os.path.join(entry.path, "__init__.py")
                    if os.path.exists(init):
                        found[entry.name] = directory

        return list(found.keys())

    def _find_addon_path(self, name: str) -> str | None:
        """Gibt den Pfad zur __init__.py eines Addons zurück."""
        # user_dir hat Vorrang
        for directory in (self.user_dir, self.app_dir):
            path = os.path.join(directory, name, "__init__.py")
            if os.path.exists(path):
                return path
        return None

    def load_addon(self, name: str, controller) -> bool:
        """Lädt ein Addon. Gibt True bei Erfolg zurück."""
        addon_path = self._find_addon_path(name)
        if not addon_path:
            print(f"Addon '{name}': __init__.py nicht gefunden.")
            return False

        spec   = importlib.util.spec_from_file_location(f"addon_{name}", addon_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Addon '{name}' Ladefehler: {e}")
            return False

        cls = getattr(module, "Addon", None)
        if cls is None or not issubclass(cls, AddonBase):
            print(f"Addon '{name}': keine Klasse 'Addon(AddonBase)' gefunden.")
            return False

        # Altes Addon entladen falls vorhanden
        if name in self._addons:
            self.unload_addon(name)

        try:
            instance = cls(controller)
            instance.on_load()
        except Exception as e:
            print(f"Addon '{name}' on_load() Fehler: {e}")
            return False

        self._addons[name]      = instance
        self._addon_paths[name] = addon_path
        self._register_hooks(instance)
        return True

    def load_all(self, controller):
        """Lädt alle verfügbaren Addons automatisch."""
        for name in self.scan_addon_dir():
            ok = self.load_addon(name, controller)
            print(f"Addon '{name}': {'geladen' if ok else 'FEHLER'}")

    def unload_addon(self, name: str):
        if name in self._addons:
            try:
                self._addons[name].on_unload()
            except Exception as e:
                print(f"Addon '{name}' on_unload() Fehler: {e}")
            self._unregister_hooks(self._addons[name])
            del self._addons[name]
            self._addon_paths.pop(name, None)

    # ------------------------------------------------------------------ #
    #  Hooks                                                              #
    # ------------------------------------------------------------------ #

    def _register_hooks(self, addon: AddonBase):
        hook_map = {
            "mail_read":     addon.on_mail_read,
            "mail_deleted":  addon.on_mail_deleted,
            "mail_moved":    addon.on_mail_moved,
            "mail_sent":     addon.on_mail_sent,
            "mail_received": addon.on_mail_received,
        }
        for event, handler in hook_map.items():
            self._hooks.setdefault(event, []).append(handler)

    def _unregister_hooks(self, addon: AddonBase):
        for event in list(self._hooks.keys()):
            self._hooks[event] = [
                h for h in self._hooks[event]
                if not (hasattr(h, "__self__") and h.__self__ is addon)
            ]

    def fire(self, event: str, data: dict = None):
        for handler in self._hooks.get(event, []):
            try:
                handler(data or {})
            except Exception as e:
                print(f"Addon Event '{event}' Fehler: {e}")

    # ------------------------------------------------------------------ #
    #  Abfragen                                                           #
    # ------------------------------------------------------------------ #

    def get_loaded_addons(self) -> Dict[str, AddonBase]:
        return dict(self._addons)

    def get_all_menu_items(self) -> list:
        items = []
        for addon in self._addons.values():
            try:
                items.extend(addon.get_menu_items())
            except Exception as e:
                print(f"Addon '{addon.NAME}' get_menu_items Fehler: {e}")
        return items

    def get_folder_context_items(self, item_type: str, item_data: dict) -> list:
        items = []
        for addon in self._addons.values():
            try:
                entries = addon.get_folder_context_items(item_type, item_data)
                if entries:
                    items.extend(entries)
            except Exception as e:
                print(f"Addon '{addon.NAME}' get_folder_context_items Fehler: {e}")
        return items
