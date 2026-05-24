"""
AddonManager – Plugin/Addon-System
Stellt Schnittstellen für Addons bereit und verwaltet deren Lebenszyklus.
"""

from __future__ import annotations
import os
import sys
import importlib
import importlib.util
from typing import Dict, List, Callable, Any


class AddonBase:
    """
    Basisklasse für alle Addons.
    Addons erben von dieser Klasse und überschreiben die Hooks.
    """

    NAME: str = "UnnamedAddon"
    VERSION: str = "0.0.1"
    DESCRIPTION: str = ""

    def __init__(self, controller):
        self.controller = controller

    # Lifecycle
    def on_load(self):
        """Wird beim Laden des Addons aufgerufen."""
        pass

    def on_unload(self):
        """Wird beim Entladen des Addons aufgerufen."""
        pass

    # Mail-Hooks
    def on_mail_read(self, data: dict):
        pass

    def on_mail_deleted(self, data: dict):
        pass

    def on_mail_moved(self, data: dict):
        pass

    def on_mail_sent(self, data: dict):
        pass

    def on_mail_received(self, data: dict):
        pass

    # UI-Hooks
    def get_menu_items(self) -> list:
        """
        Gibt eine Liste von Menüeinträgen zurück.
        Format: [{"label": "Mein Addon", "handler": callable}, ...]
        """
        return []

    def get_toolbar_items(self) -> list:
        """
        Gibt eine Liste von Symbolleistenschaltflächen zurück.
        """
        return []

    def get_preview_panel(self):
        """
        Kann ein zusätzliches wx.Panel für die Mail-Vorschau zurückgeben.
        """
        return None

    # PGP-Hook (Platzhalter)
    def on_pgp_decrypt(self, mail_data: dict) -> dict:
        return mail_data

    def on_pgp_encrypt(self, mail_data: dict) -> dict:
        return mail_data


class AddonManager:
    """Verwaltet alle geladenen Addons."""

    def __init__(self, addon_dir: str = None):
        if addon_dir is None:
            addon_dir = os.path.join(os.path.expanduser("~"), ".mailclient", "addons")
        self.addon_dir = addon_dir
        os.makedirs(addon_dir, exist_ok=True)

        self._addons: Dict[str, AddonBase] = {}
        self._hooks: Dict[str, List[Callable]] = {}

    def load_addon(self, name: str, controller) -> bool:
        """Lädt ein Addon aus dem Addon-Verzeichnis."""
        addon_path = os.path.join(self.addon_dir, name, "__init__.py")
        if not os.path.exists(addon_path):
            return False

        spec = importlib.util.spec_from_file_location(f"addon_{name}", addon_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Addon '{name}' konnte nicht geladen werden: {e}")
            return False

        cls = getattr(module, "Addon", None)
        if cls is None or not issubclass(cls, AddonBase):
            return False

        instance = cls(controller)
        instance.on_load()
        self._addons[name] = instance
        self._register_hooks(instance)
        return True

    def unload_addon(self, name: str):
        if name in self._addons:
            self._addons[name].on_unload()
            self._unregister_hooks(self._addons[name])
            del self._addons[name]

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
        """Löst ein Event aus und ruft alle registrierten Handler auf."""
        for handler in self._hooks.get(event, []):
            try:
                handler(data or {})
            except Exception as e:
                print(f"Addon-Fehler bei Event '{event}': {e}")

    def get_loaded_addons(self) -> Dict[str, AddonBase]:
        return dict(self._addons)

    def get_all_menu_items(self) -> list:
        items = []
        for addon in self._addons.values():
            items.extend(addon.get_menu_items())
        return items

    def scan_addon_dir(self) -> List[str]:
        """Gibt alle verfügbaren Addon-Namen zurück."""
        result = []
        if os.path.isdir(self.addon_dir):
            for entry in os.scandir(self.addon_dir):
                if entry.is_dir() and os.path.exists(os.path.join(entry.path, "__init__.py")):
                    result.append(entry.name)
        return result
