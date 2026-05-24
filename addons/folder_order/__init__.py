"""
Addon: FolderOrder
Erweitert das Kontextmenü der Ordnerbaumstruktur um:
  • "Position nach oben"   – verschiebt Element eine Stufe höher
  • "Position nach unten"  – verschiebt Element eine Stufe tiefer

Unterscheidet korrekt zwischen Postfächern (mailboxes-Tabelle)
und Ordnern (folders-Tabelle).

Die Sortierung wird über eine 'sort_order'-Spalte in der DB gespeichert,
die beim ersten Addon-Load automatisch angelegt wird.
"""

import wx
from core.addon_manager import AddonBase


class Addon(AddonBase):

    NAME        = "FolderOrder"
    VERSION     = "1.1.0"
    DESCRIPTION = "Ordner und Postfächer per Kontextmenü sortieren"

    def on_load(self):
        self._ensure_sort_columns()

    # ------------------------------------------------------------------ #
    #  Kontextmenü                                                        #
    # ------------------------------------------------------------------ #

    def get_folder_context_items(self, item_type: str, item_data: dict) -> list:
        if item_type not in ("folder", "mailbox") or not item_data:
            return []
        return [
            {"label": "Nach oben verschieben",  "handler": self._move_up,   "enabled": True},
            {"label": "Nach unten verschieben", "handler": self._move_down, "enabled": True},
        ]

    # ------------------------------------------------------------------ #
    #  Move-Logik                                                         #
    # ------------------------------------------------------------------ #

    def _move_up(self, tree_item, item_data: dict):
        self._move(item_data, direction=-1)

    def _move_down(self, tree_item, item_data: dict):
        self._move(item_data, direction=+1)

    def _move(self, item_data: dict, direction: int):
        """
        Tauscht sort_order mit dem Nachbar-Element.

        Postfach  → Tabelle mailboxes, Geschwister = alle Postfächer
        Ordner    → Tabelle folders,   Geschwister = Ordner mit gleichem
                    mailbox_id UND parent_id
        """
        self._ensure_sort_columns()   # Spalte sicher vorhanden

        conn    = self.controller.db._get_mailstore_conn()
        item_id = item_data.get("id")
        if not item_id:
            return

        # ---- Postfach ------------------------------------------------
        if "account_id" in item_data:
            # Postfach-Datensatz: hat account_id, kein mailbox_id
            siblings = conn.execute(
                "SELECT id, sort_order FROM mailboxes ORDER BY sort_order, id"
            ).fetchall()
            table = "mailboxes"

        # ---- Ordner --------------------------------------------------
        elif "mailbox_id" in item_data:
            mailbox_id = item_data["mailbox_id"]
            parent_id  = item_data.get("parent_id")   # None = Wurzel-Ordner

            if parent_id is None:
                siblings = conn.execute(
                    "SELECT id, sort_order FROM folders "
                    "WHERE mailbox_id = ? AND parent_id IS NULL "
                    "ORDER BY sort_order, id",
                    (mailbox_id,)
                ).fetchall()
            else:
                siblings = conn.execute(
                    "SELECT id, sort_order FROM folders "
                    "WHERE mailbox_id = ? AND parent_id = ? "
                    "ORDER BY sort_order, id",
                    (mailbox_id, parent_id)
                ).fetchall()
            table = "folders"

        else:
            return  # Unbekannter Typ

        # ---- Position im Geschwister-Array finden --------------------
        ids = [row[0] for row in siblings]
        if item_id not in ids:
            wx.MessageBox(
                "Element nicht in der Geschwisterliste gefunden.\n"
                "Bitte die Anwendung neu starten.",
                "Fehler", wx.OK | wx.ICON_ERROR
            )
            return

        pos      = ids.index(item_id)
        swap_pos = pos + direction

        if swap_pos < 0 or swap_pos >= len(ids):
            msg = "ganz oben" if direction == -1 else "ganz unten"
            wx.MessageBox(
                f"Das Element befindet sich bereits {msg}.",
                "Position ändern", wx.OK | wx.ICON_INFORMATION
            )
            return

        # ---- sort_order-Werte sicherstellen (keine Duplikate) --------
        # Immer neu sequenziell vergeben → robust gegen NULL-Werte
        for i, (sid, _) in enumerate(siblings):
            conn.execute(
                f"UPDATE {table} SET sort_order = ? WHERE id = ?",
                (i * 10, sid)
            )

        # Jetzt tauschen: pos*10 ↔ swap_pos*10
        order_a = pos      * 10
        order_b = swap_pos * 10

        conn.execute(
            f"UPDATE {table} SET sort_order = ? WHERE id = ?",
            (order_b, ids[pos])
        )
        conn.execute(
            f"UPDATE {table} SET sort_order = ? WHERE id = ?",
            (order_a, ids[swap_pos])
        )
        conn.commit()

        # ---- Baum neu laden ------------------------------------------
        panel = self._find_folder_panel()
        if panel:
            panel.reload()

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    def _ensure_sort_columns(self):
        """Legt sort_order-Spalte an falls nicht vorhanden und befüllt sie."""
        conn = self.controller.db._get_mailstore_conn()
        for table in ("mailboxes", "folders"):
            cols = [r[1] for r in conn.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()]
            if "sort_order" not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN sort_order INTEGER DEFAULT 0"
                )
                rows = conn.execute(
                    f"SELECT id FROM {table} ORDER BY id"
                ).fetchall()
                for i, (rid,) in enumerate(rows):
                    conn.execute(
                        f"UPDATE {table} SET sort_order = ? WHERE id = ?",
                        (i * 10, rid)
                    )
        conn.commit()

    def _find_folder_panel(self):
        app = wx.GetApp()
        if not app:
            return None
        frame = app.GetTopWindow()
        return getattr(frame, "folder_panel", None)
