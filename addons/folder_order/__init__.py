"""
Addon: FolderOrder  v1.1
Manuelle Sortierung von Postfächern und Ordnern (inkl. Unterordner).

Funktionen:
  • "Nach oben"   / "Nach unten"   im Kontextmenü (alle Ebenen)
  • "Ganz nach oben" / "Ganz nach unten"
  • Tastaturkürzel Alt+↑ / Alt+↓ wenn der Ordnerbaum fokussiert ist
  • Die benutzerdefinierte Reihenfolge wird in sort_order-Spalte gespeichert
    und von folder_panel._add_folder_items() respektiert sobald vorhanden.

Korrekturen v1.1:
  - Unterordner werden korrekt verschoben (parent_id-Filter)
  - _ensure_sort_columns() verwendet _get_structure_conn() (thread-sicher)
  - reload() nach Move beibehält selektierten Ordner (neues folder_panel)
  - Alt+Pfeil-Tastaturkürzel direkt am TreeCtrl gebunden
  - "Ganz nach oben" / "Ganz nach unten" als neue Menüeinträge
"""

import wx
from core.addon_manager import AddonBase
from core.i18n import tr


class Addon(AddonBase):

    NAME    = "FolderOrder"
    VERSION = "1.1.0"

    @property
    def DESCRIPTION(self):
        return tr("fo_description")

    def on_load(self):
        self._ensure_sort_columns()
        # Alt+Pfeil-Tastenkürzel am TreeCtrl registrieren
        wx.CallAfter(self._bind_keyboard_shortcuts)

    # ------------------------------------------------------------------ #
    #  Kontextmenü (wird von FolderPanel eingebunden)                    #
    # ------------------------------------------------------------------ #

    def get_folder_context_items(self, item_type: str, item_data: dict) -> list:
        if item_type not in ("folder", "mailbox") or not item_data:
            return []
        return [
            {"label": tr("fo_move_top"),    "handler": self._move_top,    "enabled": True},
            {"label": tr("fo_move_up"),     "handler": self._move_up,     "enabled": True},
            {"label": tr("fo_move_down"),   "handler": self._move_down,   "enabled": True},
            {"label": tr("fo_move_bottom"), "handler": self._move_bottom, "enabled": True},
        ]

    # ------------------------------------------------------------------ #
    #  Handler                                                            #
    # ------------------------------------------------------------------ #

    def _move_up(self, tree_item, item_data: dict):
        self._move(item_data, direction=-1)

    def _move_down(self, tree_item, item_data: dict):
        self._move(item_data, direction=+1)

    def _move_top(self, tree_item, item_data: dict):
        self._move_to_edge(item_data, to_top=True)

    def _move_bottom(self, tree_item, item_data: dict):
        self._move_to_edge(item_data, to_top=False)

    # ------------------------------------------------------------------ #
    #  Tastaturkürzel: Alt+↑ / Alt+↓ am TreeCtrl                        #
    # ------------------------------------------------------------------ #

    def _bind_keyboard_shortcuts(self):
        panel = self._find_folder_panel()
        if not panel:
            return
        try:
            panel.tree.Bind(wx.EVT_KEY_DOWN, self._on_tree_key)
        except Exception:
            pass

    def _on_tree_key(self, event: wx.KeyEvent):
        key = event.GetKeyCode()
        alt = event.AltDown()
        if not alt or key not in (wx.WXK_UP, wx.WXK_DOWN):
            event.Skip()
            return
        panel = self._find_folder_panel()
        if not panel:
            event.Skip()
            return
        item = panel.tree.GetSelection()
        if not item or not item.IsOk():
            event.Skip()
            return
        data = panel.tree.GetItemData(item)
        if not data:
            event.Skip()
            return
        node_type = data[0]
        if node_type == "folder":
            item_data = panel._folder_map.get(item, {})
        elif node_type == "mailbox":
            item_data = panel._mailbox_map.get(item, {})
        else:
            event.Skip()
            return
        if key == wx.WXK_UP:
            self._move(item_data, direction=-1)
        else:
            self._move(item_data, direction=+1)

    # ------------------------------------------------------------------ #
    #  Move-Kern                                                          #
    # ------------------------------------------------------------------ #

    def _get_siblings(self, item_data: dict):
        """
        Gibt (conn, table, siblings_list) zurück.
        siblings_list: [(id, sort_order), ...] geordnet nach sort_order, id
        """
        self._ensure_sort_columns()
        conn    = self.controller.db._get_structure_conn()
        item_id = item_data.get("id")
        if not item_id:
            return None, None, None

        if "account_id" in item_data:
            # Postfach-Ebene
            siblings = conn.execute(
                "SELECT id, sort_order FROM mailboxes ORDER BY sort_order, id"
            ).fetchall()
            return conn, "mailboxes", siblings

        if "mailbox_id" in item_data:
            mailbox_id = item_data["mailbox_id"]
            parent_id  = item_data.get("parent_id")
            if parent_id is None:
                siblings = conn.execute(
                    "SELECT id, sort_order FROM folders "
                    "WHERE mailbox_id=? AND parent_id IS NULL "
                    "ORDER BY sort_order, id",
                    (mailbox_id,)
                ).fetchall()
            else:
                siblings = conn.execute(
                    "SELECT id, sort_order FROM folders "
                    "WHERE mailbox_id=? AND parent_id=? "
                    "ORDER BY sort_order, id",
                    (mailbox_id, parent_id)
                ).fetchall()
            return conn, "folders", siblings

        return None, None, None

    def _write_order(self, conn, table: str, ordered_ids: list):
        """Schreibt sort_order in Zehnerschritten für ordered_ids."""
        for i, oid in enumerate(ordered_ids):
            conn.execute(
                f"UPDATE {table} SET sort_order=? WHERE id=?",
                (i * 10, oid)
            )
        conn.commit()

    def _move(self, item_data: dict, direction: int):
        conn, table, siblings = self._get_siblings(item_data)
        if conn is None:
            return
        item_id = item_data.get("id")
        ids     = [row[0] for row in siblings]
        if item_id not in ids:
            wx.MessageBox(tr("fo_not_found"), tr("fo_error_title"), wx.OK | wx.ICON_ERROR)
            return
        pos      = ids.index(item_id)
        swap_pos = pos + direction
        if swap_pos < 0 or swap_pos >= len(ids):
            msg = tr("fo_already_top") if direction == -1 else tr("fo_already_bottom")
            wx.MessageBox(msg, tr("fo_title"), wx.OK | wx.ICON_INFORMATION)
            return
        ids[pos], ids[swap_pos] = ids[swap_pos], ids[pos]
        self._write_order(conn, table, ids)
        self._reload()

    def _move_to_edge(self, item_data: dict, to_top: bool):
        conn, table, siblings = self._get_siblings(item_data)
        if conn is None:
            return
        item_id = item_data.get("id")
        ids     = [row[0] for row in siblings]
        if item_id not in ids:
            wx.MessageBox(tr("fo_not_found"), tr("fo_error_title"), wx.OK | wx.ICON_ERROR)
            return
        ids.remove(item_id)
        if to_top:
            ids.insert(0, item_id)
        else:
            ids.append(item_id)
        self._write_order(conn, table, ids)
        self._reload()

    def _reload(self):
        panel = self._find_folder_panel()
        if panel:
            panel.reload()   # stellt selektierten Ordner automatisch wieder her

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    def _ensure_sort_columns(self):
        """Legt sort_order-Spalte an wenn noch nicht vorhanden."""
        conn = self.controller.db._get_structure_conn()
        for table in ("mailboxes", "folders"):
            cols = [r[1] for r in conn.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()]
            if "sort_order" not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN sort_order INTEGER DEFAULT 0"
                )
                # Initiale Reihenfolge = aktuelle DB-Reihenfolge
                rows = conn.execute(f"SELECT id FROM {table} ORDER BY id").fetchall()
                for i, (rid,) in enumerate(rows):
                    conn.execute(
                        f"UPDATE {table} SET sort_order=? WHERE id=?", (i * 10, rid)
                    )
        conn.commit()

    def _find_folder_panel(self):
        app = wx.GetApp()
        if not app:
            return None
        frame = app.GetTopWindow()
        return getattr(frame, "folder_panel", None)
