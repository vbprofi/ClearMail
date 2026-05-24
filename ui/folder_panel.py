"""
FolderPanel – Linke Seite: Baumstruktur der Postfächer und Ordner.

Kontextmenü unterscheidet zwischen Postfach-Knoten und Ordner-Knoten.
Addons können das Kontextmenü über get_folder_context_items() erweitern.
"""

import wx


# Ordner-Icon-Index
ICON_MAILBOX  = 0
ICON_INBOX    = 1
ICON_SENT     = 2
ICON_DRAFTS   = 3
ICON_TRASH    = 4
ICON_SPAM     = 5
ICON_ARCHIVE  = 6
ICON_FOLDER   = 7

FOLDER_TYPE_ICONS = {
    "inbox":   ICON_INBOX,
    "sent":    ICON_SENT,
    "drafts":  ICON_DRAFTS,
    "trash":   ICON_TRASH,
    "spam":    ICON_SPAM,
    "archive": ICON_ARCHIVE,
    "custom":  ICON_FOLDER,
}


class FolderPanel(wx.Panel):
    """Panel mit Postfach-/Ordner-Baumstruktur und vollständigem Kontextmenü."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.on_folder_selected = None   # callback(folder_id, folder_name)

        self._folder_map  = {}   # TreeItemId -> folder dict
        self._mailbox_map = {}   # TreeItemId -> mailbox dict

        self._build_ui()
        self._build_image_list()
        self._bind_events()
        self.reload()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(self, label="Ordner")
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 4)

        self.tree = wx.TreeCtrl(
            self,
            style=(
                wx.TR_HAS_BUTTONS |
                wx.TR_LINES_AT_ROOT |
                wx.TR_HIDE_ROOT |
                wx.TR_SINGLE |
                wx.BORDER_SUNKEN
            )
        )
        self.tree.SetName(
            "Postfächer und Ordner, Baumansicht. "
            "Pfeiltasten navigieren, Enter öffnet/schließt, "
            "Applikationstaste oder Shift+F10 für Kontextmenü, "
            "F6 wechselt den Bereich."
        )
        sizer.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        self.SetSizer(sizer)

    def _build_image_list(self):
        il = wx.ImageList(16, 16, True)
        art = wx.ArtProvider
        il.Add(art.GetBitmap(wx.ART_FOLDER,      wx.ART_OTHER, (16, 16)))  # 0 mailbox
        il.Add(art.GetBitmap(wx.ART_GO_DOWN,     wx.ART_OTHER, (16, 16)))  # 1 inbox
        il.Add(art.GetBitmap(wx.ART_GO_UP,       wx.ART_OTHER, (16, 16)))  # 2 sent
        il.Add(art.GetBitmap(wx.ART_NEW,         wx.ART_OTHER, (16, 16)))  # 3 drafts
        il.Add(art.GetBitmap(wx.ART_DELETE,      wx.ART_OTHER, (16, 16)))  # 4 trash
        il.Add(art.GetBitmap(wx.ART_WARNING,     wx.ART_OTHER, (16, 16)))  # 5 spam
        il.Add(art.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_OTHER, (16, 16)))  # 6 archive
        il.Add(art.GetBitmap(wx.ART_FOLDER,      wx.ART_OTHER, (16, 16)))  # 7 custom
        self.tree.SetImageList(il)
        self._image_list = il

    def _bind_events(self):
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED,    self._on_selection_changed)
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_item_activated)
        # Kontextmenü: rechte Maustaste UND Applikationstaste (Shift+F10)
        self.tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self._on_item_right_click)
        self.tree.Bind(wx.EVT_CONTEXT_MENU,          self._on_context_menu_key)

    # ------------------------------------------------------------------ #
    #  Daten laden                                                        #
    # ------------------------------------------------------------------ #

    def reload(self):
        self.tree.DeleteAllItems()
        self._folder_map.clear()
        self._mailbox_map.clear()

        root      = self.tree.AddRoot("Root")
        mailboxes = self.controller.get_mailboxes()

        for mb in mailboxes:
            mb_item = self.tree.AppendItem(root, mb["name"], ICON_MAILBOX, ICON_MAILBOX)
            self.tree.SetItemBold(mb_item, True)
            self.tree.SetItemData(mb_item, ("mailbox", mb["id"]))
            self._mailbox_map[mb_item] = dict(mb)

            folders = self.controller.get_folders(mb["id"])
            self._add_folder_items(mb_item, folders, parent_id=None)
            self.tree.Expand(mb_item)

    def _add_folder_items(self, parent_item, folders: list, parent_id):
        for f in folders:
            if f["parent_id"] != parent_id:
                continue
            unread   = f["unread"] or 0
            icon_idx = FOLDER_TYPE_ICONS.get(f["folder_type"], ICON_FOLDER)
            label    = f["name"] if not unread else f"{f['name']} ({unread})"

            item = self.tree.AppendItem(parent_item, label, icon_idx, icon_idx)
            self.tree.SetItemData(item, ("folder", f["id"]))
            self.tree.SetItemBold(item, unread > 0)
            self._folder_map[item] = dict(f)

            self._add_folder_items(item, folders, parent_id=f["id"])

    # ------------------------------------------------------------------ #
    #  Tree-Events                                                        #
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self, event):
        try:
            item = event.GetItem()
            if not item.IsOk():
                return
            data = self.tree.GetItemData(item)
            if data and data[0] == "folder":
                folder_id   = data[1]
                folder_name = self._folder_map.get(item, {}).get("name", "")
                if self.on_folder_selected:
                    self.on_folder_selected(folder_id, folder_name)
        except RuntimeError:
            pass

    def _on_item_activated(self, event):
        try:
            item = event.GetItem()
            if not item.IsOk():
                return
            if self.tree.ItemHasChildren(item):
                if self.tree.IsExpanded(item):
                    self.tree.Collapse(item)
                else:
                    self.tree.Expand(item)
        except RuntimeError:
            pass

    def _on_item_right_click(self, event):
        """Rechte Maustaste: Item selektieren, dann Menü zeigen."""
        item = event.GetItem()
        if item.IsOk():
            self.tree.SelectItem(item)
        self._show_context_menu(item)

    def _on_context_menu_key(self, event):
        """Applikationstaste / Shift+F10: Menü für aktuell selektiertes Item."""
        item = self.tree.GetSelection()
        self._show_context_menu(item if item.IsOk() else None)

    # ------------------------------------------------------------------ #
    #  Kontextmenü                                                        #
    # ------------------------------------------------------------------ #

    def _show_context_menu(self, item):
        """Zeigt das Kontextmenü je nach Item-Typ (Postfach / Ordner)."""
        menu = wx.Menu()

        if item and item.IsOk():
            data = self.tree.GetItemData(item)
            node_type = data[0] if data else None
        else:
            node_type = None

        if node_type == "mailbox":
            self._build_mailbox_menu(menu, item)
        elif node_type == "folder":
            self._build_folder_menu(menu, item)
        else:
            menu.Append(wx.ID_ANY, "(Kein Element ausgewählt)").Enable(False)

        # ---- Addon-Erweiterungen ----
        addon_items = self.controller.addon_mgr.get_folder_context_items(
            item_type=node_type,
            item_data=self._get_item_data_dict(item),
        )
        if addon_items:
            menu.AppendSeparator()
            for entry in addon_items:
                mi = menu.Append(wx.ID_ANY, entry["label"])
                if entry.get("enabled", True):
                    self.Bind(
                        wx.EVT_MENU,
                        lambda e, fn=entry["handler"], it=item: fn(it, self._get_item_data_dict(it)),
                        mi
                    )
                else:
                    mi.Enable(False)

        self.tree.PopupMenu(menu)
        menu.Destroy()

    def _build_mailbox_menu(self, menu: wx.Menu, item):
        """Menüeinträge für ein Postfach."""
        mi_new_folder = menu.Append(wx.ID_ANY, "Neuen Ordner erstellen...")
        mi_sep        = menu.AppendSeparator()
        mi_rename     = menu.Append(wx.ID_ANY, "Postfach umbenennen...")
        mi_remove     = menu.Append(wx.ID_ANY, "Postfach entfernen")

        self.Bind(wx.EVT_MENU, lambda e: self._on_new_folder(item),    mi_new_folder)
        self.Bind(wx.EVT_MENU, lambda e: self._on_rename_mailbox(item), mi_rename)
        self.Bind(wx.EVT_MENU, lambda e: self._on_remove_mailbox(item), mi_remove)

    def _build_folder_menu(self, menu: wx.Menu, item):
        """Menüeinträge für einen Ordner."""
        f = self._folder_map.get(item, {})
        is_system = f.get("folder_type", "custom") != "custom"

        mi_new_sub = menu.Append(wx.ID_ANY, "Neuen Unterordner erstellen...")
        mi_rename  = menu.Append(wx.ID_ANY, "Ordner umbenennen...")
        mi_delete  = menu.Append(wx.ID_ANY, "Ordner löschen")

        if is_system:
            mi_rename.Enable(False)
            mi_delete.Enable(False)

        self.Bind(wx.EVT_MENU, lambda e: self._on_new_subfolder(item), mi_new_sub)
        self.Bind(wx.EVT_MENU, lambda e: self._on_rename_folder(item), mi_rename)
        self.Bind(wx.EVT_MENU, lambda e: self._on_delete_folder(item), mi_delete)

    # ------------------------------------------------------------------ #
    #  Aktionen                                                           #
    # ------------------------------------------------------------------ #

    def _on_new_folder(self, parent_item):
        """Neuen Ordner unter einem Postfach anlegen."""
        mb = self._mailbox_map.get(parent_item)
        if not mb:
            return
        name = wx.GetTextFromUser(
            "Name des neuen Ordners:", "Neuer Ordner", parent=self
        ).strip()
        if not name:
            return
        conn = self.controller.db._get_mailstore_conn()
        conn.execute(
            "INSERT INTO folders (mailbox_id, parent_id, name, folder_type) VALUES (?, NULL, ?, 'custom')",
            (mb["id"], name)
        )
        conn.commit()
        self.reload()

    def _on_new_subfolder(self, parent_item):
        """Neuen Unterordner unter einem Ordner anlegen."""
        f = self._folder_map.get(parent_item)
        if not f:
            return
        name = wx.GetTextFromUser(
            "Name des Unterordners:", "Neuer Unterordner", parent=self
        ).strip()
        if not name:
            return
        conn = self.controller.db._get_mailstore_conn()
        conn.execute(
            "INSERT INTO folders (mailbox_id, parent_id, name, folder_type) VALUES (?, ?, ?, 'custom')",
            (f["mailbox_id"], f["id"], name)
        )
        conn.commit()
        self.reload()

    def _on_rename_folder(self, item):
        f = self._folder_map.get(item)
        if not f:
            return
        new_name = wx.GetTextFromUser(
            "Neuer Name:", "Ordner umbenennen",
            default_value=f["name"], parent=self
        ).strip()
        if not new_name or new_name == f["name"]:
            return
        conn = self.controller.db._get_mailstore_conn()
        conn.execute("UPDATE folders SET name = ? WHERE id = ?", (new_name, f["id"]))
        conn.commit()
        self.tree.SetItemText(item, new_name)
        self._folder_map[item]["name"] = new_name

    def _on_delete_folder(self, item):
        f = self._folder_map.get(item)
        if not f:
            return
        if wx.MessageBox(
            f"Ordner '{f['name']}' und alle darin enthaltenen Mails wirklich löschen?\n"
            "Diese Aktion kann nicht rückgängig gemacht werden.",
            "Ordner löschen",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self
        ) != wx.YES:
            return
        conn = self.controller.db._get_mailstore_conn()
        # Mails löschen, dann Ordner
        conn.execute("DELETE FROM mails WHERE folder_id = ?", (f["id"],))
        conn.execute("DELETE FROM folders WHERE id = ?",      (f["id"],))
        conn.commit()
        del self._folder_map[item]
        self.tree.Delete(item)

    def _on_rename_mailbox(self, item):
        mb = self._mailbox_map.get(item)
        if not mb:
            return
        new_name = wx.GetTextFromUser(
            "Neuer Anzeigename:", "Postfach umbenennen",
            default_value=mb["name"], parent=self
        ).strip()
        if not new_name or new_name == mb["name"]:
            return
        conn = self.controller.db._get_mailstore_conn()
        conn.execute("UPDATE mailboxes SET name = ? WHERE id = ?", (new_name, mb["id"]))
        conn.commit()
        self.tree.SetItemText(item, new_name)
        self._mailbox_map[item]["name"] = new_name

    def _on_remove_mailbox(self, item):
        mb = self._mailbox_map.get(item)
        if not mb:
            return
        if wx.MessageBox(
            f"Postfach '{mb['name']}' wirklich entfernen?\n"
            "Alle Ordner und Mails dieses Postfachs werden gelöscht.",
            "Postfach entfernen",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self
        ) != wx.YES:
            return
        conn = self.controller.db._get_mailstore_conn()
        # Mails → Ordner → Postfach löschen
        conn.execute(
            "DELETE FROM mails WHERE folder_id IN "
            "(SELECT id FROM folders WHERE mailbox_id = ?)", (mb["id"],)
        )
        conn.execute("DELETE FROM folders WHERE mailbox_id = ?",  (mb["id"],))
        conn.execute("DELETE FROM mailboxes WHERE id = ?",        (mb["id"],))
        conn.commit()
        self.reload()

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    def _get_item_data_dict(self, item) -> dict:
        """Gibt das Daten-Dictionary für ein Tree-Item zurück."""
        if item is None or not item.IsOk():
            return {}
        data = self.tree.GetItemData(item)
        if not data:
            return {}
        if data[0] == "folder":
            return self._folder_map.get(item, {})
        if data[0] == "mailbox":
            return self._mailbox_map.get(item, {})
        return {}

    def refresh_folder_unread(self, folder_id: int):
        """Aktualisiert den Ungelesen-Zähler eines Ordners im Baum."""
        for item, f in self._folder_map.items():
            if f["id"] != folder_id:
                continue
            folders = self.controller.get_folders(f["mailbox_id"])
            for updated in folders:
                if updated["id"] == folder_id:
                    unread = updated["unread"] or 0
                    label  = updated["name"] if not unread else f"{updated['name']} ({unread})"
                    self.tree.SetItemText(item, label)
                    self.tree.SetItemBold(item, unread > 0)
                    self._folder_map[item] = dict(updated)
                    break
            break

    def get_selected_folder_name(self) -> str:
        item = self.tree.GetSelection()
        if item.IsOk():
            return self.tree.GetItemText(item)
        return ""

    def get_selected_item_type(self):
        """Gibt ('folder'|'mailbox', id) des selektierten Items zurück."""
        item = self.tree.GetSelection()
        if item.IsOk():
            return self.tree.GetItemData(item)
        return None
