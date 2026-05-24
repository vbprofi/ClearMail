"""
Datenbankmanager - Verwaltet beide SQLite-Datenbanken:
- accounts.db: Login-Daten, Einstellungen
- mailstore.db: Mails, Postfächer, Ordner
"""

import sqlite3
import os
import hashlib
from datetime import datetime, timedelta
import random


class DatabaseManager:
    """Zentrale Datenbankverwaltung"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.expanduser("~"), ".mailclient")
        os.makedirs(data_dir, exist_ok=True)

        self.accounts_db_path = os.path.join(data_dir, "accounts.db")
        self.mailstore_db_path = os.path.join(data_dir, "mailstore.db")

        self._accounts_conn = None
        self._mailstore_conn = None

    # ------------------------------------------------------------------ #
    #  Verbindungen                                                        #
    # ------------------------------------------------------------------ #

    def _get_accounts_conn(self) -> sqlite3.Connection:
        if self._accounts_conn is None:
            self._accounts_conn = sqlite3.connect(self.accounts_db_path)
            self._accounts_conn.row_factory = sqlite3.Row
        return self._accounts_conn

    def _get_mailstore_conn(self) -> sqlite3.Connection:
        if self._mailstore_conn is None:
            self._mailstore_conn = sqlite3.connect(self.mailstore_db_path)
            self._mailstore_conn.row_factory = sqlite3.Row
        return self._mailstore_conn

    def close(self):
        if self._accounts_conn:
            self._accounts_conn.close()
        if self._mailstore_conn:
            self._mailstore_conn.close()

    # ------------------------------------------------------------------ #
    #  Initialisierung                                                     #
    # ------------------------------------------------------------------ #

    def initialize(self):
        self._create_accounts_schema()
        self._create_mailstore_schema()
        self._seed_demo_data()

    def _create_accounts_schema(self):
        conn = self._get_accounts_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                email       TEXT NOT NULL UNIQUE,
                protocol    TEXT NOT NULL DEFAULT 'IMAP',
                in_host     TEXT,
                in_port     INTEGER,
                in_ssl      INTEGER DEFAULT 1,
                out_host    TEXT,
                out_port    INTEGER DEFAULT 587,
                out_ssl     INTEGER DEFAULT 1,
                username    TEXT,
                password    TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                active      INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS settings (
                key         TEXT PRIMARY KEY,
                value       TEXT,
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS addon_registry (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                version     TEXT,
                enabled     INTEGER DEFAULT 1,
                path        TEXT,
                meta        TEXT
            );
        """)
        conn.commit()

    def _create_mailstore_schema(self):
        conn = self._get_mailstore_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS mailboxes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id  INTEGER NOT NULL,
                name        TEXT NOT NULL,
                email       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS folders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                mailbox_id  INTEGER NOT NULL,
                parent_id   INTEGER,
                name        TEXT NOT NULL,
                folder_type TEXT DEFAULT 'custom',
                imap_path   TEXT,
                unread      INTEGER DEFAULT 0,
                FOREIGN KEY (mailbox_id) REFERENCES mailboxes(id),
                FOREIGN KEY (parent_id)  REFERENCES folders(id)
            );

            CREATE TABLE IF NOT EXISTS mails (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id    INTEGER NOT NULL,
                uid          TEXT,
                subject      TEXT,
                sender       TEXT,
                sender_name  TEXT,
                recipients   TEXT,
                cc           TEXT,
                bcc          TEXT,
                date         TEXT,
                body_text    TEXT,
                body_html    TEXT,
                is_read      INTEGER DEFAULT 0,
                is_flagged   INTEGER DEFAULT 0,
                is_answered  INTEGER DEFAULT 0,
                has_attach   INTEGER DEFAULT 0,
                size         INTEGER DEFAULT 0,
                message_id   TEXT,
                raw_path     TEXT,
                created_at   TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (folder_id) REFERENCES folders(id)
            );

            CREATE TABLE IF NOT EXISTS attachments (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                mail_id   INTEGER NOT NULL,
                filename  TEXT,
                mime_type TEXT,
                size      INTEGER,
                data      BLOB,
                FOREIGN KEY (mail_id) REFERENCES mails(id)
            );
        """)
        conn.commit()

    # ------------------------------------------------------------------ #
    #  Demo-Daten                                                         #
    # ------------------------------------------------------------------ #

    def _seed_demo_data(self):
        conn = self._get_mailstore_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mailboxes")
        if cur.fetchone()[0] > 0:
            return  # Bereits befüllt

        demo_accounts = [
            (1, "Max Mustermann",   "max.mustermann@example.com"),
            (2, "Anna Schmidt",     "anna.schmidt@werk.de"),
            (3, "Info Firma GmbH",  "info@firma-gmbh.de"),
        ]

        imap_folders = [
            ("Posteingang",  "inbox",   None),
            ("Gesendet",     "sent",    None),
            ("Entwürfe",     "drafts",  None),
            ("Papierkorb",   "trash",   None),
            ("Spam",         "spam",    None),
            ("Archiv",       "archive", None),
        ]

        acc_conn = self._get_accounts_conn()
        for aid, name, email in demo_accounts:
            acc_conn.execute(
                "INSERT OR IGNORE INTO accounts (id, name, email, protocol, in_host, in_port, out_host, out_port, username) "
                "VALUES (?, ?, ?, 'IMAP', 'imap.example.com', 993, 'smtp.example.com', 587, ?)",
                (aid, name, email, email)
            )
        acc_conn.commit()

        folder_ids = {}   # (mailbox_id, folder_name) -> folder_id
        mailbox_ids = {}

        for aid, name, email in demo_accounts:
            cur.execute("INSERT INTO mailboxes (account_id, name, email) VALUES (?, ?, ?)",
                        (aid, name, email))
            mb_id = cur.lastrowid
            mailbox_ids[aid] = mb_id

            for fname, ftype, _ in imap_folders:
                cur.execute(
                    "INSERT INTO folders (mailbox_id, parent_id, name, folder_type, imap_path) VALUES (?, NULL, ?, ?, ?)",
                    (mb_id, fname, ftype, fname.upper())
                )
                fid = cur.lastrowid
                folder_ids[(mb_id, ftype)] = fid

            # Unterordner für Archiv
            archive_id = folder_ids[(mb_id, "archive")]
            for sub in ["2023", "2024", "Projekte"]:
                cur.execute(
                    "INSERT INTO folders (mailbox_id, parent_id, name, folder_type) VALUES (?, ?, ?, 'custom')",
                    (mb_id, archive_id, sub)
                )

        conn.commit()

        # 10 Testmails je Posteingang
        senders = [
            ("newsletter@techmagazin.de",  "TechMagazin Newsletter"),
            ("support@beispiel-shop.de",    "Beispiel Shop Support"),
            ("chef@firma.de",              "Dr. Hans Müller"),
            ("kollegin@werk.de",           "Sabine Lehmann"),
            ("no-reply@bank.de",           "Sparkasse Online"),
            ("friend@privat.de",           "Klaus Berger"),
            ("events@stadt.de",            "Stadtportal"),
            ("security@dienst.de",         "Sicherheitsdienst"),
            ("noreply@paket.de",           "DHL Paketdienst"),
            ("kontakt@verein.de",          "Sportverein 1899"),
        ]

        subjects = [
            "Ihre monatliche Zusammenfassung ist bereit",
            "Bestellbestätigung #A-20241105-9921",
            "Wichtige Informationen zum Quartalsbericht",
            "Meeting-Einladung: Projektplanung Q1 2025",
            "Ihre Kontoauszüge für Oktober 2024",
            "Wochenendausflug – bist du dabei?",
            "Veranstaltungshinweis: Stadtfest 2024",
            "Sicherheitshinweis: Neues Gerät erkannt",
            "Ihr Paket ist unterwegs – Sendungsnummer 1Z999",
            "Einladung: Jahreshauptversammlung am 15.11.",
        ]

        bodies = [
            "Sehr geehrte Damen und Herren,\n\nim Anhang finden Sie Ihre monatliche Zusammenfassung für den Monat Oktober 2024.\n\nMit freundlichen Grüßen\nIhr Support-Team",
            "Vielen Dank für Ihre Bestellung!\n\nWir haben Ihre Bestellung erhalten und werden diese umgehend bearbeiten.\n\nBestellnummer: A-20241105-9921\nArtikel: 3x Produkt A, 1x Produkt B\nGesamtbetrag: 89,95 EUR\n\nMit freundlichen Grüßen",
            "Liebe Kolleginnen und Kollegen,\n\nhiermit lade ich Sie herzlich zu unserem Quartalsgespräch ein.\n\nTermin: 20. November 2024, 10:00 Uhr\nOrt: Konferenzraum 3, EG\n\nBitte bestätigen Sie Ihre Teilnahme.\n\nMit freundlichen Grüßen\nDr. Hans Müller",
            "Hallo,\n\nwürden wir uns diese Woche noch kurz abstimmen können? Ich habe ein paar Fragen zum laufenden Projekt.\n\nBeste Grüße\nSabine",
            "Sehr geehrter Herr Mustermann,\n\nIhre Kontoauszüge für den Monat Oktober 2024 stehen ab sofort in Ihrem Online-Banking bereit.\n\nMit freundlichen Grüßen\nIhre Sparkasse",
            "Hey Max,\n\nwieso meldest du dich nicht? Wir wollten doch am Wochenende wandern gehen. Bist du noch dabei?\n\nViele Grüße\nKlaus",
            "Liebe Bürgerinnen und Bürger,\n\ndas Stadtfest findet dieses Jahr am 30. November auf dem Marktplatz statt.\n\nWir freuen uns auf Ihren Besuch!\n\nStadtmarketing",
            "Wir haben festgestellt, dass sich ein neues Gerät in Ihrem Konto angemeldet hat.\n\nFalls Sie das nicht waren, ändern Sie bitte sofort Ihr Passwort.\n\nIhr Sicherheitsdienst",
            "Sehr geehrter Kunde,\n\nIhr Paket mit der Sendungsnummer 1Z999AA10123456784 ist auf dem Weg zu Ihnen.\n\nVoraussichtliche Lieferung: Morgen, 08:00-14:00 Uhr\n\nDHL Paketdienst",
            "Sehr geehrtes Mitglied,\n\nwir laden Sie herzlich zur Jahreshauptversammlung am 15. November 2024 ein.\n\nBeginn: 19:00 Uhr\nOrt: Vereinsheim, Sportplatz 1\n\nIhr Vorstand",
        ]

        base_date = datetime.now()
        for mb_id in mailbox_ids.values():
            inbox_id = folder_ids[(mb_id, "inbox")]
            for i in range(10):
                mail_date = base_date - timedelta(days=i, hours=random.randint(0, 12))
                sender_email, sender_name = senders[i]
                cur.execute("""
                    INSERT INTO mails
                        (folder_id, subject, sender, sender_name, recipients, date,
                         body_text, is_read, is_flagged, size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    inbox_id,
                    subjects[i],
                    sender_email,
                    sender_name,
                    "max.mustermann@example.com",
                    mail_date.strftime("%Y-%m-%d %H:%M:%S"),
                    bodies[i],
                    1 if i > 3 else 0,
                    1 if i == 2 else 0,
                    random.randint(2000, 80000)
                ))
            # Ungelesen-Zähler aktualisieren
            conn.execute("UPDATE folders SET unread = 4 WHERE id = ?", (inbox_id,))

        conn.commit()

    # ------------------------------------------------------------------ #
    #  Postfach / Ordner API                                              #
    # ------------------------------------------------------------------ #

    def get_mailboxes(self) -> list:
        conn = self._get_mailstore_conn()
        return list(conn.execute("SELECT * FROM mailboxes ORDER BY id").fetchall())

    def get_folders(self, mailbox_id: int) -> list:
        conn = self._get_mailstore_conn()
        return list(conn.execute(
            "SELECT * FROM folders WHERE mailbox_id = ? ORDER BY folder_type, name",
            (mailbox_id,)
        ).fetchall())

    def get_mails(self, folder_id: int) -> list:
        conn = self._get_mailstore_conn()
        return list(conn.execute(
            "SELECT * FROM mails WHERE folder_id = ? ORDER BY date DESC",
            (folder_id,)
        ).fetchall())

    def get_mail(self, mail_id: int):
        conn = self._get_mailstore_conn()
        return conn.execute("SELECT * FROM mails WHERE id = ?", (mail_id,)).fetchone()

    def mark_mail_read(self, mail_id: int, is_read: bool = True):
        conn = self._get_mailstore_conn()
        conn.execute("UPDATE mails SET is_read = ? WHERE id = ?", (1 if is_read else 0, mail_id))
        conn.commit()

    def mark_mail_flagged(self, mail_id: int, flagged: bool = True):
        conn = self._get_mailstore_conn()
        conn.execute("UPDATE mails SET is_flagged = ? WHERE id = ?", (1 if flagged else 0, mail_id))
        conn.commit()

    def delete_mail(self, mail_id: int):
        conn = self._get_mailstore_conn()
        conn.execute("DELETE FROM mails WHERE id = ?", (mail_id,))
        conn.commit()

    def move_mail(self, mail_id: int, target_folder_id: int):
        conn = self._get_mailstore_conn()
        conn.execute("UPDATE mails SET folder_id = ? WHERE id = ?", (target_folder_id, mail_id))
        conn.commit()

    def insert_mail(self, folder_id: int, data: dict) -> int:
        conn = self._get_mailstore_conn()
        cur = conn.execute("""
            INSERT INTO mails
                (folder_id, subject, sender, sender_name, recipients, cc, bcc,
                 date, body_text, body_html, is_read, has_attach, size, message_id)
            VALUES
                (:folder_id, :subject, :sender, :sender_name, :recipients, :cc, :bcc,
                 :date, :body_text, :body_html, :is_read, :has_attach, :size, :message_id)
        """, {**{"folder_id": folder_id, "cc": "", "bcc": "", "body_html": "",
                 "is_read": 0, "has_attach": 0, "size": 0, "message_id": ""},
              **data})
        conn.commit()
        return cur.lastrowid

    def update_folder_unread(self, folder_id: int):
        conn = self._get_mailstore_conn()
        conn.execute(
            "UPDATE folders SET unread = (SELECT COUNT(*) FROM mails WHERE folder_id = ? AND is_read = 0) WHERE id = ?",
            (folder_id, folder_id)
        )
        conn.commit()

    # ------------------------------------------------------------------ #
    #  Konto-API                                                          #
    # ------------------------------------------------------------------ #

    def get_accounts(self) -> list:
        conn = self._get_accounts_conn()
        return list(conn.execute("SELECT * FROM accounts ORDER BY id").fetchall())

    def get_account(self, account_id: int):
        conn = self._get_accounts_conn()
        return conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()

    def save_account(self, data: dict) -> int:
        conn = self._get_accounts_conn()
        if data.get("id"):
            conn.execute("""
                UPDATE accounts SET name=:name, email=:email, protocol=:protocol,
                    in_host=:in_host, in_port=:in_port, in_ssl=:in_ssl,
                    out_host=:out_host, out_port=:out_port, out_ssl=:out_ssl,
                    username=:username, password=:password
                WHERE id=:id
            """, data)
            conn.commit()
            return data["id"]
        else:
            cur = conn.execute("""
                INSERT INTO accounts (name, email, protocol, in_host, in_port, in_ssl,
                    out_host, out_port, out_ssl, username, password)
                VALUES (:name, :email, :protocol, :in_host, :in_port, :in_ssl,
                    :out_host, :out_port, :out_ssl, :username, :password)
            """, data)
            conn.commit()
            return cur.lastrowid

    def delete_account(self, account_id: int):
        conn = self._get_accounts_conn()
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()

    # ------------------------------------------------------------------ #
    #  Einstellungen                                                       #
    # ------------------------------------------------------------------ #

    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._get_accounts_conn()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        conn = self._get_accounts_conn()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value)
        )
        conn.commit()
