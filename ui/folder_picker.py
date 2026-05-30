"""
FolderPickerDialog – Ordnerauswahl-Dialog für Kopieren/Verschieben.
Zeigt alle Postfächer und Ordner als Baumstruktur.
"""

import wx
from core.i18n import tr


class FolderPickerDialog(wx.Dialog):

    def __init__(self, parent, controller, title: str = None):
        super().__init__(parent, title=title or tr("ctx_copy_to_folder"),
                         size=(340, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller        = controller
        self.selected_folder_id = None
        self._folder_map       = {}
        self._build_ui()
        self._load()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label=tr("ctx_copy_to_folder"))
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 8)

        self.tree = wx.TreeCtrl(
            panel,
            style=wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT |
                  wx.TR_HIDE_ROOT | wx.TR_SINGLE | wx.BORDER_SUNKEN
        )
        self.tree.SetName(tr("ctx_copy_to_folder"))
        sizer.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        bs = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK,     tr("dlg_save"))
        btn_cancel  = wx.Button(panel, wx.ID_CANCEL, tr("dlg_cancel"))
        self.btn_ok.SetDefault()
        self.btn_ok.Enable(False)   # erst aktiv wenn Ordner gewählt
        bs.AddButton(self.btn_ok); bs.AddButton(btn_cancel); bs.Realize()
        sizer.Add(bs, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(sizer)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_sel)
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_activated)

    def _load(self):
        self.tree.DeleteAllItems()
        self._folder_map.clear()
        root = self.tree.AddRoot("Root")

        for mb in self.controller.get_mailboxes():
            mb_item = self.tree.AppendItem(root, mb["name"])
            self.tree.SetItemBold(mb_item, True)
            self.tree.SetItemData(mb_item, None)  # Postfach → nicht wählbar

            for f in self.controller.get_folders(mb["id"]):
                if f["parent_id"] is not None:
                    continue  # Unterordner werden unten hinzugefügt
                f_item = self.tree.AppendItem(mb_item, f["name"])
                self.tree.SetItemData(f_item, f["id"])
                self._folder_map[f_item] = f["id"]
                self._add_children(f_item, mb["id"], f["id"],
                                   self.controller.get_folders(mb["id"]))

            self.tree.Expand(mb_item)

    def _add_children(self, parent_item, mailbox_id, parent_id, all_folders):
        for f in all_folders:
            if f["parent_id"] != parent_id:
                continue
            item = self.tree.AppendItem(parent_item, f["name"])
            self.tree.SetItemData(item, f["id"])
            self._folder_map[item] = f["id"]
            self._add_children(item, mailbox_id, f["id"], all_folders)

    def _on_sel(self, event):
        item = event.GetItem()
        if item.IsOk():
            fid = self.tree.GetItemData(item)
            self.selected_folder_id = fid
            self.btn_ok.Enable(fid is not None)

    def _on_activated(self, event):
        if self.selected_folder_id is not None:
            self.EndModal(wx.ID_OK)
