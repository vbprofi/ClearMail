"""
FolderPanel – Linke Seite: Baumstruktur der Postfächer und Ordner.
Vollständig i18n-fähig. Papierkorb-Unterstützung.
"""

import wx
from core.i18n import tr


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

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.on_folder_selected = None

        self._folder_map  = {}
        self._mailbox_map = {}

        self._build_ui()
        self._build_image_list()
        self._bind_events()
        self.reload()

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(self, label=tr("folder_mailboxes"))
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 4)

        self.tree = wx.TreeCtrl(
            self,
            style=(wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT |
                   wx.TR_HIDE_ROOT | wx.TR_SINGLE | wx.BORDER_SUNKEN)
        )
        self.tree.SetName(tr("folder_mailboxes"))
        self.tree.SetToolTip(tr("folder_tree_tooltip"))
        sizer.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        self.SetSizer(sizer)

    def _build_image_list(self):
        il  = wx.ImageList(16, 16, True)
        art = wx.ArtProvider
        il.Add(art.GetBitmap(wx.ART_FOLDER,      wx.ART_OTHER, (16, 16)))
        il.Add(art.GetBitmap(wx.ART_GO_DOWN,     wx.ART_OTHER, (16, 16)))
        il.Add(art.GetBitmap(wx.ART_GO_UP,       wx.ART_OTHER, (16, 16)))
        il.Add(art.GetBitmap(wx.ART_NEW,         wx.ART_OTHER, (16, 16)))
        il.Add(art.GetBitmap(wx.ART_DELETE,      wx.ART_OTHER, (16, 16)))
        il.Add(art.GetBitmap(wx.ART_WARNING,     wx.ART_OTHER, (16, 16)))
        il.Add(art.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_OTHER, (16, 16)))
        il.Add(art.GetBitmap(wx.ART_FOLDER,      wx.ART_OTHER, (16, 16)))
        self.tree.SetImageList(il)
        self._image_list = il

    def _bind_events(self):
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED,     self._on_selection_changed)
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED,  self._on_item_activated)
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

    def _add_folder_items(self, parent_item, folders, parent_id):
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
                f           = self._folder_map.get(item, {})
                folder_id   = data[1]
                folder_name = f.get("name", "")
                mailbox_id  = f.get("mailbox_id")
                if self.on_folder_selected:
                    self.on_folder_selected(folder_id, folder_name, mailbox_id)
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
        item = event.GetItem()
        if item.IsOk():
            self.tree.SelectItem(item)
        self._show_context_menu(item)

    def _on_context_menu_key(self, event):
        item = self.tree.GetSelection()
        self._show_context_menu(item if item.IsOk() else None)

    # ------------------------------------------------------------------ #
    #  Kontextmenü                                                        #
    # ------------------------------------------------------------------ #

    def _show_context_menu(self, item):
        menu = wx.Menu()

        if item and item.IsOk():
            data      = self.tree.GetItemData(item)
            node_type = data[0] if data else None
        else:
            node_type = None

        if node_type == "mailbox":
            self._build_mailbox_menu(menu, item)
        elif node_type == "folder":
            self._build_folder_menu(menu, item)
        else:
            menu.Append(wx.ID_ANY, tr("hint_title")).Enable(False)

        # Addon-Erweiterungen
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

    def _build_mailbox_menu(self, menu, item):
        mi_new    = menu.Append(wx.ID_ANY, tr("ctx_folder_new"))
        mi_rename = menu.Append(wx.ID_ANY, tr("ctx_mailbox_rename"))
        mi_remove = menu.Append(wx.ID_ANY, tr("ctx_mailbox_remove"))
        self.Bind(wx.EVT_MENU, lambda e: self._on_new_folder(item),    mi_new)
        self.Bind(wx.EVT_MENU, lambda e: self._on_rename_mailbox(item), mi_rename)
        self.Bind(wx.EVT_MENU, lambda e: self._on_remove_mailbox(item), mi_remove)

    def _build_folder_menu(self, menu, item):
        f         = self._folder_map.get(item, {})
        is_system = f.get("folder_type", "custom") != "custom"

        mi_new_sub = menu.Append(wx.ID_ANY, tr("ctx_folder_new_sub"))
        mi_rename  = menu.Append(wx.ID_ANY, tr("ctx_folder_rename"))
        mi_delete  = menu.Append(wx.ID_ANY, tr("ctx_folder_delete"))

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
        mb = self._mailbox_map.get(parent_item)
        if not mb:
            return
        name = wx.GetTextFromUser(
            tr("new_folder_prompt"), tr("new_folder_title"), parent=self
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
        f = self._folder_map.get(parent_item)
        if not f:
            return
        name = wx.GetTextFromUser(
            tr("new_subfolder_prompt"), tr("new_subfolder_title"), parent=self
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
            tr("rename_folder_prompt"), tr("rename_folder_title"),
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
        use_trash = self.controller.get_setting("delete_to_trash", "1") == "1"
        confirm   = self.controller.get_setting("confirm_delete",  "1") == "1"

        if confirm:
            msg = (tr("dlg_delete_folder_trash", name=f["name"]) if use_trash
                   else tr("dlg_delete_folder_msg", name=f["name"]))
            if wx.MessageBox(msg, tr("dlg_delete_folder_title"),
                             wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) != wx.YES:
                return

        self.controller.delete_folder(f["id"], f["mailbox_id"], use_trash=use_trash)
        del self._folder_map[item]
        self.tree.Delete(item)

    def _on_rename_mailbox(self, item):
        mb = self._mailbox_map.get(item)
        if not mb:
            return
        new_name = wx.GetTextFromUser(
            tr("rename_mailbox_prompt"), tr("rename_mailbox_title"),
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
        if wx.MessageBox(tr("dlg_delete_mailbox_msg", name=mb["name"]),
                         tr("dlg_delete_mailbox_title"),
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) != wx.YES:
            return
        conn = self.controller.db._get_mailstore_conn()
        conn.execute(
            "DELETE FROM mails WHERE folder_id IN "
            "(SELECT id FROM folders WHERE mailbox_id = ?)", (mb["id"],)
        )
        conn.execute("DELETE FROM folders   WHERE mailbox_id = ?", (mb["id"],))
        conn.execute("DELETE FROM mailboxes WHERE id = ?",         (mb["id"],))
        conn.commit()
        self.reload()

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden                                                      #
    # ------------------------------------------------------------------ #

    def _get_item_data_dict(self, item) -> dict:
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
        item = self.tree.GetSelection()
        if item.IsOk():
            return self.tree.GetItemData(item)
        return None
