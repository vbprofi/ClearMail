"""
Addon: FolderOrder
Erweitert das Kontextmenü der Ordnerbaumstruktur um:
  • "Nach oben verschieben"  – verschiebt Element eine Stufe höher
  • "Nach unten verschieben" – verschiebt Element eine Stufe tiefer

Sprachdateien: locale/de/messages.json, locale/en/messages.json
"""

import wx
from core.addon_manager import AddonBase
from core.i18n import tr


class Addon(AddonBase):

    NAME    = "FolderOrder"
    VERSION = "1.2.0"

    @property
    def DESCRIPTION(self):
        return tr("fo_description")

    def on_load(self):
        self._ensure_sort_columns()

    # ------------------------------------------------------------------ #
    #  Kontextmenü                                                        #
    # ------------------------------------------------------------------ #

    def get_folder_context_items(self, item_type: str, item_data: dict) -> list:
        if item_type not in ("folder", "mailbox") or not item_data:
            return []
        return [
            {"label": tr("fo_move_up"),   "handler": self._move_up,   "enabled": True},
            {"label": tr("fo_move_down"), "handler": self._move_down, "enabled": True},
        ]

    # ------------------------------------------------------------------ #
    #  Move-Logik                                                         #
    # ------------------------------------------------------------------ #

    def _move_up(self, tree_item, item_data: dict):
        self._move(item_data, direction=-1)

    def _move_down(self, tree_item, item_data: dict):
        self._move(item_data, direction=+1)

    def _move(self, item_data: dict, direction: int):
        self._ensure_sort_columns()

        conn    = self.controller.db._get_mailstore_conn()
        item_id = item_data.get("id")
        if not item_id:
            return

        # Postfach (hat account_id, kein mailbox_id)
        if "account_id" in item_data:
            siblings = conn.execute(
                "SELECT id, sort_order FROM mailboxes ORDER BY sort_order, id"
            ).fetchall()
            table = "mailboxes"

        # Ordner (hat mailbox_id)
        elif "mailbox_id" in item_data:
            mailbox_id = item_data["mailbox_id"]
            parent_id  = item_data.get("parent_id")

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
            return

        ids = [row[0] for row in siblings]
        if item_id not in ids:
            wx.MessageBox(
                tr("fo_not_found"),
                tr("fo_error_title"), wx.OK | wx.ICON_ERROR
            )
            return

        pos      = ids.index(item_id)
        swap_pos = pos + direction

        if swap_pos < 0 or swap_pos >= len(ids):
            msg = tr("fo_already_top") if direction == -1 else tr("fo_already_bottom")
            wx.MessageBox(msg, tr("fo_title"), wx.OK | wx.ICON_INFORMATION)
            return

        # Sequenzielle sort_order-Werte vergeben (verhindert Duplikate/NULL)
        for i, (sid, _) in enumerate(siblings):
            conn.execute(
                f"UPDATE {table} SET sort_order = ? WHERE id = ?",
                (i * 10, sid)
            )

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

        panel = self._find_folder_panel()
        if panel:
            panel.reload()

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    def _ensure_sort_columns(self):
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
