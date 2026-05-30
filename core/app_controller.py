"""
AppController – MVC-Controller-Schicht
"""

from __future__ import annotations
import os, json
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
        mail = self.db.get_mail(mail_id, folder_id)
        if mail and not int(mail["is_read"] or 0):
            fid = int(mail["folder_id"] or folder_id or 0)
            self.db.mark_mail_read(mail_id, True, folder_id=fid)
            if fid:
                self.db.update_folder_unread(fid)
            self.addon_mgr.fire("mail_read", {"mail_id": mail_id})
        return mail

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
                self.db.move_mail(mail_id, trash_id, source_folder_id=folder_id)
                self.db.update_folder_unread(folder_id)
                self.db.update_folder_unread(trash_id)
                self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": trash_id})
                return "moved_to_trash"
        self.db.delete_mail(mail_id, folder_id)
        self.db.update_folder_unread(folder_id)
        self.addon_mgr.fire("mail_deleted", {"mail_id": mail_id})
        return "deleted"

    def move_mail(self, mail_id: int, target_folder_id: int, source_folder_id: int = None):
        self.db.move_mail(mail_id, target_folder_id, source_folder_id)
        self.addon_mgr.fire("mail_moved", {"mail_id": mail_id, "folder_id": target_folder_id})

    def mark_mail_flagged(self, mail_id: int, flagged: bool, folder_id: int = None):
        self.db.mark_mail_flagged(mail_id, flagged, folder_id=folder_id)

    def mark_mail_read(self, mail_id: int, is_read: bool, folder_id: int = None):
        self.db.mark_mail_read(mail_id, is_read, folder_id=folder_id)

    def delete_folder(self, folder_id: int, mailbox_id: int, use_trash: bool = None) -> str:
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
        """Speichert als RFC-2822-.eml-Datei."""
        mail = self.db.get_mail(mail_id, folder_id)
        if not mail: return False
        try:
            def h(n, v): return f"{n}: {str(v or '').replace(chr(10),' ')}\n"
            sn = str(mail["sender_name"] or "")
            se = str(mail["sender"] or "")
            from_f = f"{sn} <{se}>" if sn else se
            hdr  = h("From", from_f)
            hdr += h("To",      mail["recipients"])
            if mail["cc"]:  hdr += h("Cc", mail["cc"])
            hdr += h("Subject", mail["subject"])
            hdr += h("Date",    mail["date"])
            if mail["message_id"]: hdr += h("Message-ID", mail["message_id"])
            hdr += "MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n\n"
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
        """Öffnet .email (JSON), .eml oder .txt und gibt Mail-Dict zurück."""
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
        """Parst RFC-2822-EML-Inhalt in ein Mail-Dict."""
        sep  = content.find("\n\n")
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
            "sender_name":"",
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

    def fetch_new_mails(self, account_id: int):
        raise NotImplementedError("IMAP/POP3 noch nicht implementiert.")
    def send_mail(self, account_id: int, mail_data: dict):
        raise NotImplementedError("SMTP noch nicht implementiert.")

    def is_first_run(self) -> bool:
        return self.db.is_first_run()

    def search_mails(self, query: str, field: str = "all",
                     folder_id: int = None,
                     date_from: str = None, date_to: str = None) -> list:
        return self.db.search_mails(query, field, folder_id, date_from, date_to)

    def copy_mail(self, mail_id: int, target_folder_id: int,
                  source_folder_id: int = None) -> int:
        result = self.db.copy_mail(mail_id, target_folder_id, source_folder_id)
        self.db.update_folder_unread(target_folder_id)
        return result

    # ------------------------------------------------------------------ #
    #  Protokolle                                                         #
    # ------------------------------------------------------------------ #

    def fetch_new_mails(self, account_id: int = None, progress_cb=None) -> int:
        """
        Ruft neue Mails per IMAP oder POP3 ab.
        Gibt die Anzahl der neu abgerufenen Mails zurück.
        Raises RuntimeError bei Verbindungsfehlern.
        """
        accounts = [self.db.get_account(account_id)] if account_id else self.db.get_accounts()
        total    = 0

        for acc in accounts:
            if not acc: continue
            acc = dict(acc)
            proto = acc.get("protocol", "IMAP").upper()
            if proto == "LOCAL": continue
            if not acc.get("in_host"): continue

            if progress_cb:
                progress_cb(f"Verbinde mit {acc['in_host']}…")

            try:
                if proto == "POP3":
                    total += self._fetch_pop3(acc, progress_cb)
                else:  # IMAP (Standard)
                    total += self._fetch_imap(acc, progress_cb)
            except Exception as e:
                if progress_cb:
                    progress_cb(f"Fehler ({acc['name']}): {e}")

        return total

    def _fetch_imap(self, acc: dict, progress_cb=None) -> int:
        """
        IMAP-Synchronisierung mit UID-Bereichs-Technik (RFC 3501).
        SEARCH UID {last_uid}:* → nur Mails mit UID > last_uid sind neu.
        Skaliert bei großen Postfächern ohne vollständigen Index-Scan.
        """
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

            # Phase 1: Pro Ordner die höchste bekannte UID ermitteln
            # (kein vollständiger UID-Scan – nur MAX(uid) aus DB)
            folder_tasks: list[tuple] = []
            for fi in sorted_folders:
                imap_path = fi["path"]
                folder_id = folder_map.get(imap_path)
                if not folder_id:
                    continue
                last_uid = self._get_max_uid(folder_id)
                folder_tasks.append((imap_path, folder_id, last_uid,
                                     fi["name"].split(".")[-1]))

            # Phase 2: Neue Mails per UID-Bereich laden
            # Unbekannt wie viele kommen → Pulse-Fortschritt bis wir total kennen
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
                        progress_cb(f"{fetched}/{total_est} – {folder_name}…",
                                    pct, total_est)

                if inserted_in_folder:
                    self.db.update_folder_unread(folder_id)

        if progress_cb and count == 0:
            progress_cb("Keine neuen Mails.", 100, 0)
        return count

    def _fetch_pop3(self, acc: dict, progress_cb=None) -> int:
        from protocols.pop3_smtp_handler import POP3Handler

        handler = POP3Handler(
            host=acc["in_host"], port=int(acc["in_port"] or 995),
            username=acc["username"] or acc["email"],
            password=acc["password"] or "",
            use_ssl=bool(acc.get("in_ssl", 1)),
        )

        # Posteingang des Kontos finden
        inbox_id = self._get_inbox_folder_id(acc["id"])
        if not inbox_id:
            return 0

        known = self._get_known_uids(inbox_id)
        count = 0
        with handler:
            if progress_cb:
                progress_cb(f"Lade Mails per POP3…")
            new_mails = handler.fetch_new_mails(known_uids=known)
            for m in new_mails:
                m["folder_id"] = inbox_id
                self.db.insert_mail(inbox_id, m)
                count += 1
        if count:
            self.db.update_folder_unread(inbox_id)
        return count

    def send_outbox(self, progress_cb=None) -> int:
        """
        Sendet alle Mails aus dem Postausgang (Lokale Ordner → Postausgang).
        Erfolgreich gesendete Mails werden in Gesendet des jeweiligen Kontos verschoben.
        Gibt Anzahl gesendeter Mails zurück.
        """
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
            m = dict(mail)
            # Konto aus der From-Adresse ermitteln
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

                # In Gesendet-Ordner verschieben
                sent_id = self._get_sent_folder_id(acc["id"])
                if sent_id:
                    self.db.move_mail(m["id"], sent_id, source_folder_id=outbox_id)
                    self.db.update_folder_unread(outbox_id)

                    # Optional: auf IMAP-Server in Gesendet ablegen
                    if proto == "IMAP" and acc.get("in_host"):
                        try:
                            imap = IMAPHandler(
                                host=acc["in_host"], port=int(acc["in_port"] or 993),
                                username=acc["username"] or acc["email"],
                                password=acc["password"] or "",
                                use_ssl=bool(acc.get("in_ssl", 1)),
                            )
                            with imap:
                                # Gesendet-Pfad auf dem IMAP-Server suchen
                                for f in imap.list_folders():
                                    if f.get("name", "").lower() in ("sent", "gesendet", "sent items"):
                                        imap.append_mail(f["path"], raw_bytes, "\\Seen")
                                        break
                        except Exception:
                            pass  # IMAP-Append optional

                sent_count += 1

            except RuntimeError as e:
                if progress_cb:
                    progress_cb(f"Fehler: {e}")

        return sent_count

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden Protokolle                                           #
    # ------------------------------------------------------------------ #

    def _sync_imap_folders(self, acc: dict, server_folders: list) -> dict:
        """
        Synchronisiert IMAP-Server-Ordner (Thunderbird-Stil):
        - Platzhalter (lokal vorher angelegt, kein imap_path) werden mit dem
          passenden Server-Ordner zusammengeführt (per folder_type).
        - Ordnernamen werden lokalisiert angezeigt.
        - Keine Duplikate.
        """
        from core.i18n import tr
        sc = self.db._get_structure_conn()
        mb_row = sc.execute(
            "SELECT id FROM mailboxes WHERE account_id=?", (acc["id"],)
        ).fetchone()
        if not mb_row:
            return {}
        mb_id = mb_row[0]

        # Lokalisierte Ordnernamen (Thunderbird-Konvention)
        LOCALIZED = {
            "inbox":   tr("folder_inbox")   if tr("folder_inbox")   != "folder_inbox"   else "Posteingang",
            "sent":    tr("folder_sent")    if tr("folder_sent")    != "folder_sent"    else "Gesendet",
            "drafts":  tr("folder_drafts")  if tr("folder_drafts")  != "folder_drafts"  else "Entwürfe",
            "trash":   tr("folder_trash")   if tr("folder_trash")   != "folder_trash"   else "Papierkorb",
            "spam":    tr("folder_spam")    if tr("folder_spam")    != "folder_spam"    else "Spam",
            "archive": tr("folder_archive") if tr("folder_archive") != "folder_archive" else "Archiv",
        }

        # Alle vorhandenen Ordner dieses Postfachs
        existing_by_imap = {}  # imap_path → folder_id
        existing_by_type = {}  # folder_type → folder_id (Platzhalter ohne imap_path)
        for r in sc.execute(
            "SELECT id, imap_path, folder_type FROM folders WHERE mailbox_id=?",
            (mb_id,)
        ).fetchall():
            r = dict(r)
            if r["imap_path"]:
                existing_by_imap[r["imap_path"]] = r["id"]
            elif r["folder_type"] and r["folder_type"] not in ("outbox",):
                existing_by_type[r["folder_type"]] = r["id"]

        folder_map = {}
        for sf in server_folders:
            path  = sf["path"]
            ftype = self._guess_folder_type(sf["name"])
            local_name = LOCALIZED.get(ftype, sf["name"])

            if path in existing_by_imap:
                # Bereits synchronisiert
                folder_map[path] = existing_by_imap[path]
            elif ftype in existing_by_type:
                # Platzhalter zusammenführen: imap_path + lokalisierten Namen setzen
                fid = existing_by_type.pop(ftype)
                sc.execute(
                    "UPDATE folders SET imap_path=?, name=? WHERE id=?",
                    (path, local_name, fid)
                )
                folder_map[path] = fid
                existing_by_imap[path] = fid
            else:
                # Neuen Ordner anlegen
                sc.execute(
                    "INSERT INTO folders "
                    "(mailbox_id, parent_id, name, folder_type, imap_path, unread) "
                    "VALUES (?, NULL, ?, ?, ?, 0)",
                    (mb_id, local_name, ftype, path)
                )
                fid = sc.execute("SELECT last_insert_rowid()").fetchone()[0]
                folder_map[path] = fid
                existing_by_imap[path] = fid

        sc.commit()
        return folder_map

    @staticmethod
    def _guess_folder_type(name: str) -> str:
        n = name.lower()
        if n in ("inbox", "posteingang"):                              return "inbox"
        if n in ("sent", "gesendet", "sent items", "sent mail"):       return "sent"
        if n in ("drafts", "entwürfe", "draft"):                       return "drafts"
        if n in ("trash", "papierkorb", "deleted", "deleted items", "bin"): return "trash"
        if n in ("spam", "junk", "junk mail", "bulk mail"):            return "spam"
        if n in ("archive", "archiv", "archives"):                     return "archive"
        if n in ("outbox", "postausgang"):                             return "outbox"
        return "custom"

    def _get_max_uid(self, folder_id: int) -> int:
        """
        Gibt die höchste bekannte UID eines Ordners zurück.
        Für SEARCH UID {max+1}:* – deutlich schneller als alle UIDs laden.
        Gibt 0 zurück wenn keine Mails vorhanden (→ alle laden).
        """
        try:
            mode = self.db.get_setting("mail_storage", "sqlite_one")
            sql  = "SELECT MAX(CAST(uid AS INTEGER)) FROM mails WHERE folder_id=? AND uid IS NOT NULL AND uid != ''"
            if mode == "sqlite_one":
                row = self.db._get_structure_conn().execute(sql, (folder_id,)).fetchone()
            elif mode == "sqlite_per_account":
                conn = self.db._mail_conn_for_folder(folder_id)
                row  = conn.execute(sql, (folder_id,)).fetchone()
            else:
                # File-Backend: max UID aus JSON-Metadaten
                mails = self.db.get_mails(folder_id)
                uids  = [int(dict(m).get("uid", 0) or 0) for m in mails]
                return max(uids) if uids else 0
            return int(row[0]) if row and row[0] else 0
        except Exception:
            return 0

    def _get_known_uids(self, folder_id: int) -> set:
        """Kompatibilitäts-Wrapper – nutzt _get_max_uid intern nicht mehr."""
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

    def _get_inbox_folder_id(self, account_id: int) -> int | None:
        sc = self.db._get_structure_conn()
        row = sc.execute(
            "SELECT f.id FROM folders f JOIN mailboxes mb ON f.mailbox_id=mb.id "
            "WHERE mb.account_id=? AND f.folder_type='inbox'", (account_id,)
        ).fetchone()
        return row[0] if row else None

    def _get_sent_folder_id(self, account_id: int) -> int | None:
        sc = self.db._get_structure_conn()
        row = sc.execute(
            "SELECT f.id FROM folders f JOIN mailboxes mb ON f.mailbox_id=mb.id "
            "WHERE mb.account_id=? AND f.folder_type='sent'", (account_id,)
        ).fetchone()
        return row[0] if row else None

    def _get_outbox_folder_id(self) -> int | None:
        """Gibt die ID des Postausgangs in Lokale Ordner zurück."""
        return self._get_local_folder_by_type("outbox")

    def _get_local_folder_by_type(self, folder_type: str) -> int | None:
        """Findet einen Ordner in LOCAL-Konten per Typ (zwei-Schritt, kein Cross-DB-JOIN)."""
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

    def _find_account_by_email(self, email_addr: str) -> dict | None:
        """Findet ein Konto anhand der E-Mail-Adresse im From-Feld."""
        for acc in self.db.get_accounts():
            a = dict(acc)
            if a.get("email", "").lower() in email_addr.lower():
                return a
        return None

    def create_welcome_mail(self, inbox_folder_id: int):
        """Legt die Willkommens-Nachricht im Posteingang an."""
        from core.i18n import tr
        from datetime import datetime
        self.db.insert_mail(inbox_folder_id, {
            "subject":      tr("welcome_subject"),
            "sender":       tr("welcome_sender"),
            "sender_name":  tr("welcome_sender_name"),
            "recipients":   "",
            "date":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "body_text":    tr("welcome_body"),
            "body_html":    "",
            "is_read":      0,
            "is_flagged":   0,
            "has_attach":   0,
            "size":         len(tr("welcome_body")),
        })
        self.db.update_folder_unread(inbox_folder_id)
