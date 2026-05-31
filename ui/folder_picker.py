"""
FolderPickerDialog – Ordnerauswahl für Kopieren/Verschieben.

FIX (2026-05):
  RuntimeError "wrapped C/C++ object of type TreeCtrl has been deleted"
  Der Fehler trat auf weil EVT_TREE_SEL_CHANGED nach EndModal() noch
  gefeuert wurde und _on_sel() dann auf das bereits zerstörte TreeCtrl
  zugriff. Lösung: IsOk()-Guard + try/except RuntimeError in _on_sel,
  und Bind auf EVT_TREE_ITEM_ACTIVATED nutzt EndModal nur wenn Dialog
  noch offen ist (self.IsShown()).
"""

import wx
from core.i18n import tr


class FolderPickerDialog(wx.Dialog):

    def __init__(self, parent, controller, title: str = None):
        super().__init__(parent, title=title or tr("ctx_copy_to_folder"),
                         size=(340, 440),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.controller         = controller
        self.selected_folder_id = None
        self._folder_map        = {}
        self._closing           = False   # Guard gegen Post-Modal-Events
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
            style=(wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT |
                   wx.TR_HIDE_ROOT | wx.TR_SINGLE | wx.BORDER_SUNKEN)
        )
        self.tree.SetName(tr("ctx_copy_to_folder"))
        sizer.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        bs          = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK,     tr("dlg_save"))
        btn_cancel  = wx.Button(panel, wx.ID_CANCEL, tr("dlg_cancel"))
        self.btn_ok.SetDefault()
        self.btn_ok.Enable(False)
        bs.AddButton(self.btn_ok)
        bs.AddButton(btn_cancel)
        bs.Realize()
        sizer.Add(bs, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(sizer)

        # FIX: try/except RuntimeError Guard in allen Tree-Callbacks
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED,    self._on_sel)
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_activated)
        self.Bind(wx.EVT_CLOSE,                    self._on_close)

    def _on_close(self, event):
        self._closing = True
        event.Skip()

    def _load(self):
        self.tree.DeleteAllItems()
        self._folder_map.clear()
        root = self.tree.AddRoot("Root")

        FOLDER_ORDER = {
            "inbox": 0, "sent": 1, "drafts": 2, "outbox": 3,
            "trash": 4, "spam": 5, "archive": 6, "custom": 7,
        }

        for mb in self.controller.get_mailboxes():
            mb      = dict(mb)
            mb_item = self.tree.AppendItem(root, mb["name"])
            self.tree.SetItemBold(mb_item, True)
            self.tree.SetItemData(mb_item, None)  # Postfächer nicht wählbar

            folders = [dict(f) for f in self.controller.get_folders(mb["id"])]
            # Top-Level-Ordner sortiert nach Typ
            top = sorted(
                [f for f in folders if f["parent_id"] is None],
                key=lambda f: (FOLDER_ORDER.get(f.get("folder_type", "custom"), 7),
                               (f["name"] or "").lower())
            )
            for f in top:
                f_item = self.tree.AppendItem(mb_item, f["name"])
                self.tree.SetItemData(f_item, f["id"])
                self._folder_map[f_item] = f["id"]
                self._add_children(f_item, folders, f["id"], FOLDER_ORDER)

            self.tree.Expand(mb_item)

    def _add_children(self, parent_item, all_folders, parent_id, order):
        children = sorted(
            [f for f in all_folders if f["parent_id"] == parent_id],
            key=lambda f: (order.get(f.get("folder_type", "custom"), 7),
                           (f["name"] or "").lower())
        )
        for f in children:
            item = self.tree.AppendItem(parent_item, f["name"])
            self.tree.SetItemData(item, f["id"])
            self._folder_map[item] = f["id"]
            self._add_children(item, all_folders, f["id"], order)

    def _on_sel(self, event):
        # FIX: Guard gegen Post-Modal-Events auf bereits zerstörtem C++-Objekt
        if self._closing:
            return
        try:
            item = event.GetItem()
            if not item or not item.IsOk():
                return
            fid = self.tree.GetItemData(item)
            self.selected_folder_id = fid
            self.btn_ok.Enable(fid is not None)
        except RuntimeError:
            # TreeCtrl wurde bereits zerstört – Event ignorieren
            pass

    def _on_activated(self, event):
        # FIX: nur EndModal wenn Dialog noch sichtbar ist
        if self._closing:
            return
        try:
            if self.selected_folder_id is not None and self.IsShown():
                self.EndModal(wx.ID_OK)
        except RuntimeError:
            pass
