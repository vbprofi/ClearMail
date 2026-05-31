"""
Addon: Adressbuch / Address Book
=================================
Eigene SQLite-Datenbank: ~/.mailclient/addressbook.db
GUI: Baumansicht (Gruppen) links | Kontaktliste rechts
Import/Export: vCard (.vcf), CSV (.csv)
Eigene Sprachdateien: locale/de/ und locale/en/
"""

import wx
import os
import csv
import re
import io
import sqlite3
from datetime import datetime
from core.addon_manager import AddonBase
from core.i18n import tr


# ------------------------------------------------------------------ #
#  Datenbank                                                          #
# ------------------------------------------------------------------ #

class AddressBookDB:
    """Eigene SQLite-Datenbank für das Adressbuch."""

    def __init__(self):
        data_dir = os.path.join(os.path.expanduser("~"), ".mailclient")
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, "addressbook.db")
        self._conn = None

    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self):
        self.conn().executescript("""
            CREATE TABLE IF NOT EXISTS groups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS contacts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id   INTEGER,
                firstname  TEXT DEFAULT '',
                lastname   TEXT DEFAULT '',
                email      TEXT DEFAULT '',
                email2     TEXT DEFAULT '',
                phone      TEXT DEFAULT '',
                mobile     TEXT DEFAULT '',
                org        TEXT DEFAULT '',
                title      TEXT DEFAULT '',
                address    TEXT DEFAULT '',
                notes      TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (group_id) REFERENCES groups(id)
            );
        """)
        # Demo-Daten nur beim ersten Start
        cur = self.conn().execute("SELECT COUNT(*) FROM groups")
        if cur.fetchone()[0] == 0:
            self.conn().execute("INSERT INTO groups (name, sort_order) VALUES ('Privat', 0)")
            self.conn().execute("INSERT INTO groups (name, sort_order) VALUES ('Arbeit', 10)")
            gid = self.conn().execute("SELECT id FROM groups WHERE name='Privat'").fetchone()[0]
            self.conn().execute("""
                INSERT INTO contacts (group_id, firstname, lastname, email, phone, org)
                VALUES (?, 'Max', 'Mustermann', 'max@example.com', '+49 30 12345678', 'Beispiel GmbH')
            """, (gid,))
            self.conn().execute("""
                INSERT INTO contacts (group_id, firstname, lastname, email, mobile)
                VALUES (?, 'Anna', 'Schmidt', 'anna@example.com', '+49 170 9876543')
            """, (gid,))
        self.conn().commit()

    def get_groups(self):
        return list(self.conn().execute(
            "SELECT * FROM groups ORDER BY sort_order, name").fetchall())

    def get_contacts(self, group_id=None, search=""):
        q = "SELECT * FROM contacts"
        params = []
        conditions = []
        if group_id is not None:
            conditions.append("group_id = ?"); params.append(group_id)
        if search:
            s = f"%{search}%"
            conditions.append(
                "(firstname LIKE ? OR lastname LIKE ? OR email LIKE ? OR org LIKE ?)")
            params.extend([s, s, s, s])
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY lastname, firstname"
        return list(self.conn().execute(q, params).fetchall())

    def save_contact(self, data: dict) -> int:
        fields = ["firstname","lastname","email","email2","phone","mobile",
                  "org","title","address","notes","group_id"]
        if data.get("id"):
            sets = ", ".join(f"{f}=?" for f in fields)
            vals = [data.get(f,"") for f in fields] + [data["id"]]
            self.conn().execute(f"UPDATE contacts SET {sets} WHERE id=?", vals)
            self.conn().commit()
            return data["id"]
        else:
            cols = ", ".join(fields)
            plh  = ", ".join("?" for _ in fields)
            vals = [data.get(f,"") for f in fields]
            cur  = self.conn().execute(f"INSERT INTO contacts ({cols}) VALUES ({plh})", vals)
            self.conn().commit()
            return cur.lastrowid

    def delete_contact(self, contact_id: int):
        self.conn().execute("DELETE FROM contacts WHERE id=?", (contact_id,))
        self.conn().commit()

    def save_group(self, data: dict) -> int:
        if data.get("id"):
            self.conn().execute("UPDATE groups SET name=? WHERE id=?",
                                (data["name"], data["id"]))
            self.conn().commit()
            return data["id"]
        cur = self.conn().execute("INSERT INTO groups (name) VALUES (?)", (data["name"],))
        self.conn().commit()
        return cur.lastrowid

    def delete_group(self, group_id: int):
        self.conn().execute("UPDATE contacts SET group_id=NULL WHERE group_id=?", (group_id,))
        self.conn().execute("DELETE FROM groups WHERE id=?", (group_id,))
        self.conn().commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# ------------------------------------------------------------------ #
#  vCard-Parser / -Writer                                             #
# ------------------------------------------------------------------ #

def _decode_qp(value: str) -> str:
    """Dekodiert Quoted-Printable."""
    try:
        import quopri
        return quopri.decodestring(value.encode()).decode("utf-8", errors="replace")
    except Exception:
        return value


def parse_vcf(text: str) -> list[dict]:
    """Parst eine oder mehrere vCards aus einem String."""
    contacts = []
    current  = {}
    in_card  = False

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper() == "BEGIN:VCARD":
            current = {}; in_card = True; continue
        if line.upper() == "END:VCARD":
            if current:
                contacts.append(current)
            in_card = False; continue
        if not in_card:
            continue

        key, _, value = line.partition(":")
        key_upper = key.upper().split(";")[0]
        if "ENCODING=QUOTED-PRINTABLE" in key.upper():
            value = _decode_qp(value)

        if key_upper == "FN":
            parts = value.split(" ", 1)
            current.setdefault("firstname", parts[0])
            current.setdefault("lastname",  parts[1] if len(parts) > 1 else "")
        elif key_upper == "N":
            parts = value.split(";")
            current["lastname"]  = parts[0] if len(parts) > 0 else ""
            current["firstname"] = parts[1] if len(parts) > 1 else ""
        elif key_upper in ("EMAIL", "EMAIL;TYPE=INTERNET",
                           "EMAIL;TYPE=HOME", "EMAIL;TYPE=WORK"):
            if "email" not in current:
                current["email"] = value
            else:
                current["email2"] = value
        elif key_upper in ("TEL", "TEL;TYPE=VOICE", "TEL;TYPE=HOME"):
            current.setdefault("phone", value)
        elif key_upper in ("TEL;TYPE=CELL", "TEL;TYPE=MOBILE"):
            current.setdefault("mobile", value)
        elif key_upper == "ORG":
            current["org"] = value.split(";")[0]
        elif key_upper == "TITLE":
            current["title"] = value
        elif key_upper == "ADR":
            current["address"] = value.replace(";", " ").strip()
        elif key_upper == "NOTE":
            current["notes"] = value

    return contacts


def write_vcf(contacts: list) -> str:
    """Schreibt Kontakte als vCard-String."""
    lines = []
    for c in contacts:
        lines.append("BEGIN:VCARD")
        lines.append("VERSION:3.0")
        name = f"{c.get('lastname','')};{c.get('firstname','')};;;"
        fn   = f"{c.get('firstname','')} {c.get('lastname','')}".strip()
        lines.append(f"N:{name}")
        lines.append(f"FN:{fn}")
        if c.get("email"):  lines.append(f"EMAIL;TYPE=INTERNET:{c['email']}")
        if c.get("email2"): lines.append(f"EMAIL;TYPE=INTERNET:{c['email2']}")
        if c.get("phone"):  lines.append(f"TEL;TYPE=VOICE:{c['phone']}")
        if c.get("mobile"): lines.append(f"TEL;TYPE=CELL:{c['mobile']}")
        if c.get("org"):    lines.append(f"ORG:{c['org']}")
        if c.get("title"):  lines.append(f"TITLE:{c['title']}")
        if c.get("address"):lines.append(f"ADR:;;{c['address']};;;;")
        if c.get("notes"):  lines.append(f"NOTE:{c['notes']}")
        lines.append("END:VCARD")
        lines.append("")
    return "\n".join(lines)


def parse_csv(text: str) -> list[dict]:
    """Parst CSV-Kontakte. Unterstützt Outlook-Export und generisches Format."""
    contacts = []
    reader   = csv.DictReader(io.StringIO(text))
    # Spalten-Mapping (Outlook-Export ↔ intern)
    mapping  = {
        "Vorname": "firstname", "First Name": "firstname", "firstname": "firstname",
        "Nachname": "lastname",  "Last Name":  "lastname",  "lastname":  "lastname",
        "E-Mail-Adresse": "email", "E-mail Address": "email", "email": "email",
        "E-Mail 2": "email2",    "email2": "email2",
        "Telefon (privat)": "phone", "Home Phone": "phone", "phone": "phone",
        "Mobiltelefon": "mobile", "Mobile Phone": "mobile", "mobile": "mobile",
        "Firma": "org",          "Company": "org",           "org": "org",
        "Position": "title",     "Job Title": "title",       "title": "title",
        "Notizen": "notes",      "Notes": "notes",           "notes": "notes",
    }
    for row in reader:
        c = {}
        for src, dst in mapping.items():
            if src in row and row[src].strip():
                c.setdefault(dst, row[src].strip())
        if c:
            contacts.append(c)
    return contacts


def write_csv(contacts: list) -> str:
    out     = io.StringIO()
    fields  = ["firstname","lastname","email","email2","phone","mobile","org","title","notes"]
    headers = ["Vorname","Nachname","E-Mail-Adresse","E-Mail 2",
               "Telefon","Mobil","Firma","Position","Notizen"]
    writer  = csv.writer(out)
    writer.writerow(headers)
    for c in contacts:
        writer.writerow([c.get(f,"") for f in fields])
    return out.getvalue()


# ------------------------------------------------------------------ #
#  Kontakt-Dialog                                                     #
# ------------------------------------------------------------------ #

class ContactDialog(wx.Dialog):

    def __init__(self, parent, data=None):
        title = tr("ab_contact_title_edit") if data else tr("ab_contact_title_new")
        super().__init__(parent, title=title, size=(480, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._data = data or {}
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)
        nb    = wx.Notebook(panel)

        # ---- Basisdaten ----
        pg1 = wx.Panel(nb)
        gs  = wx.FlexGridSizer(cols=2, vgap=7, hgap=8)
        gs.AddGrowableCol(1)

        def f(label, key, pw=False):
            lbl  = wx.StaticText(pg1, label=label)
            ctrl = wx.TextCtrl(pg1, style=wx.TE_PASSWORD if pw else 0)
            ctrl.SetName(label.rstrip(":"))
            ctrl.SetValue(str(self._data.get(key, "")))
            gs.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            gs.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.txt_firstname = f(tr("ab_contact_firstname"), "firstname")
        self.txt_lastname  = f(tr("ab_contact_lastname"),  "lastname")
        self.txt_email     = f(tr("ab_contact_email"),     "email")
        self.txt_email2    = f(tr("ab_contact_email2"),    "email2")
        self.txt_phone     = f(tr("ab_contact_phone"),     "phone")
        self.txt_mobile    = f(tr("ab_contact_mobile"),    "mobile")
        self.txt_org       = f(tr("ab_contact_org"),       "org")
        self.txt_title_f   = f(tr("ab_contact_title_field"), "title")

        pg1.SetSizer(self._w(gs));  nb.AddPage(pg1, tr("ab_contacts"))

        # ---- Adresse / Notizen ----
        pg2 = wx.Panel(nb)
        gs2 = wx.FlexGridSizer(cols=2, vgap=7, hgap=8)
        gs2.AddGrowableCol(1)
        lbl_addr = wx.StaticText(pg2, label=tr("ab_contact_address"))
        self.txt_address = wx.TextCtrl(pg2, style=wx.TE_MULTILINE, size=(-1, 60))
        self.txt_address.SetName(tr("ab_contact_address"))
        self.txt_address.SetValue(str(self._data.get("address", "")))
        gs2.Add(lbl_addr, 0, wx.ALIGN_TOP | wx.TOP, 3)
        gs2.Add(self.txt_address, 1, wx.EXPAND)
        lbl_notes = wx.StaticText(pg2, label=tr("ab_contact_notes"))
        self.txt_notes = wx.TextCtrl(pg2, style=wx.TE_MULTILINE, size=(-1, 80))
        self.txt_notes.SetName(tr("ab_contact_notes"))
        self.txt_notes.SetValue(str(self._data.get("notes", "")))
        gs2.Add(lbl_notes, 0, wx.ALIGN_TOP | wx.TOP, 3)
        gs2.Add(self.txt_notes, 1, wx.EXPAND)
        pg2.SetSizer(self._w(gs2));  nb.AddPage(pg2, tr("ab_contact_address"))

        outer.Add(nb, 1, wx.EXPAND | wx.ALL, 6)
        bs = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(panel, wx.ID_OK, tr("dlg_save"))
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, tr("dlg_cancel"))
        btn_ok.SetDefault()
        bs.AddButton(btn_ok);  bs.AddButton(btn_cancel);  bs.Realize()
        outer.Add(bs, 0, wx.EXPAND | wx.ALL, 6)
        panel.SetSizer(outer)
        self.txt_firstname.SetFocus()

    @staticmethod
    def _w(grid):
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(grid, 1, wx.EXPAND | wx.ALL, 10)
        return s

    def get_data(self) -> dict:
        return {
            "id":        self._data.get("id"),
            "group_id":  self._data.get("group_id"),
            "firstname": self.txt_firstname.GetValue().strip(),
            "lastname":  self.txt_lastname.GetValue().strip(),
            "email":     self.txt_email.GetValue().strip(),
            "email2":    self.txt_email2.GetValue().strip(),
            "phone":     self.txt_phone.GetValue().strip(),
            "mobile":    self.txt_mobile.GetValue().strip(),
            "org":       self.txt_org.GetValue().strip(),
            "title":     self.txt_title_f.GetValue().strip(),
            "address":   self.txt_address.GetValue().strip(),
            "notes":     self.txt_notes.GetValue().strip(),
        }


# ------------------------------------------------------------------ #
#  Adressbuch-Fenster                                                 #
# ------------------------------------------------------------------ #

class AddressBookFrame(wx.Frame):

    def __init__(self, parent, db: AddressBookDB):
        super().__init__(parent, title=tr("ab_title"), size=(820, 580),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.db   = db
        self._sel_group_id = None
        self._contacts     = []
        self._build_menu()   # ZUERST: Menü-Items anlegen
        self._build_ui()     # DANN: UI (ohne _bind()-Aufruf)
        self._bind()         # ZULETZT: alle Events verbinden
        self._load_groups()
        self.Centre()

    def _build_ui(self):
        panel = wx.Panel(self)
        main  = wx.BoxSizer(wx.HORIZONTAL)

        # ---- Links: Gruppen-Baum ----
        left = wx.BoxSizer(wx.VERTICAL)
        lbl  = wx.StaticText(panel, label=tr("ab_groups"))
        lbl.SetFont(lbl.GetFont().Bold())
        left.Add(lbl, 0, wx.ALL, 4)

        self.tree = wx.TreeCtrl(panel,
            style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_SINGLE | wx.BORDER_SUNKEN)
        self.tree.SetName(tr("ab_groups") + ", " + tr("ab_title"))
        self.tree.SetMinSize((180, -1))
        left.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        main.Add(left, 0, wx.EXPAND | wx.ALL, 4)

        # ---- Rechts: Suche + Kontaktliste ----
        right = wx.BoxSizer(wx.VERTICAL)

        # Suchzeile (Label zuerst → AT)
        search_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_search = wx.StaticText(panel, label=tr("ab_search"))
        self.txt_search = wx.SearchCtrl(panel)
        self.txt_search.SetName(tr("ab_search"))
        search_row.Add(lbl_search, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        search_row.Add(self.txt_search, 1)
        right.Add(search_row, 0, wx.EXPAND | wx.ALL, 4)

        lbl_c = wx.StaticText(panel, label=tr("ab_contacts"))
        lbl_c.SetFont(lbl_c.GetFont().Bold())
        right.Add(lbl_c, 0, wx.LEFT | wx.BOTTOM, 4)

        self.list_ctrl = wx.ListCtrl(panel,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
        self.list_ctrl.SetName(tr("ab_contacts") + ", " + tr("ab_title"))
        self.list_ctrl.InsertColumn(0, tr("ab_col_name"),  width=180)
        self.list_ctrl.InsertColumn(1, tr("ab_col_email"), width=200)
        self.list_ctrl.InsertColumn(2, tr("ab_col_phone"), width=120)
        self.list_ctrl.InsertColumn(3, tr("ab_col_org"),   width=150)
        right.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        # Toolbar-Buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_new     = wx.Button(panel, label=tr("ab_new_contact"))
        self.btn_edit    = wx.Button(panel, label=tr("ab_edit_contact"))
        self.btn_delete  = wx.Button(panel, label=tr("ab_delete_contact"))
        self.btn_import  = wx.Button(panel, label=tr("ab_import"))
        self.btn_export  = wx.Button(panel, label=tr("ab_export"))
        for b in (self.btn_new, self.btn_edit, self.btn_delete,
                  self.btn_import, self.btn_export):
            btn_row.Add(b, 0, wx.RIGHT, 6)
        right.Add(btn_row, 0, wx.LEFT | wx.BOTTOM, 4)
        main.Add(right, 1, wx.EXPAND | wx.ALL, 4)

        panel.SetSizer(main)

    def _build_menu(self):
        mb  = wx.MenuBar()
        mab = wx.Menu()
        self.mi_new    = mab.Append(wx.ID_ANY, tr("ab_new_contact"))
        self.mi_edit   = mab.Append(wx.ID_ANY, tr("ab_edit_contact"))
        self.mi_delete = mab.Append(wx.ID_ANY, tr("ab_delete_contact"))
        mab.AppendSeparator()
        self.mi_import = mab.Append(wx.ID_ANY, tr("ab_import"))
        self.mi_export = mab.Append(wx.ID_ANY, tr("ab_export"))
        mab.AppendSeparator()
        self.mi_close  = mab.Append(wx.ID_CLOSE, tr("ab_close"))
        mb.Append(mab, tr("ab_title"))
        self.SetMenuBar(mb)

        mgrp = wx.Menu()
        self.mi_new_grp    = mgrp.Append(wx.ID_ANY, tr("ab_new_group"))
        self.mi_rename_grp = mgrp.Append(wx.ID_ANY, tr("ab_rename_group"))
        self.mi_del_grp    = mgrp.Append(wx.ID_ANY, tr("ab_delete_group"))
        mb.Append(mgrp, tr("ab_groups"))

    def _bind(self):
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_group_sel)
        self.tree.Bind(wx.EVT_RIGHT_DOWN,        self._on_group_ctx)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_edit_contact)
        self.txt_search.Bind(wx.EVT_TEXT, lambda e: self._load_contacts())
        self.btn_new.Bind(wx.EVT_BUTTON,    self._on_new_contact)
        self.btn_edit.Bind(wx.EVT_BUTTON,   self._on_edit_contact)
        self.btn_delete.Bind(wx.EVT_BUTTON, self._on_delete_contact)
        self.btn_import.Bind(wx.EVT_BUTTON, self._on_import)
        self.btn_export.Bind(wx.EVT_BUTTON, self._on_export)
        self.Bind(wx.EVT_MENU, self._on_new_contact,    self.mi_new)
        self.Bind(wx.EVT_MENU, self._on_edit_contact,   self.mi_edit)
        self.Bind(wx.EVT_MENU, self._on_delete_contact, self.mi_delete)
        self.Bind(wx.EVT_MENU, self._on_import,         self.mi_import)
        self.Bind(wx.EVT_MENU, self._on_export,         self.mi_export)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(),  self.mi_close)
        self.Bind(wx.EVT_MENU, self._on_new_group,    self.mi_new_grp)
        self.Bind(wx.EVT_MENU, self._on_rename_group, self.mi_rename_grp)
        self.Bind(wx.EVT_MENU, self._on_delete_group, self.mi_del_grp)

    # ------------------------------------------------------------------ #
    #  Gruppen                                                            #
    # ------------------------------------------------------------------ #

    def _load_groups(self):
        try:
            self.tree.DeleteAllItems()
        except RuntimeError:
            return
        self._group_map = {}
        root = self.tree.AddRoot("root")

        # "Alle Kontakte"
        all_item = self.tree.AppendItem(root, tr("ab_group_all"))
        self.tree.SetItemData(all_item, None)
        self._all_item = all_item

        for g in self.db.get_groups():
            item = self.tree.AppendItem(root, g["name"])
            self.tree.SetItemData(item, g["id"])
            self._group_map[item] = dict(g)

        self.tree.SelectItem(all_item)
        self._sel_group_id = None
        self._load_contacts()

    def _on_group_sel(self, event):
        try:
            item = event.GetItem()
            if not item.IsOk():
                return
            gid = self.tree.GetItemData(item)
            self._sel_group_id = gid
            self._load_contacts()
        except RuntimeError:
            pass  # C++-Objekt bereits zerstört

    def _on_group_ctx(self, event):
        try:
            menu = wx.Menu()
            mi_new    = menu.Append(wx.ID_ANY, tr("ab_new_group"))
            mi_rename = menu.Append(wx.ID_ANY, tr("ab_rename_group"))
            mi_del    = menu.Append(wx.ID_ANY, tr("ab_delete_group"))
            self.Bind(wx.EVT_MENU, self._on_new_group,    mi_new)
            self.Bind(wx.EVT_MENU, self._on_rename_group, mi_rename)
            self.Bind(wx.EVT_MENU, self._on_delete_group, mi_del)
            self.tree.PopupMenu(menu)
            menu.Destroy()
        except RuntimeError:
            pass

    def _on_new_group(self, event=None):
        name = wx.GetTextFromUser(tr("ab_group_prompt"), tr("ab_group_new_title"), parent=self).strip()
        if name:
            self.db.save_group({"name": name})
            self._load_groups()

    def _on_rename_group(self, event=None):
        try:
            item = self.tree.GetSelection()
            if not item.IsOk() or self.tree.GetItemData(item) is None:
                return
        except RuntimeError:
            return
        g    = self._group_map.get(item, {})
        name = wx.GetTextFromUser(tr("ab_group_prompt"), tr("ab_group_rename_title"),
                                  default_value=g.get("name",""), parent=self).strip()
        if name:
            self.db.save_group({"id": g["id"], "name": name})
            self._load_groups()

    def _on_delete_group(self, event=None):
        try:
            item = self.tree.GetSelection()
            if not item.IsOk() or self.tree.GetItemData(item) is None:
                return
        except RuntimeError:
            return
        g = self._group_map.get(item, {})
        if wx.MessageBox(tr("ab_group_del_msg", name=g.get("name","")),
                         tr("ab_group_del_title"),
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) == wx.YES:
            self.db.delete_group(g["id"])
            self._load_groups()

    # ------------------------------------------------------------------ #
    #  Kontakte                                                           #
    # ------------------------------------------------------------------ #

    def _load_contacts(self):
        try:
            self.list_ctrl.DeleteAllItems()
        except RuntimeError:
            return
        search = self.txt_search.GetValue().strip()
        self._contacts = self.db.get_contacts(self._sel_group_id, search)
        for c in self._contacts:
            name = f"{c['firstname']} {c['lastname']}".strip()
            idx  = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), name)
            self.list_ctrl.SetItem(idx, 1, str(c["email"]  or ""))
            self.list_ctrl.SetItem(idx, 2, str(c["phone"]  or ""))
            self.list_ctrl.SetItem(idx, 3, str(c["org"]    or ""))

    def _selected_contact(self):
        idx = self.list_ctrl.GetFirstSelected()
        if idx < 0 or idx >= len(self._contacts):
            return None
        return dict(self._contacts[idx])

    def _on_new_contact(self, event=None):
        data = {}
        if self._sel_group_id is not None:
            data["group_id"] = self._sel_group_id
        dlg = ContactDialog(self, data)
        if dlg.ShowModal() == wx.ID_OK:
            self.db.save_contact(dlg.get_data())
            self._load_contacts()
        dlg.Destroy()

    def _on_edit_contact(self, event=None):
        c = self._selected_contact()
        if not c:
            wx.MessageBox(tr("ab_no_contact_sel"), tr("ab_title"), wx.OK, self)
            return
        dlg = ContactDialog(self, c)
        if dlg.ShowModal() == wx.ID_OK:
            self.db.save_contact(dlg.get_data())
            self._load_contacts()
        dlg.Destroy()

    def _on_delete_contact(self, event=None):
        c = self._selected_contact()
        if not c:
            wx.MessageBox(tr("ab_no_contact_sel"), tr("ab_title"), wx.OK, self)
            return
        name = f"{c.get('firstname','')} {c.get('lastname','')}".strip()
        if wx.MessageBox(tr("ab_del_contact_msg", name=name), tr("ab_del_contact_title"),
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) == wx.YES:
            self.db.delete_contact(c["id"])
            self._load_contacts()

    # ------------------------------------------------------------------ #
    #  Import / Export                                                    #
    # ------------------------------------------------------------------ #

    def _on_import(self, event=None):
        with wx.FileDialog(self, tr("ab_import_title"),
                           wildcard=tr("ab_wildcard_all") + "|" + tr("ab_wildcard_vcard") + "|" + tr("ab_wildcard_csv"),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as d:
            if d.ShowModal() != wx.ID_OK:
                return
            paths = d.GetPaths()

        count = 0
        try:
            gid = self._sel_group_id
            for path in paths:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                if path.lower().endswith(".vcf"):
                    contacts = parse_vcf(text)
                else:
                    contacts = parse_csv(text)
                for c in contacts:
                    c["group_id"] = gid
                    self.db.save_contact(c)
                    count += 1
            wx.MessageBox(tr("ab_import_ok", count=count), tr("ab_import_title"), wx.OK, self)
            self._load_contacts()
        except Exception as e:
            wx.MessageBox(tr("ab_import_err", error=str(e)), tr("ab_title"), wx.OK | wx.ICON_ERROR, self)

    def _on_export(self, event=None):
        contacts = self.db.get_contacts(self._sel_group_id)
        if not contacts:
            return
        with wx.FileDialog(self, tr("ab_export_title"),
                           wildcard=tr("ab_wildcard_vcard") + "|" + tr("ab_wildcard_csv"),
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as d:
            if d.ShowModal() != wx.ID_OK:
                return
            path = d.GetPath()

        try:
            data = [dict(c) for c in contacts]
            if path.lower().endswith(".csv"):
                text = write_csv(data)
            else:
                if not path.lower().endswith(".vcf"):
                    path += ".vcf"
                text = write_vcf(data)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            wx.MessageBox(tr("ab_export_ok", count=len(data)), tr("ab_export_title"), wx.OK, self)
        except Exception as e:
            wx.MessageBox(tr("ab_export_err", error=str(e)), tr("ab_title"), wx.OK | wx.ICON_ERROR, self)


# ================================================================== #
#  Addon-Klasse                                                       #
# ================================================================== #

class Addon(AddonBase):

    NAME        = "addressbook"
    VERSION     = "1.0.0"
    DESCRIPTION = "Adressbuch / Address Book (vCard, CSV)"

    def on_load(self):
        self._db  = AddressBookDB()
        self._db.initialize()
        self._win = None

    def on_unload(self):
        if self._win and self._win:
            try:
                self._win.Close()
            except Exception:
                pass
        self._db.close()

    def open_window(self, parent):
        if self._win is None or not self._win:
            self._win = AddressBookFrame(parent, self._db)
        self._win.Show()
        self._win.Raise()

    def get_settings_panel(self, parent) -> wx.Panel:
        return AddressBookSettingsPanel(parent, self.controller, self._db)

    def get_menu_items(self) -> list:
        return [{
            "label":   tr("ab_menu_open"),
            "handler": self._open_from_menu,
        }]

    def _open_from_menu(self, mail_id=None):
        app   = wx.GetApp()
        frame = app.GetTopWindow() if app else None
        self.open_window(frame)


# ------------------------------------------------------------------ #
#  Addon-Einstellungs-Panel für das Adressbuch                       #
# ------------------------------------------------------------------ #

class AddressBookSettingsPanel(wx.Panel):
    """
    Einstellungen für das Adressbuch-Addon:
      - Angezeigte Felder konfigurieren (Reihenfolge + Sichtbarkeit)
      - Beispieldaten beim ersten Start: ja/nein
      - Datenbank-Pfad anzeigen
    """

    # Alle verfügbaren Felder mit Anzeigename und DB-Spaltenname
    ALL_FIELDS = [
        ("firstname",  "ab_field_firstname"),
        ("lastname",   "ab_field_lastname"),
        ("email",      "ab_field_email"),
        ("email2",     "ab_field_email2"),
        ("phone",      "ab_field_phone"),
        ("mobile",     "ab_field_mobile"),
        ("org",        "ab_field_org"),
        ("title",      "ab_field_title"),
        ("address",    "ab_field_address"),
        ("notes",      "ab_field_notes"),
    ]

    def __init__(self, parent, controller, db):
        super().__init__(parent)
        self._ctrl = controller
        self._db   = db
        self._build()
        self._load()

    def _build(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ---- Sichtbare Felder ----
        lbl = wx.StaticText(self, label=tr("ab_settings_fields_label"))
        lbl.SetFont(lbl.GetFont().Bold())
        sizer.Add(lbl, 0, wx.ALL, 8)

        hint = wx.StaticText(self, label=tr("ab_settings_fields_hint"))
        hint.SetForegroundColour(wx.Colour(100, 100, 100))
        sizer.Add(hint, 0, wx.LEFT | wx.BOTTOM, 8)

        self._chk_fields = {}
        field_grid = wx.GridSizer(cols=2, vgap=4, hgap=12)
        for col, key in self.ALL_FIELDS:
            chk = wx.CheckBox(self, label=tr(key))
            chk.SetName(col)
            self._chk_fields[col] = chk
            field_grid.Add(chk, 0)
        sizer.Add(field_grid, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ---- Beispieldaten ----
        self.chk_sample = wx.CheckBox(self, label=tr("ab_settings_sample_data"))
        self.chk_sample.SetName(tr("ab_settings_sample_data"))
        sizer.Add(self.chk_sample, 0, wx.ALL, 8)

        lbl_sample_hint = wx.StaticText(self, label=tr("ab_settings_sample_hint"))
        lbl_sample_hint.SetForegroundColour(wx.Colour(100, 100, 100))
        sizer.Add(lbl_sample_hint, 0, wx.LEFT | wx.BOTTOM, 8)

        # ---- Datenbankpfad ----
        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        db_path = self._db._path if self._db else "?"
        lbl_db = wx.StaticText(self, label=tr("ab_settings_db_path", path=db_path))
        lbl_db.SetForegroundColour(wx.Colour(100, 100, 100))
        sizer.Add(lbl_db, 0, wx.ALL, 8)

        self.SetSizer(sizer)

    def _load(self):
        # Sichtbare Felder laden (Standard: alle sichtbar)
        visible_raw = self._ctrl.get_setting("ab_visible_fields", "")
        if visible_raw:
            visible = set(visible_raw.split(","))
        else:
            visible = {col for col, _ in self.ALL_FIELDS}
        for col, chk in self._chk_fields.items():
            chk.SetValue(col in visible)
        # Beispieldaten
        self.chk_sample.SetValue(
            self._ctrl.get_setting("ab_sample_data", "1") == "1")

    def save(self):
        visible = [col for col, chk in self._chk_fields.items() if chk.GetValue()]
        if not visible:
            import wx as _wx
            _wx.MessageBox(tr("ab_settings_fields_required"),
                           tr("error_title"), _wx.OK | _wx.ICON_WARNING)
            raise ValueError("Mindestens ein Feld muss sichtbar sein.")
        self._ctrl.set_setting("ab_visible_fields", ",".join(visible))
        old_sample = self._ctrl.get_setting("ab_sample_data", "1")
        new_sample = "1" if self.chk_sample.GetValue() else "0"
        self._ctrl.set_setting("ab_sample_data", new_sample)
        # Wenn Beispieldaten neu aktiviert und DB leer → Beispieldaten einfügen
        if new_sample == "1" and old_sample == "0":
            try:
                cur = self._db.conn().execute("SELECT COUNT(*) FROM contacts")
                if cur.fetchone()[0] == 0:
                    self._db.initialize()
            except Exception:
                pass
