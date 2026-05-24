"""
FolderPanel – Linke Seite: Baumstruktur der Postfächer und Ordner
Screenreader-optimiert: aussagekräftige Namen, Tastaturnavigation
"""

import wx


# Ordner-Icon-Index (für ImageList)
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
    """Panel mit Postfach-/Ordner-Baumstruktur."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.on_folder_selected = None   # Callback: fn(folder_id, folder_name)

        self._folder_map = {}            # item_id -> folder dict
        self._mailbox_map = {}           # item_id -> mailbox dict

        self._build_ui()
        self._build_image_list()
        self._bind_events()
        self.reload()

    # ------------------------------------------------------------------ #
    #  UI aufbauen                                                        #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(self, label="Postfächer")
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
        self.tree.SetName("Postfächer und Ordner, Baumansicht")
        self.tree.SetToolTip(
            "Postfach- und Ordnerstruktur. "
            "Pfeiltasten zum Navigieren, Enter zum Öffnen. "
            "F6 wechselt zum nächsten Bereich."
        )
        sizer.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        self.SetSizer(sizer)

    def _build_image_list(self):
        """Erstellt eine einfache ImageList aus Systemicons."""
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
        self._image_list = il  # Referenz halten, sonst GC

    def _bind_events(self):
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_selection_changed)
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_item_activated)
        self.tree.Bind(wx.EVT_RIGHT_DOWN, self._on_right_click)

    # ------------------------------------------------------------------ #
    #  Daten laden                                                        #
    # ------------------------------------------------------------------ #

    def reload(self):
        self.tree.DeleteAllItems()
        self._folder_map.clear()
        self._mailbox_map.clear()

        root = self.tree.AddRoot("Root")
        mailboxes = self.controller.get_mailboxes()

        for mb in mailboxes:
            mb_id   = mb["id"]
            mb_name = mb["name"]
            mb_email= mb["email"]

            # Postfach-Knoten
            mb_item = self.tree.AppendItem(root, mb_name, ICON_MAILBOX, ICON_MAILBOX)
            self.tree.SetItemBold(mb_item, True)
            self.tree.SetItemData(mb_item, ("mailbox", mb_id))
            accessible_name = f"Postfach {mb_name}, {mb_email}"
            # Tooltip als Screenreader-Hilfe
            self._mailbox_map[mb_item] = dict(mb)

            # Ordner laden
            folders = self.controller.get_folders(mb_id)
            self._add_folder_items(mb_item, folders, parent_id=None)
            self.tree.Expand(mb_item)

    def _add_folder_items(self, parent_item, folders: list, parent_id):
        """Fügt Ordner-Items rekursiv hinzu."""
        for f in folders:
            if f["parent_id"] != parent_id:
                continue
            unread = f["unread"] or 0
            icon_idx = FOLDER_TYPE_ICONS.get(f["folder_type"], ICON_FOLDER)
            label = f["name"]
            if unread > 0:
                label = f"{f['name']} ({unread})"

            item = self.tree.AppendItem(parent_item, label, icon_idx, icon_idx)
            self.tree.SetItemData(item, ("folder", f["id"]))
            if unread > 0:
                self.tree.SetItemBold(item, True)
            self._folder_map[item] = dict(f)

            # Kinder
            self._add_folder_items(item, folders, parent_id=f["id"])

    # ------------------------------------------------------------------ #
    #  Event-Handler                                                      #
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self, event):
        try:
            if not self.tree:
                return
            item = event.GetItem()
            if not item.IsOk():
                return
            data = self.tree.GetItemData(item)
            if data and data[0] == "folder":
                folder_id = data[1]
                folder_name = self._folder_map.get(item, {}).get("name", "")
                if self.on_folder_selected:
                    self.on_folder_selected(folder_id, folder_name)
        except RuntimeError:
            pass  # C++-Objekt bereits zerstört

    def _on_item_activated(self, event):
        try:
            if not self.tree:
                return
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

    def _on_right_click(self, event):
        # Ordner-Kontext-Menü
        menu = wx.Menu()
        mi_new_sub = menu.Append(wx.ID_ANY, "Neuen Unterordner erstellen")
        mi_rename  = menu.Append(wx.ID_ANY, "Umbenennen")
        mi_delete  = menu.Append(wx.ID_ANY, "Löschen")
        self.Bind(wx.EVT_MENU, self._on_new_subfolder, mi_new_sub)
        self.Bind(wx.EVT_MENU, self._on_rename_folder, mi_rename)
        self.Bind(wx.EVT_MENU, self._on_delete_folder, mi_delete)
        self.PopupMenu(menu)
        menu.Destroy()

    def _on_new_subfolder(self, event):
        wx.MessageBox("Neuen Unterordner erstellen – noch nicht implementiert.", "Hinweis", wx.OK, self)

    def _on_rename_folder(self, event):
        wx.MessageBox("Ordner umbenennen – noch nicht implementiert.", "Hinweis", wx.OK, self)

    def _on_delete_folder(self, event):
        wx.MessageBox("Ordner löschen – noch nicht implementiert.", "Hinweis", wx.OK, self)

    # ------------------------------------------------------------------ #
    #  Öffentliche Methoden                                               #
    # ------------------------------------------------------------------ #

    def refresh_folder_unread(self, folder_id: int):
        """Aktualisiert den Ungelesen-Zähler eines Ordners."""
        for item, f in self._folder_map.items():
            if f["id"] == folder_id:
                # Neuen Wert aus DB holen
                folders = self.controller.get_folders(f["mailbox_id"])
                for updated in folders:
                    if updated["id"] == folder_id:
                        unread = updated["unread"] or 0
                        label  = updated["name"]
                        if unread > 0:
                            label = f"{updated['name']} ({unread})"
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
