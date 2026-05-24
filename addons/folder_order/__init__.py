"""
Addon: FolderOrder
Erweitert das Kontextmenü der Ordnerbaumstruktur um:
  • "Position nach oben"   – verschiebt Ordner/Postfach eine Stufe höher
  • "Position nach unten"  – verschiebt Ordner/Postfach eine Stufe tiefer

Die Sortierung wird über eine 'sort_order'-Spalte in der DB gespeichert.
Da die Demo-DB diese Spalte nicht enthält, wird sie beim ersten Aufruf angelegt.

Installation:
  Dieses Verzeichnis nach ~/.mailclient/addons/folder_order/ kopieren.
"""

import wx
from core.addon_manager import AddonBase


class Addon(AddonBase):

    NAME        = "FolderOrder"
    VERSION     = "1.0.0"
    DESCRIPTION = "Ordner per Kontextmenü nach oben/unten verschieben"

    def on_load(self):
        self._ensure_sort_column()

    # ------------------------------------------------------------------ #
    #  Kontextmenü-Einträge                                               #
    # ------------------------------------------------------------------ #

    def get_folder_context_items(self, item_type: str, item_data: dict) -> list:
        """Gibt Einträge für Ordner UND Postfächer zurück."""
        if item_type not in ("folder", "mailbox"):
            return []
        if not item_data:
            return []

        return [
            {
                "label":   "Position nach oben",
                "handler": self._move_up,
                "enabled": True,
            },
            {
                "label":   "Position nach unten",
                "handler": self._move_down,
                "enabled": True,
            },
        ]

    # ------------------------------------------------------------------ #
    #  Handler                                                            #
    # ------------------------------------------------------------------ #

    def _move_up(self, tree_item, item_data: dict):
        """Verschiebt das Element eine Position nach oben (kleinere sort_order)."""
        self._move(tree_item, item_data, direction=-1)

    def _move_down(self, tree_item, item_data: dict):
        """Verschiebt das Element eine Position nach unten (größere sort_order)."""
        self._move(tree_item, item_data, direction=+1)

    def _move(self, tree_item, item_data: dict, direction: int):
        """
        Kernlogik: Tauscht sort_order mit dem Nachbar-Element.
        direction: -1 = nach oben, +1 = nach unten
        """
        db     = self.controller.db
        conn   = db._get_mailstore_conn()
        item_id = item_data.get("id")

        if not item_id:
            return

        # Ist es ein Ordner oder ein Postfach?
        if "mailbox_id" in item_data:
            table      = "folders"
            id_col     = "id"
            # Geschwister: gleicher parent_id und mailbox_id
            parent_id  = item_data.get("parent_id")
            mailbox_id = item_data.get("mailbox_id")
            if parent_id is None:
                siblings = conn.execute(
                    "SELECT id, sort_order FROM folders "
                    "WHERE mailbox_id = ? AND parent_id IS NULL ORDER BY sort_order, id",
                    (mailbox_id,)
                ).fetchall()
            else:
                siblings = conn.execute(
                    "SELECT id, sort_order FROM folders "
                    "WHERE mailbox_id = ? AND parent_id = ? ORDER BY sort_order, id",
                    (mailbox_id, parent_id)
                ).fetchall()
        else:
            # Postfach
            table    = "mailboxes"
            id_col   = "id"
            siblings = conn.execute(
                "SELECT id, sort_order FROM mailboxes ORDER BY sort_order, id"
            ).fetchall()

        # Aktuelle Position im Geschwister-Array ermitteln
        ids = [row[0] for row in siblings]
        if item_id not in ids:
            return
        pos = ids.index(item_id)
        swap_pos = pos + direction

        if swap_pos < 0 or swap_pos >= len(ids):
            direction_str = "oben" if direction == -1 else "unten"
            wx.MessageBox(
                f"Element befindet sich bereits ganz {direction_str}.",
                "Position ändern",
                wx.OK | wx.ICON_INFORMATION
            )
            return

        swap_id = ids[swap_pos]

        # sort_order-Werte tauschen
        order_a = siblings[pos][1]     # aktuelles Element
        order_b = siblings[swap_pos][1]  # Tausch-Element

        if order_a == order_b:
            # Gleiche Werte → neue sequenzielle Werte vergeben
            for i, (sid, _) in enumerate(siblings):
                conn.execute(
                    f"UPDATE {table} SET sort_order = ? WHERE {id_col} = ?",
                    (i * 10, sid)
                )
            # Neu berechnete Werte
            order_a = pos * 10
            order_b = swap_pos * 10

        conn.execute(
            f"UPDATE {table} SET sort_order = ? WHERE {id_col} = ?",
            (order_b, item_id)
        )
        conn.execute(
            f"UPDATE {table} SET sort_order = ? WHERE {id_col} = ?",
            (order_a, swap_id)
        )
        conn.commit()

        # Baum neu laden um neue Reihenfolge anzuzeigen
        # Wir suchen das FolderPanel im Widget-Baum
        folder_panel = self._find_folder_panel()
        if folder_panel:
            folder_panel.reload()

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    def _ensure_sort_column(self):
        """Fügt sort_order-Spalte hinzu falls noch nicht vorhanden."""
        db   = self.controller.db
        conn = db._get_mailstore_conn()
        for table in ("folders", "mailboxes"):
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "sort_order" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN sort_order INTEGER DEFAULT 0")
                # Initiale Werte setzen
                rows = conn.execute(f"SELECT id FROM {table} ORDER BY id").fetchall()
                for i, (rid,) in enumerate(rows):
                    conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (i * 10, rid))
        conn.commit()

    def _find_folder_panel(self):
        """Sucht das FolderPanel über die wx-App."""
        app = wx.GetApp()
        if not app:
            return None
        frame = app.GetTopWindow()
        if not frame:
            return None
        return getattr(frame, "folder_panel", None)
