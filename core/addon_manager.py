"""
AddonManager – Plugin/Addon-System

Addon-Verzeichnisse:
  1. <app_dir>/addons/    – mitgelieferte Addons
  2. ~/.mailclient/addons/ – benutzerdefinierte Addons

Addons können eigene Sprachdateien mitbringen:
  addons/<name>/locale/<lang>/messages.json
"""

from __future__ import annotations
import os, sys, importlib.util
from typing import Dict, List, Callable


class AddonBase:
    NAME: str        = "UnnamedAddon"
    VERSION: str     = "0.0.1"
    DESCRIPTION: str = ""

    def __init__(self, controller):
        self.controller = controller

    def on_load(self):   pass
    def on_unload(self): pass
    def on_mail_read(self,     data: dict): pass
    def on_mail_deleted(self,  data: dict): pass
    def on_mail_moved(self,    data: dict): pass
    def on_mail_sent(self,     data: dict): pass
    def on_mail_received(self, data: dict): pass
    def get_menu_items(self) -> list:                                        return []
    def get_folder_context_items(self, t: str, d: dict) -> list:            return []
    def get_toolbar_items(self) -> list:                                     return []
    def get_preview_panel(self):                                             return None
    def on_pgp_decrypt(self, d: dict) -> dict:                              return d
    def on_pgp_encrypt(self, d: dict) -> dict:                              return d

    def get_settings_panel(self, parent) -> "wx.Panel | None":
        """
        Optionaler Einstellungs-Panel für dieses Addon.
        Gibt einen wx.Panel zurück der im Addon-Einstellungsdialog angezeigt wird,
        oder None wenn das Addon keine eigenen Einstellungen hat.
        Der Panel muss eine Methode save() implementieren die die Einstellungen speichert.
        """
        return None


class AddonManager:

    def __init__(self, app_dir: str = None, user_dir: str = None):
        if app_dir is None:
            app_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "addons")
        if user_dir is None:
            user_dir = os.path.join(os.path.expanduser("~"), ".mailclient", "addons")

        self.app_dir   = app_dir
        self.user_dir  = user_dir
        self.addon_dir = user_dir  # Install-Ziel

        os.makedirs(app_dir,  exist_ok=True)
        os.makedirs(user_dir, exist_ok=True)

        self._addons:      Dict[str, AddonBase] = {}
        self._hooks:       Dict[str, List[Callable]] = {}
        self._addon_paths: Dict[str, str] = {}

    def scan_addon_dir(self) -> List[str]:
        found: Dict[str, str] = {}
        for directory in (self.app_dir, self.user_dir):
            if not os.path.isdir(directory):
                continue
            for entry in sorted(os.scandir(directory), key=lambda e: e.name):
                if entry.is_dir() and os.path.exists(os.path.join(entry.path, "__init__.py")):
                    found[entry.name] = directory
        return list(found.keys())

    def _find_addon_path(self, name: str) -> str | None:
        for directory in (self.user_dir, self.app_dir):
            path = os.path.join(directory, name, "__init__.py")
            if os.path.exists(path):
                return path
        return None

    def _find_addon_dir(self, name: str) -> str | None:
        for directory in (self.user_dir, self.app_dir):
            d = os.path.join(directory, name)
            if os.path.isdir(d):
                return d
        return None

    def load_addon(self, name: str, controller, lang: str = "de") -> bool:
        addon_path = self._find_addon_path(name)
        if not addon_path:
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
            return False

        if name in self._addons:
            self.unload_addon(name)

        # FIX: Sprachdateien ZUERST laden, dann on_load() aufrufen –
        # sonst gibt tr() in on_load() noch die unübersetzten Keys zurück.
        addon_dir = self._find_addon_dir(name)
        if addon_dir:
            from core.i18n import load_addon_translations
            load_addon_translations(addon_dir, lang)

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

    def load_all(self, controller, lang: str = "de"):
        for name in self.scan_addon_dir():
            ok = self.load_addon(name, controller, lang=lang)
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

    def _register_hooks(self, addon: AddonBase):
        for event, handler in {
            "mail_read":     addon.on_mail_read,
            "mail_deleted":  addon.on_mail_deleted,
            "mail_moved":    addon.on_mail_moved,
            "mail_sent":     addon.on_mail_sent,
            "mail_received": addon.on_mail_received,
        }.items():
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

    def get_loaded_addons(self) -> Dict[str, AddonBase]:
        return dict(self._addons)

    def get_all_menu_items(self) -> list:
        items = []
        for addon in self._addons.values():
            try: items.extend(addon.get_menu_items())
            except Exception as e: print(f"Addon '{addon.NAME}' menu Fehler: {e}")
        return items

    def get_folder_context_items(self, item_type: str, item_data: dict) -> list:
        items = []
        for addon in self._addons.values():
            try:
                entries = addon.get_folder_context_items(item_type, item_data)
                if entries: items.extend(entries)
            except Exception as e: print(f"Addon '{addon.NAME}' context Fehler: {e}")
        return items
