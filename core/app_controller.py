"""
AppController – MVC-Controller-Schicht

IMAP-Thread-Sicherheit (sqlite3.InterfaceError-Fix):
  SQLite-Verbindungen dürfen NICHT thread-übergreifend verwendet werden.
  Daher: alle DB-Zugriffe passieren AUSSCHLIESSLICH im Haupt-Thread.
  Worker-Threads erhalten nur primitive Werte (str, int, dict mit Strings).

  Muster:
    # Haupt-Thread: alle Daten aus DB lesen
    uid, imap_path, acc = self._resolve_mail_imap(mail_id, folder_id)
    # Worker-Thread: nur IMAP-Netzwerk, KEIN self.db-Zugriff
    def _w(uid=uid, path=imap_path, acc=acc): ...
    threading.Thread(target=_w, daemon=True).start()
"""

from __future__ import annotations
import os
import json
import threading
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from database.db_manager import DatabaseManager
    from core.addon_manager import AddonManager


class AppController:

    def __init__(self, db: "DatabaseManager", addon_mgr: "AddonManager"):
        self.db        = db
        self.addon_mgr = addon_mgr
        self.view      = None

    # ------------------------------------------------------------------ #
    #  Struktur                                                           #
    # ------------------------------------------------------------------ #

    def get_mailboxes(self): return self.db.get_mailboxes()
    def get_folders(self, mailbox_id: int): return self.db.get_folders(mailbox_id)

    def get_trash_folder_id(self, mailbox_id: int) -> Optional[int]:
        for f in self.db.get_folders(mailbox_id):
            if f["folder_type"] == "trash":
                return f["id"]
        return None

    # ------------------------------------------------------------------ #
    #  Mails                                                              #
    # ------------------------------------------------------------------ #

    def get_mails(self, folder_id: int) -> list:
        return self.db.get_mails(folder_id)

    def get_mail(self, mail_id: int, folder_id: int = None):
        """Lädt eine Mail. Markiert sie NICHT automatisch als gelesen –
        das steuert ausschließlich _on_mail_selected im MainFrame."""
        return self.db.get_mail(mail_id, folder_id)

    def mark_mail_read(self, mail_id: int, is_read: bool, folder_id: int = None):
        self.db.mark_mail_read(mail_id, is_read, folder_id=folder_id)
        if not folder_id:
            return
        # DB-Daten im Haupt-Thread lesen, dann Thread starten
        uid, imap_path, acc = self._resolve_mail_imap(mail_id, folder_id)
        if not uid or not imap_path:
            return
        def _w(uid=uid, path=imap_path, acc=acc, is_read=is_read):
            from core.protocol_runner import log
            try:
                with _make_imap(acc) as imap:
                    if is_read:
                        imap.mark_read(uid, path)
                    else:
                        imap.mark_unread(uid, path)
            except Exception as e:
                log("warning", f"IMAP mark_read uid={uid}: {e}")
        threading.Thread(target=_w, daemon=True).start()

    def mark_mail_flagged(self, mail_id: int, flagged: bool, folder_id: int = None):
        self.db.mark_mail_flagged(mail_id, flagged, folder_id=folder_id)
        if not folder_id:
            return
        uid, imap_path, acc = self._resolve_mail_imap(mail_id, folder_id)
        if not uid or not imap_path:
            return
        def _w(uid=uid, path=imap_path, acc=acc, flagged=flagged):
            from core.protocol_runner import log
            try:
                with _make_imap(acc) as imap:
                    if flagged:
                        imap.mark_flagged(uid, path)
                    else:
                        imap.select_folder(path)
                        imap._conn.uid("store", uid, "-FLAGS", "\\Flagged")
            except Exception as e:
                log("warning", f"IMAP mark_flagged uid={uid}: {e}")
        threading.Thread(target=_w, daemon=True).start()

    def delete_mail(self, mail_id: int, folder_id: int,
                    mailbox_id: int = None, use_trash: bool = None) -> str:
        if use_trash is None:
            use_trash = self.db.get_setting("delete_to_trash", "1") == "1"
        if use_trash and mailbox_id:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id and folder_id == trash_id:
                use_trash = False

        if use_trash and mailbox_id:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id:
                # DB-Daten im Haupt-Thread lesen
                uid, src_path, acc  = self._resolve_mail_imap(mail_id, folder_id)
                dst_path            = self._resolve_folder_imap_path(trash_id)

                self.db.move_mail(mail_id, trash_id, source_folder_id=folder_id)
                self.db.update_folder_unread(folder_id)
                self.db.update_folder_unread(trash_id)
                self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": trash_id})

                if uid and src_path and dst_path and acc:
                    def _w(uid=uid, s=src_path, d=dst_path, acc=acc):
                        from core.protocol_runner import log
                        try:
                            with _make_imap(acc) as imap:
                                imap.move_mail(uid, s, d)
                        except Exception as e:
                            log("warning", f"IMAP trash-move uid={uid}: {e}")
                    threading.Thread(target=_w, daemon=True).start()
                return "moved_to_trash"

        # Endgültig löschen
        uid, imap_path, acc = self._resolve_mail_imap(mail_id, folder_id)
        self.db.delete_mail(mail_id, folder_id)
        self.db.update_folder_unread(folder_id)
        self.addon_mgr.fire("mail_deleted", {"mail_id": mail_id})

        if uid and imap_path and acc:
            def _w(uid=uid, path=imap_path, acc=acc):
                from core.protocol_runner import log
                try:
                    with _make_imap(acc) as imap:
                        imap.delete_mail(uid, path)
                except Exception as e:
                    log("warning", f"IMAP delete uid={uid}: {e}")
            threading.Thread(target=_w, daemon=True).start()
        return "deleted"

    def move_mail(self, mail_id: int, target_folder_id: int,
                  source_folder_id: int = None):
        uid = src_path = acc = dst_path = None
        if source_folder_id:
            uid, src_path, acc = self._resolve_mail_imap(mail_id, source_folder_id)
            dst_path           = self._resolve_folder_imap_path(target_folder_id)

        self.db.move_mail(mail_id, target_folder_id, source_folder_id)
        self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": target_folder_id})

        if uid and src_path and dst_path and acc:
            def _w(uid=uid, s=src_path, d=dst_path, acc=acc):
                from core.protocol_runner import log
                try:
                    with _make_imap(acc) as imap:
                        imap.move_mail(uid, s, d)
                except Exception as e:
                    log("warning", f"IMAP move uid={uid}: {e}")
            threading.Thread(target=_w, daemon=True).start()

    def copy_mail(self, mail_id: int, target_folder_id: int,
                  source_folder_id: int = None) -> int:
        uid = src_path = acc = dst_path = None
        if source_folder_id:
            uid, src_path, acc = self._resolve_mail_imap(mail_id, source_folder_id)
            dst_path           = self._resolve_folder_imap_path(target_folder_id)

        result = self.db.copy_mail(mail_id, target_folder_id, source_folder_id)
        self.db.update_folder_unread(target_folder_id)

        if uid and src_path and dst_path and acc:
            def _w(uid=uid, s=src_path, d=dst_path, acc=acc):
                from core.protocol_runner import log
                try:
                    with _make_imap(acc) as imap:
                        imap.select_folder(s)
                        imap._conn.uid("copy", uid, f'"{d}"')
                except Exception as e:
                    log("warning", f"IMAP copy uid={uid}: {e}")
            threading.Thread(target=_w, daemon=True).start()
        return result

    def delete_folder(self, folder_id: int, mailbox_id: int,
                      use_trash: bool = None) -> str:
        if use_trash is None:
            use_trash = self.db.get_setting("delete_to_trash", "1") == "1"
        mode = self.db.get_setting("mail_storage", "sqlite_one")
        sc   = self.db._get_structure_conn()
        if use_trash:
            trash_id = self.get_trash_folder_id(mailbox_id)
            if trash_id and trash_id != folder_id:
                if mode == "sqlite_one":
                    sc.execute("UPDATE mails SET folder_id=? WHERE folder_id=?",
                               (trash_id, folder_id))
                    sc.commit()
                elif mode == "sqlite_per_account":
                    conn = self.db._mail_conn_for_folder(folder_id)
                    conn.execute("UPDATE mails SET folder_id=? WHERE folder_id=?",
                                 (trash_id, folder_id))
                    conn.commit()
                self.db.update_folder_unread(trash_id)
        if mode == "sqlite_one":
            sc.execute("DELETE FROM mails WHERE folder_id IN "
                       "(SELECT id FROM folders WHERE id=? OR parent_id=?)",
                       (folder_id, folder_id))
        elif mode == "sqlite_per_account":
            conn = self.db._mail_conn_for_folder(folder_id)
            conn.execute("DELETE FROM mails WHERE folder_id=?", (folder_id,))
            conn.commit()
        elif mode == "files":
            import shutil
            d = os.path.join(self.db.data_dir, "mailstore", str(folder_id))
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
        sc.execute("DELETE FROM folders WHERE parent_id=?", (folder_id,))
        sc.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        sc.commit()
        return "deleted"

    # ------------------------------------------------------------------ #
    #  Ordner – IMAP-Sync (alle DB-Zugriffe im Haupt-Thread)            #
    # ------------------------------------------------------------------ #

    def imap_create_folder(self, folder_id: int, parent_folder_id: int = None):
        """Legt Ordner auf IMAP-Server an. DB-Zugriff NUR hier (Haupt-Thread)."""
        sc     = self.db._get_structure_conn()
        f_row  = sc.execute(
            "SELECT name, mailbox_id FROM folders WHERE id=?", (folder_id,)
        ).fetchone()
        if not f_row:
            return
        name, mailbox_id = f_row[0], f_row[1]
        acc = self._resolve_account_for_mailbox(mailbox_id)
        if not acc:
            return
        parent_path = ""
        if parent_folder_id:
            p_row = sc.execute(
                "SELECT imap_path FROM folders WHERE id=?", (parent_folder_id,)
            ).fetchone()
            parent_path = (p_row[0] or "") if p_row else ""
        # sc wird nach Rückgabe aus dem Haupt-Thread nicht mehr benötigt
        db_path = getattr(self.db, "structure_db_path", None)

        def _w(acc=acc, name=name, parent_path=parent_path,
               fid=folder_id, db_path=db_path):
            from core.protocol_runner import log
            try:
                with _make_imap(acc) as imap:
                    sep      = imap._separator
                    new_path = f"{parent_path}{sep}{name}" if parent_path else name
                    ok       = imap.create_folder(new_path)
                    if ok:
                        # Eigene Verbindung im Worker-Thread
                        import sqlite3
                        if db_path:
                            c = sqlite3.connect(db_path)
                            c.execute("UPDATE folders SET imap_path=? WHERE id=?",
                                      (new_path, fid))
                            c.commit(); c.close()
                        log("info", f"IMAP CREATE {new_path!r} OK")
                    else:
                        log("warning", f"IMAP CREATE {new_path!r} failed")
            except Exception as e:
                log("warning", f"IMAP create_folder: {e}")
        threading.Thread(target=_w, daemon=True).start()

    def imap_rename_folder(self, folder_id: int, new_name: str):
        """Umbenennen auf Server. DB-Zugriff NUR hier (Haupt-Thread)."""
        sc    = self.db._get_structure_conn()
        f_row = sc.execute(
            "SELECT imap_path, mailbox_id FROM folders WHERE id=?", (folder_id,)
        ).fetchone()
        if not f_row or not f_row[0]:
            return
        old_path, mailbox_id = f_row[0], f_row[1]
        acc = self._resolve_account_for_mailbox(mailbox_id)
        if not acc:
            return
        # Kind-Ordner-Pfade jetzt lesen (Haupt-Thread)
        children = [
            (row[0], row[1])
            for row in sc.execute(
                "SELECT id, imap_path FROM folders WHERE imap_path LIKE ?",
                (old_path + "/%",)
            ).fetchall()
        ]
        db_path = getattr(self.db, "structure_db_path", None)

        def _w(old=old_path, new_name=new_name, fid=folder_id,
               children=children, acc=acc, db_path=db_path):
            from core.protocol_runner import log
            import sqlite3
            try:
                with _make_imap(acc) as imap:
                    sep       = imap._separator
                    parts     = old.split(sep)
                    parts[-1] = new_name
                    new_path  = sep.join(parts)
                    typ, _    = imap._conn.rename(f'"{old}"', f'"{new_path}"')
                    if typ == "OK" and db_path:
                        c = sqlite3.connect(db_path)
                        c.execute("UPDATE folders SET imap_path=? WHERE id=?",
                                  (new_path, fid))
                        for child_id, child_old in children:
                            c.execute("UPDATE folders SET imap_path=? WHERE id=?",
                                      (new_path + child_old[len(old):], child_id))
                        c.commit(); c.close()
                        log("info", f"IMAP RENAME {old!r} → {new_path!r} OK")
                    else:
                        log("warning", f"IMAP RENAME {old!r} failed (typ={typ})")
            except Exception as e:
                log("warning", f"IMAP rename_folder: {e}")
        threading.Thread(target=_w, daemon=True).start()

    def imap_delete_folder(self, folder_id: int):
        """Ordner löschen auf Server. DB-Zugriff NUR hier (Haupt-Thread)."""
        sc    = self.db._get_structure_conn()
        f_row = sc.execute(
            "SELECT imap_path, mailbox_id FROM folders WHERE id=?", (folder_id,)
        ).fetchone()
        if not f_row or not f_row[0]:
            return
        imap_path, mailbox_id = f_row[0], f_row[1]
        acc = self._resolve_account_for_mailbox(mailbox_id)
        if not acc:
            return

        def _w(path=imap_path, acc=acc):
            from core.protocol_runner import log
            try:
                with _make_imap(acc) as imap:
                    imap.delete_folder(path)
                    log("info", f"IMAP DELETE {path!r} OK")
            except Exception as e:
                log("warning", f"IMAP delete_folder: {e}")
        threading.Thread(target=_w, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Private Resolver – NUR im Haupt-Thread aufrufen                  #
    # ------------------------------------------------------------------ #

    def _resolve_mail_imap(self, mail_id: int,
                           folder_id: int) -> "tuple[str|None, str|None, dict|None]":
        """
        Gibt (uid, imap_path, acc_dict) zurück.
        Alle DB-Zugriffe hier – Ergebnis kann sicher an Threads übergeben werden.
        Gibt (None, None, None) wenn kein IMAP-Konto oder keine UID.
        """
        try:
            mail = self.db.get_mail(mail_id, folder_id)
            if not mail:
                return None, None, None
            uid = str(dict(mail).get("uid") or "") or None
            if not uid:
                return None, None, None
            imap_path, acc = self._resolve_folder_imap(folder_id)
            return uid, imap_path, acc
        except Exception:
            return None, None, None

    def _resolve_folder_imap(self, folder_id: int) -> "tuple[str|None, dict|None]":
        """
        Gibt (imap_path, acc_dict) für einen Ordner zurück.
        NUR im Haupt-Thread aufrufen.
        """
        try:
            sc  = self.db._get_structure_conn()
            row = sc.execute(
                "SELECT f.imap_path, mb.account_id "
                "FROM folders f JOIN mailboxes mb ON f.mailbox_id=mb.id "
                "WHERE f.id=?", (folder_id,)
            ).fetchone()
            if not row or not row[0]:
                return None, None
            acc = self.db.get_account(row[1])
            if not acc:
                return None, None
            acc = dict(acc)
            if acc.get("protocol", "LOCAL").upper() != "IMAP":
                return None, None
            return row[0], acc
        except Exception:
            return None, None

    def _resolve_folder_imap_path(self, folder_id: int) -> "str | None":
        """Gibt nur den imap_path zurück. NUR im Haupt-Thread aufrufen."""
        try:
            sc  = self.db._get_structure_conn()
            row = sc.execute(
                "SELECT imap_path FROM folders WHERE id=?", (folder_id,)
            ).fetchone()
            return row[0] if row and row[0] else None
        except Exception:
            return None

    def _resolve_account_for_mailbox(self, mailbox_id: int) -> "dict | None":
        """Gibt acc_dict für ein Postfach zurück. NUR im Haupt-Thread aufrufen."""
        try:
            sc     = self.db._get_structure_conn()
            mb_row = sc.execute(
                "SELECT account_id FROM mailboxes WHERE id=?", (mailbox_id,)
            ).fetchone()
            if not mb_row:
                return None
            acc = self.db.get_account(mb_row[0])
            if not acc:
                return None
            acc = dict(acc)
            if acc.get("protocol", "LOCAL").upper() != "IMAP":
                return None
            return acc
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Datei-Export/Import                                               #
    # ------------------------------------------------------------------ #

    def save_mail_as_email(self, mail_id: int, path: str,
                           folder_id: int = None) -> bool:
        mail = self.db.get_mail(mail_id, folder_id)
        if not mail: return False
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dict(mail), f, ensure_ascii=False, indent=2, default=str)
            return True
        except OSError: return False

    def save_mail_as_eml(self, mail_id: int, path: str,
                         folder_id: int = None) -> bool:
        mail = self.db.get_mail(mail_id, folder_id)
        if not mail: return False
        try:
            def h(n, v): return f"{n}: {str(v or '').replace(chr(10),' ')}\n"
            sn     = str(mail["sender_name"] or "")
            se     = str(mail["sender"] or "")
            from_f = f"{sn} <{se}>" if sn else se
            hdr    = h("From", from_f)
            hdr   += h("To",       mail["recipients"])
            if mail["cc"]:  hdr += h("Cc", mail["cc"])
            hdr   += h("Subject",  mail["subject"])
            hdr   += h("Date",     mail["date"])
            if mail["message_id"]: hdr += h("Message-ID", mail["message_id"])
            hdr   += "MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n\n"
            with open(path, "w", encoding="utf-8") as f:
                f.write(hdr + str(mail["body_text"] or mail["body_html"] or ""))
            return True
        except OSError: return False

    def save_mail_as_txt(self, mail_id: int, path: str,
                         folder_id: int = None) -> bool:
        mail = self.db.get_mail(mail_id, folder_id)
        if not mail: return False
        try:
            lines = [
                f"Von:     {mail['sender_name']} <{mail['sender']}>",
                f"An:      {mail['recipients']}",
                f"Betreff: {mail['subject']}",
                f"Datum:   {mail['date']}", "",
                str(mail["body_text"] or ""),
            ]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
        except OSError: return False

    def open_mail_file(self, path: str) -> Optional[dict]:
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".email":
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            elif ext == ".eml":
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return self._parse_eml_string(content, path)
            elif ext == ".txt":
                with open(path, encoding="utf-8", errors="replace") as f:
                    return {"subject": os.path.basename(path),
                            "body_text": f.read(), "sender": "", "recipients": ""}
        except (OSError, Exception):
            pass
        return None

    @staticmethod
    def _parse_eml_string(content: str, path: str = "") -> dict:
        sep        = content.find("\n\n")
        header_txt = content[:sep] if sep != -1 else ""
        body       = content[sep+2:] if sep != -1 else content
        headers: dict = {}
        for line in header_txt.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()
        return {
            "subject":    headers.get("subject", os.path.basename(path)),
            "sender":     headers.get("from", ""),
            "sender_name": "",
            "recipients": headers.get("to", ""),
            "cc":         headers.get("cc", ""),
            "date":       headers.get("date", ""),
            "message_id": headers.get("message-id", ""),
            "body_text":  body,
            "body_html":  "",
            "is_read":    1,
            "is_flagged": 0,
            "has_attach": 0,
        }

    # ------------------------------------------------------------------ #
    #  Konten + Einstellungen                                            #
    # ------------------------------------------------------------------ #

    def get_accounts(self): return self.db.get_accounts()
    def get_account(self, aid): return self.db.get_account(aid)
    def save_account(self, data): return self.db.save_account(data)
    def delete_account(self, aid): self.db.delete_account(aid)
    def get_setting(self, key, default=""): return self.db.get_setting(key, default)
    def set_setting(self, key, value): self.db.set_setting(key, value)

    def is_first_run(self) -> bool:
        return self.db.is_first_run()

    def search_mails(self, query: str, field: str = "all",
                     folder_id: int = None,
                     date_from: str = None, date_to: str = None) -> list:
        return self.db.search_mails(query, field, folder_id, date_from, date_to)

    # ------------------------------------------------------------------ #
    #  Protokolle                                                         #
    # ------------------------------------------------------------------ #

    def fetch_new_mails(self, account_id: int = None, progress_cb=None) -> int:
        accounts = [self.db.get_account(account_id)] if account_id else self.db.get_accounts()
        total    = 0
        for acc in accounts:
            if not acc: continue
            acc   = dict(acc)
            proto = acc.get("protocol", "IMAP").upper()
            if proto == "LOCAL": continue
            if not acc.get("in_host"): continue
            if progress_cb:
                progress_cb(f"Verbinde mit {acc['in_host']}…")
            try:
                if proto == "POP3":
                    total += self._fetch_pop3(acc, progress_cb)
                else:
                    total += self._fetch_imap(acc, progress_cb)
            except Exception as e:
                if progress_cb:
                    progress_cb(f"Fehler ({acc['name']}): {e}")
        return total

    def send_mail(self, account_id: int, mail_data: dict):
        raise NotImplementedError("SMTP noch nicht implementiert.")

    def _fetch_imap(self, acc: dict, progress_cb=None) -> int:
        from protocols.imap_sync import IMAPSync
        from core.protocol_runner import log
        log("info", f"Fetch IMAP: account={acc.get('name')} host={acc.get('in_host')}")

        syncer = IMAPSync(
            host=acc["in_host"], port=int(acc["in_port"] or 993),
            username=acc["username"] or acc["email"],
            password=acc["password"] or "",
            use_ssl=bool(acc.get("in_ssl", 1)),
        )
        count = 0
        with syncer:
            if progress_cb:
                progress_cb("Ordnerstruktur wird abgerufen…", 0, 0)

            server_folders = syncer.list_folders()
            folder_map     = self._sync_imap_folders(acc, server_folders)

            FOLDER_ORDER = ["inbox","sent","drafts","outbox","trash","spam","archive","custom"]
            def _fkey(fi):
                ft = self._guess_folder_type(fi["name"])
                return FOLDER_ORDER.index(ft) if ft in FOLDER_ORDER else len(FOLDER_ORDER)
            sorted_folders = sorted(server_folders, key=_fkey)

            folder_tasks: list[tuple] = []
            for fi in sorted_folders:
                imap_path = fi["path"]
                folder_id = folder_map.get(imap_path)
                if not folder_id:
                    continue
                last_uid = self._get_max_uid(folder_id)
                folder_tasks.append((imap_path, folder_id, last_uid,
                                     fi["name"].split(".")[-1]))

            total_est = 0
            fetched   = 0
            for imap_path, folder_id, last_uid, folder_name in folder_tasks:
                if progress_cb:
                    progress_cb(f"Prüfe {folder_name}…", -1, 0)
                new_in_folder = []
                try:
                    for uid_str, raw, flags_raw in syncer.new_mails_since(imap_path, last_uid):
                        new_in_folder.append((uid_str, raw, flags_raw))
                except Exception as e:
                    log("error", f"IMAP new_mails_since {imap_path!r}: {e}")
                    continue

                total_est += len(new_in_folder)
                inserted_in_folder = 0
                for uid_str, raw, flags_raw in new_in_folder:
                    try:
                        m = IMAPSync.parse_mail(uid_str, raw, flags_raw)
                        m["folder_id"] = folder_id
                        self.db.insert_mail(folder_id, m)
                        log("debug", f"IMAP stored UID={uid_str} subject={str(m.get('subject',''))[:50]!r}")
                        count += 1
                        inserted_in_folder += 1
                    except Exception as e:
                        log("error", f"IMAP insert UID={uid_str}: {e}")
                    fetched += 1
                    if progress_cb:
                        pct = int(fetched / max(total_est, 1) * 100)
                        progress_cb(f"{fetched}/{total_est} – {folder_name}…", pct, total_est)
                if inserted_in_folder:
                    self.db.update_folder_unread(folder_id)

        if progress_cb and count == 0:
            progress_cb("Keine neuen Mails.", 100, 0)
        return count

    def _fetch_pop3(self, acc: dict, progress_cb=None) -> int:
        """
        POP3-Fetch: Kopier-Semantik – Mails werden NUR heruntergeladen,
        NIE vom Server gelöscht (kein DELE). UIDs werden in der DB
        gespeichert um bereits bekannte Mails beim nächsten Abruf zu
        überspringen (identisches Verhalten wie Thunderbird im Kopiermodus).
        """
        from protocols.pop3_smtp_handler import POP3Handler
        from core.protocol_runner import log
        log("info", f"Fetch POP3: account={acc.get('name')} host={acc.get('in_host')}")

        # Sicherstellen dass Standardordner vorhanden sind
        # (falls Konto vor diesem Fix angelegt wurde, fehlen sie noch)
        self._ensure_pop3_folders(acc)

        inbox_id = self._get_inbox_folder_id(acc["id"])
        if not inbox_id:
            log("error", f"POP3 no inbox folder for account {acc.get('name')!r}")
            return 0

        known  = self._get_known_uids(inbox_id)
        log("info", f"POP3 known UIDs in inbox: {len(known)}")

        handler = POP3Handler(
            host=acc["in_host"], port=int(acc["in_port"] or 995),
            username=acc["username"] or acc["email"],
            password=acc["password"] or "",
            use_ssl=bool(acc.get("in_ssl", 1)),
        )

        count = 0
        with handler:
            def _prog(current, total, subject=""):
                if progress_cb:
                    pct = int(current / max(total, 1) * 100)
                    progress_cb(
                        f"POP3 {current}/{total}: {str(subject)[:40]}…",
                        pct, total
                    )

            new_mails = handler.fetch_new_mails(known_uids=known,
                                                progress_cb=_prog)
            for m in new_mails:
                try:
                    m["folder_id"] = inbox_id
                    self.db.insert_mail(inbox_id, m)
                    log("debug", f"POP3 stored uid={m.get('uid','?')!r} "
                                 f"subject={str(m.get('subject',''))[:50]!r}")
                    count += 1
                except Exception as e:
                    log("error", f"POP3 insert: {e}")

        if count:
            self.db.update_folder_unread(inbox_id)
        if progress_cb and count == 0:
            progress_cb("Keine neuen Mails (POP3).", 100, 0)
        return count

    def _ensure_pop3_folders(self, acc: dict):
        """
        Legt die Standardordner für ein POP3-Konto an falls sie fehlen.
        Idempotent – kann mehrfach aufgerufen werden.
        Nötig für Konten die vor dem Fix angelegt wurden.
        """
        sc     = self.db._get_structure_conn()
        mb_row = sc.execute(
            "SELECT id FROM mailboxes WHERE account_id=?", (acc["id"],)
        ).fetchone()
        if not mb_row:
            return
        mb_id = mb_row[0]

        existing_types = {
            row[0] for row in sc.execute(
                "SELECT folder_type FROM folders WHERE mailbox_id=?", (mb_id,)
            ).fetchall()
        }

        defaults = [
            ("Posteingang", "inbox"),
            ("Gesendet",    "sent"),
            ("Entwürfe",    "drafts"),
            ("Papierkorb",  "trash"),
            ("Spam",        "spam"),
            ("Archiv",      "archive"),
        ]
        added = False
        for fname, ftype in defaults:
            if ftype not in existing_types:
                sc.execute(
                    "INSERT INTO folders (mailbox_id,parent_id,name,folder_type,unread) "
                    "VALUES (?,NULL,?,?,0)",
                    (mb_id, fname, ftype)
                )
                added = True
        if added:
            sc.commit()

    def send_outbox(self, progress_cb=None) -> int:
        from protocols.pop3_smtp_handler import SMTPHandler
        from protocols.imap_handler import IMAPHandler
        from core.protocol_runner import log
        log("info", "send_outbox: start")

        outbox_id = self._get_outbox_folder_id()
        if not outbox_id:
            return 0
        mails = self.db.get_mails(outbox_id)
        if not mails:
            return 0

        sent_count = 0
        for mail in mails:
            m   = dict(mail)
            acc = self._find_account_by_email(m.get("sender", ""))
            if not acc:
                continue
            proto = acc.get("protocol", "IMAP").upper()
            if proto == "LOCAL":
                continue
            try:
                to_list = [a.strip() for a in (m.get("recipients") or "").split(",") if a.strip()]
                cc_list = [a.strip() for a in (m.get("cc") or "").split(",") if a.strip()]
                smtp = SMTPHandler(
                    host=acc["out_host"], port=int(acc["out_port"] or 587),
                    username=acc["username"] or acc["email"],
                    password=acc["password"] or "",
                    use_ssl=bool(acc.get("out_ssl", 1)),
                )
                if progress_cb:
                    progress_cb(f"Sende an {m.get('recipients', '')}…")
                raw_bytes = smtp.send(
                    from_addr=m.get("sender", acc["email"]),
                    to_addrs=to_list,
                    subject=m.get("subject", ""),
                    body_text=m.get("body_text", ""),
                    body_html=m.get("body_html", ""),
                    cc=cc_list,
                )
                sent_id = self._get_sent_folder_id(acc["id"])
                if sent_id:
                    self.db.move_mail(m["id"], sent_id, source_folder_id=outbox_id)
                    self.db.update_folder_unread(outbox_id)
                    if proto == "IMAP" and acc.get("in_host"):
                        try:
                            imap = IMAPHandler(
                                host=acc["in_host"], port=int(acc["in_port"] or 993),
                                username=acc["username"] or acc["email"],
                                password=acc["password"] or "",
                                use_ssl=bool(acc.get("in_ssl", 1)),
                            )
                            with imap:
                                for f in imap.list_folders():
                                    if f.get("name", "").lower() in ("sent", "gesendet", "sent items"):
                                        imap.append_mail(f["path"], raw_bytes, "\\Seen")
                                        break
                        except Exception:
                            pass
                sent_count += 1
            except RuntimeError as e:
                if progress_cb:
                    progress_cb(f"Fehler: {e}")
        return sent_count

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden Protokolle                                           #
    # ------------------------------------------------------------------ #

    def _sync_imap_folders(self, acc: dict, server_folders: list) -> dict:
        from core.i18n import tr
        sc = self.db._get_structure_conn()
        mb_row = sc.execute(
            "SELECT id FROM mailboxes WHERE account_id=?", (acc["id"],)
        ).fetchone()
        if not mb_row:
            return {}
        mb_id = mb_row[0]

        LOCALIZED = {
            "inbox":   tr("folder_inbox")   if tr("folder_inbox")   != "folder_inbox"   else "Posteingang",
            "sent":    tr("folder_sent")    if tr("folder_sent")    != "folder_sent"    else "Gesendet",
            "drafts":  tr("folder_drafts")  if tr("folder_drafts")  != "folder_drafts"  else "Entwürfe",
            "trash":   tr("folder_trash")   if tr("folder_trash")   != "folder_trash"   else "Papierkorb",
            "spam":    tr("folder_spam")    if tr("folder_spam")    != "folder_spam"    else "Spam",
            "archive": tr("folder_archive") if tr("folder_archive") != "folder_archive" else "Archiv",
        }

        existing_by_imap = {}
        existing_by_type = {}
        for r in sc.execute(
            "SELECT id, imap_path, folder_type FROM folders WHERE mailbox_id=?", (mb_id,)
        ).fetchall():
            r = dict(r)
            if r["imap_path"]:
                existing_by_imap[r["imap_path"]] = r["id"]
            elif r["folder_type"] and r["folder_type"] not in ("outbox",):
                existing_by_type[r["folder_type"]] = r["id"]

        sorted_folders = sorted(server_folders, key=lambda f: f.get("level", 0))
        folder_map = {}
        for sf in sorted_folders:
            path       = sf["path"]
            ftype      = self._guess_folder_type(sf["name"])
            local_name = LOCALIZED.get(ftype, sf["name"])
            parent_path = sf.get("parent", "")
            parent_id   = folder_map.get(parent_path) if parent_path else None

            if path in existing_by_imap:
                fid = existing_by_imap[path]
                if parent_id is not None:
                    sc.execute(
                        "UPDATE folders SET parent_id=? WHERE id=? AND parent_id IS NULL",
                        (parent_id, fid)
                    )
                folder_map[path] = fid
            elif ftype in existing_by_type and parent_id is None:
                fid = existing_by_type.pop(ftype)
                sc.execute("UPDATE folders SET imap_path=?, name=? WHERE id=?",
                           (path, local_name, fid))
                folder_map[path] = fid
                existing_by_imap[path] = fid
            else:
                sc.execute(
                    "INSERT INTO folders "
                    "(mailbox_id, parent_id, name, folder_type, imap_path, unread) "
                    "VALUES (?, ?, ?, ?, ?, 0)",
                    (mb_id, parent_id, local_name, ftype, path)
                )
                fid = sc.execute("SELECT last_insert_rowid()").fetchone()[0]
                folder_map[path] = fid
                existing_by_imap[path] = fid

        sc.commit()
        return folder_map

    @staticmethod
    def _guess_folder_type(name: str) -> str:
        n = name.lower()
        if n in ("inbox", "posteingang"):                               return "inbox"
        if n in ("sent", "gesendet", "sent items", "sent mail"):        return "sent"
        if n in ("drafts", "entwürfe", "draft"):                        return "drafts"
        if n in ("trash", "papierkorb", "deleted", "deleted items", "bin"): return "trash"
        if n in ("spam", "junk", "junk mail", "bulk mail"):             return "spam"
        if n in ("archive", "archiv", "archives"):                      return "archive"
        if n in ("outbox", "postausgang"):                              return "outbox"
        return "custom"

    def _get_max_uid(self, folder_id: int) -> int:
        try:
            mode = self.db.get_setting("mail_storage", "sqlite_one")
            sql  = "SELECT MAX(CAST(uid AS INTEGER)) FROM mails WHERE folder_id=? AND uid IS NOT NULL AND uid != ''"
            if mode == "sqlite_one":
                row = self.db._get_structure_conn().execute(sql, (folder_id,)).fetchone()
            elif mode == "sqlite_per_account":
                row = self.db._mail_conn_for_folder(folder_id).execute(sql, (folder_id,)).fetchone()
            else:
                mails = self.db.get_mails(folder_id)
                uids  = [int(dict(m).get("uid", 0) or 0) for m in mails]
                return max(uids) if uids else 0
            return int(row[0]) if row and row[0] else 0
        except Exception:
            return 0

    def _get_known_uids(self, folder_id: int) -> set:
        try:
            mode = self.db.get_setting("mail_storage", "sqlite_one")
            sql  = "SELECT uid FROM mails WHERE folder_id=? AND uid IS NOT NULL AND uid != ''"
            if mode == "sqlite_one":
                rows = self.db._get_structure_conn().execute(sql, (folder_id,)).fetchall()
            elif mode == "sqlite_per_account":
                rows = self.db._mail_conn_for_folder(folder_id).execute(sql, (folder_id,)).fetchall()
            else:
                mails = self.db.get_mails(folder_id)
                return {str(dict(m).get("uid", "")) for m in mails if dict(m).get("uid")}
            return {str(r[0]) for r in rows}
        except Exception:
            return set()

    def _get_inbox_folder_id(self, account_id: int) -> "int | None":
        sc  = self.db._get_structure_conn()
        row = sc.execute(
            "SELECT f.id FROM folders f JOIN mailboxes mb ON f.mailbox_id=mb.id "
            "WHERE mb.account_id=? AND f.folder_type='inbox'", (account_id,)
        ).fetchone()
        return row[0] if row else None

    def _get_sent_folder_id(self, account_id: int) -> "int | None":
        sc  = self.db._get_structure_conn()
        row = sc.execute(
            "SELECT f.id FROM folders f JOIN mailboxes mb ON f.mailbox_id=mb.id "
            "WHERE mb.account_id=? AND f.folder_type='sent'", (account_id,)
        ).fetchone()
        return row[0] if row else None

    def _get_outbox_folder_id(self) -> "int | None":
        return self._get_local_folder_by_type("outbox")

    def _get_local_folder_by_type(self, folder_type: str) -> "int | None":
        acc_conn  = self.db._get_accounts_conn()
        local_ids = [r[0] for r in acc_conn.execute(
            "SELECT id FROM accounts WHERE protocol='LOCAL'"
        ).fetchall()]
        if not local_ids:
            return None
        sc  = self.db._get_structure_conn()
        ph  = ",".join("?" for _ in local_ids)
        row = sc.execute(
            f"SELECT f.id FROM folders f "
            f"JOIN mailboxes mb ON f.mailbox_id=mb.id "
            f"WHERE mb.account_id IN ({ph}) AND f.folder_type=?",
            local_ids + [folder_type]
        ).fetchone()
        return row[0] if row else None

    def _find_account_by_email(self, email_addr: str) -> "dict | None":
        for acc in self.db.get_accounts():
            a = dict(acc)
            if a.get("email", "").lower() in email_addr.lower():
                return a
        return None

    def create_welcome_mail(self, inbox_folder_id: int):
        from core.i18n import tr
        from datetime import datetime
        self.db.insert_mail(inbox_folder_id, {
            "subject":     tr("welcome_subject"),
            "sender":      tr("welcome_sender"),
            "sender_name": tr("welcome_sender_name"),
            "recipients":  "",
            "date":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "body_text":   tr("welcome_body"),
            "body_html":   "",
            "is_read":     0,
            "is_flagged":  0,
            "has_attach":  0,
            "size":        len(tr("welcome_body")),
        })
        self.db.update_folder_unread(inbox_folder_id)


# ------------------------------------------------------------------ #
#  Modul-Hilfsfunktion (kein self.db-Zugriff – thread-sicher)        #
# ------------------------------------------------------------------ #

def _make_imap(acc: dict):
    """Erzeugt IMAPHandler aus acc-Dict. Kein DB-Zugriff – thread-sicher."""
    from protocols.imap_handler import IMAPHandler
    return IMAPHandler(
        host=acc["in_host"],
        port=int(acc.get("in_port") or 993),
        username=acc.get("username") or acc.get("email", ""),
        password=acc.get("password") or "",
        use_ssl=bool(acc.get("in_ssl", 1)),
    )
