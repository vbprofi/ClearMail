"""
DatabaseManager v8 – saubere Architektur-Trennung:

  accounts.db   – Konten, Einstellungen (unveränderlich)
  structure.db  – Postfächer, Ordner (IMMER, unabhängig vom Mail-Modus)

Mail-Backends (einstellbar):
  sqlite_one          → structure.db enthält auch mails-Tabelle
  sqlite_per_account  → mailstore_<account_id>.db je Konto
  files               → ~/.mailclient/mailstore/<folder_id>/<id>.json + .eml

WICHTIG: is_read, is_flagged etc. sind Integer (0/1), NIEMALS leere Strings.
"""

import sqlite3, os, json, hashlib
from datetime import datetime, timedelta
import random

DATA_DIR = os.path.join(os.path.expanduser("~"), ".mailclient")

STORAGE_SQLITE_ONE         = "sqlite_one"
STORAGE_SQLITE_PER_ACCOUNT = "sqlite_per_account"
STORAGE_FILES              = "files"


class DatabaseManager:

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = DATA_DIR
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir          = data_dir
        self.accounts_db_path  = os.path.join(data_dir, "accounts.db")
        self.structure_db_path = os.path.join(data_dir, "structure.db")  # Ordner+Postfächer
        self.mailstore_db_path = os.path.join(data_dir, "structure.db")  # Alias für Kompatibilität

        self._accounts_conn:  sqlite3.Connection | None = None
        self._structure_conn: sqlite3.Connection | None = None
        self._per_account_conns: dict[int, sqlite3.Connection] = {}

    # ------------------------------------------------------------------ #
    #  Verbindungen                                                       #
    # ------------------------------------------------------------------ #

    def _get_accounts_conn(self) -> sqlite3.Connection:
        if self._accounts_conn is None:
            self._accounts_conn = sqlite3.connect(
                self.accounts_db_path, check_same_thread=False)
            self._accounts_conn.row_factory = sqlite3.Row
        return self._accounts_conn

    def _get_structure_conn(self) -> sqlite3.Connection:
        """Postfächer + Ordner – immer structure.db."""
        if self._structure_conn is None:
            self._structure_conn = sqlite3.connect(
                self.structure_db_path, check_same_thread=False)
            self._structure_conn.row_factory = sqlite3.Row
        return self._structure_conn

    # Alias für alten Code der _get_mailstore_conn() aufruft
    def _get_mailstore_conn(self) -> sqlite3.Connection:
        return self._get_structure_conn()

    def _get_account_mail_conn(self, account_id: int) -> sqlite3.Connection:
        if account_id not in self._per_account_conns:
            path = os.path.join(self.data_dir, f"mailstore_{account_id}.db")
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._per_account_conns[account_id] = conn
            self._create_mails_schema(conn)
        return self._per_account_conns[account_id]

    def _mail_conn_for_folder(self, folder_id: int) -> sqlite3.Connection:
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        if mode == STORAGE_SQLITE_PER_ACCOUNT:
            acc_id = self._account_id_for_folder(folder_id)
            if acc_id:
                return self._get_account_mail_conn(acc_id)
        return self._get_structure_conn()

    def _account_id_for_folder(self, folder_id: int) -> int | None:
        conn = self._get_structure_conn()
        row = conn.execute(
            "SELECT mb.account_id FROM folders f "
            "JOIN mailboxes mb ON f.mailbox_id = mb.id WHERE f.id = ?",
            (folder_id,)
        ).fetchone()
        return row[0] if row else None

    def close(self):
        for c in [self._accounts_conn, self._structure_conn]:
            if c:
                try: c.close()
                except Exception: pass
        self._accounts_conn  = None
        self._structure_conn = None
        for conn in self._per_account_conns.values():
            try: conn.close()
            except Exception: pass
        self._per_account_conns.clear()

    # ------------------------------------------------------------------ #
    #  Schema                                                             #
    # ------------------------------------------------------------------ #

    def initialize(self):
        self._create_accounts_schema()
        self._create_structure_schema()
        self._migrate_existing_schema()   # Spalten nachrüsten falls DB älter
        # Demo-Daten werden NICHT mehr automatisch angelegt.
        # Ersteinrichtung erfolgt über SetupDialog beim ersten Start.

    def _migrate_existing_schema(self):
        """Ergänzt fehlende Spalten in bestehenden Datenbanken (Vorwärts-Migration)."""
        conn = self._get_structure_conn()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(mails)").fetchall()]
        # body_html fehlt in sehr alten Versionen
        if "body_html" not in cols:
            conn.execute("ALTER TABLE mails ADD COLUMN body_html TEXT DEFAULT ''")
            conn.commit()

    def _create_accounts_schema(self):
        conn = self._get_accounts_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
                protocol TEXT NOT NULL DEFAULT 'IMAP',
                in_host TEXT, in_port INTEGER, in_ssl INTEGER DEFAULT 1,
                out_host TEXT, out_port INTEGER DEFAULT 587, out_ssl INTEGER DEFAULT 1,
                username TEXT, password TEXT,
                created_at TEXT DEFAULT (datetime('now')), active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS addon_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                version TEXT, enabled INTEGER DEFAULT 1, path TEXT, meta TEXT
            );
        """)
        conn.commit()

    def _create_structure_schema(self):
        """structure.db: Postfächer, Ordner, und mails-Tabelle für sqlite_one-Modus."""
        conn = self._get_structure_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS mailboxes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                name TEXT NOT NULL, email TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mailbox_id INTEGER NOT NULL, parent_id INTEGER,
                name TEXT NOT NULL, folder_type TEXT DEFAULT 'custom',
                imap_path TEXT, unread INTEGER DEFAULT 0,
                FOREIGN KEY (mailbox_id) REFERENCES mailboxes(id),
                FOREIGN KEY (parent_id)  REFERENCES folders(id)
            );
            CREATE TABLE IF NOT EXISTS mails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL, uid TEXT,
                subject TEXT, sender TEXT, sender_name TEXT,
                recipients TEXT, cc TEXT, bcc TEXT, date TEXT,
                body_text TEXT, body_html TEXT,
                is_read INTEGER NOT NULL DEFAULT 0,
                is_flagged INTEGER NOT NULL DEFAULT 0,
                is_answered INTEGER NOT NULL DEFAULT 0,
                has_attach INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0,
                message_id TEXT, raw_path TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (folder_id) REFERENCES folders(id)
            );
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mail_id INTEGER NOT NULL, filename TEXT,
                mime_type TEXT, size INTEGER, data BLOB,
                FOREIGN KEY (mail_id) REFERENCES mails(id)
            );
        """)
        conn.commit()

    def _create_mails_schema(self, conn: sqlite3.Connection):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS mails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL, uid TEXT,
                subject TEXT, sender TEXT, sender_name TEXT,
                recipients TEXT, cc TEXT, bcc TEXT, date TEXT,
                body_text TEXT, body_html TEXT,
                is_read INTEGER NOT NULL DEFAULT 0,
                is_flagged INTEGER NOT NULL DEFAULT 0,
                is_answered INTEGER NOT NULL DEFAULT 0,
                has_attach INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0,
                message_id TEXT, raw_path TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()

    # ------------------------------------------------------------------ #
    #  Demo-Daten                                                         #
    # ------------------------------------------------------------------ #

    def _seed_demo_data(self):
        conn = self._get_structure_conn()
        if conn.execute("SELECT COUNT(*) FROM mailboxes").fetchone()[0] > 0:
            return

        demo_accounts = [
            (1, "Max Mustermann",  "max.mustermann@example.com"),
            (2, "Anna Schmidt",    "anna.schmidt@werk.de"),
            (3, "Info Firma GmbH", "info@firma-gmbh.de"),
        ]
        imap_folders = [
            ("Posteingang", "inbox"), ("Gesendet", "sent"),
            ("Entwürfe", "drafts"),   ("Papierkorb", "trash"),
            ("Spam", "spam"),         ("Archiv", "archive"),
        ]
        acc_conn = self._get_accounts_conn()
        for aid, name, email in demo_accounts:
            acc_conn.execute(
                "INSERT OR IGNORE INTO accounts "
                "(id,name,email,protocol,in_host,in_port,out_host,out_port,username) "
                "VALUES (?,?,?,'IMAP','imap.example.com',993,'smtp.example.com',587,?)",
                (aid, name, email, email)
            )
        acc_conn.commit()

        cur = conn.cursor()
        folder_ids = {}
        for aid, name, email in demo_accounts:
            cur.execute("INSERT INTO mailboxes (account_id,name,email) VALUES (?,?,?)",
                        (aid, name, email))
            mb_id = cur.lastrowid
            for fname, ftype in imap_folders:
                cur.execute(
                    "INSERT INTO folders (mailbox_id,parent_id,name,folder_type) VALUES (?,NULL,?,?)",
                    (mb_id, fname, ftype)
                )
                folder_ids[(mb_id, ftype)] = cur.lastrowid
            arch_id = folder_ids[(mb_id, "archive")]
            for sub in ["2023", "2024", "Projekte"]:
                cur.execute(
                    "INSERT INTO folders (mailbox_id,parent_id,name,folder_type) VALUES (?,?,'','custom')",
                    (mb_id, arch_id)
                )
                # Fix the name
                conn.execute("UPDATE folders SET name=? WHERE id=?", (sub, cur.lastrowid))
        conn.commit()

        senders = [
            ("newsletter@techmagazin.de", "TechMagazin Newsletter"),
            ("support@beispiel-shop.de",  "Beispiel Shop Support"),
            ("chef@firma.de",             "Dr. Hans Müller"),
            ("kollegin@werk.de",          "Sabine Lehmann"),
            ("no-reply@bank.de",          "Sparkasse Online"),
            ("friend@privat.de",          "Klaus Berger"),
            ("events@stadt.de",           "Stadtportal"),
            ("security@dienst.de",        "Sicherheitsdienst"),
            ("noreply@paket.de",          "DHL Paketdienst"),
            ("kontakt@verein.de",         "Sportverein 1899"),
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
            "Sehr geehrte Damen und Herren,\n\nim Anhang die monatliche Zusammenfassung.\n\nMit freundlichen Grüßen",
            "Vielen Dank für Ihre Bestellung!\n\nBestellnummer: A-20241105-9921\nBetrag: 89,95 EUR",
            "Liebe Kollegen,\n\nhiermit lade ich zum Quartalsgespräch ein.\n\nDr. Hans Müller",
            "Hallo,\n\nkurze Abstimmung diese Woche?\n\nBeste Grüße\nSabine",
            "Ihre Kontoauszüge für Oktober 2024 stehen im Online-Banking bereit.",
            "Hey Max,\n\nWanderung am Wochenende – bist du dabei?\n\nKlaus",
            "Das Stadtfest findet am 30. November auf dem Marktplatz statt.",
            "Neues Gerät in Ihrem Konto erkannt. Falls nicht Sie: Passwort ändern.",
            "Ihr Paket 1Z999 ist unterwegs. Lieferung: morgen 08-14 Uhr.",
            "Einladung zur JHV am 15. November, 19:00 Uhr im Vereinsheim.",
        ]

        base_date = datetime.now()
        # Mails in structure.db (sqlite_one ist Standard)
        for (mb_id, _), ftype in [((k[0], None), k[1]) for k in folder_ids if k[1] == "inbox"]:
            inbox_id = folder_ids[(mb_id, "inbox")]
            for i in range(10):
                d = base_date - timedelta(days=i, hours=random.randint(0, 12))
                se, sn = senders[i]
                cur.execute(
                    "INSERT INTO mails (folder_id,subject,sender,sender_name,recipients,"
                    "date,body_text,is_read,is_flagged,size) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (inbox_id, subjects[i], se, sn, "max@example.com",
                     d.strftime("%Y-%m-%d %H:%M:%S"), bodies[i],
                     1 if i > 3 else 0, 1 if i == 2 else 0,
                     random.randint(2000, 80000))
                )
            conn.execute("UPDATE folders SET unread=4 WHERE id=?", (inbox_id,))

            # ---- 3 HTML-Demo-Mails je Posteingang ----
            html_mails = [
                {
                    "subject": "🎉 Newsletter: Neue Funktionen im Oktober 2024",
                    "sender": "newsletter@techmagazin.de",
                    "sender_name": "TechMagazin Newsletter",
                    "body_html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Newsletter</title></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
<div style="background: #0078d4; color: white; padding: 24px; border-radius: 8px 8px 0 0;">
  <h1 style="margin: 0; font-size: 24px;">TechMagazin Newsletter</h1>
  <p style="margin: 8px 0 0; opacity: 0.9;">Oktober 2024 – Neue Funktionen</p>
</div>
<div style="background: white; padding: 24px; border-radius: 0 0 8px 8px; border: 1px solid #ddd;">
  <h2 style="color: #0078d4;">Was ist neu?</h2>
  <p>Liebe Leserin, lieber Leser,</p>
  <p>in dieser Ausgabe stellen wir Ihnen die <strong>neuesten Entwicklungen</strong> aus der Tech-Welt vor.</p>

  <h3 style="border-bottom: 2px solid #0078d4; padding-bottom: 8px;">Top-Themen</h3>
  <ul>
    <li>🤖 <strong>KI-Assistenten</strong> revolutionieren den Alltag</li>
    <li>🔒 <strong>Zero-Trust-Sicherheit</strong> – Was steckt dahinter?</li>
    <li>🚀 <strong>Python 3.13</strong> – Neue Features im Überblick</li>
    <li>📱 <strong>Mobile-First</strong> – Warum Desktop nicht stirbt</li>
  </ul>

  <blockquote style="border-left: 4px solid #0078d4; margin: 16px 0; padding: 12px 16px; background: #f0f7ff; border-radius: 0 4px 4px 0;">
    <em>"Die beste Art, die Zukunft vorherzusagen, ist, sie zu gestalten."</em><br>
    <small>– Peter Drucker</small>
  </blockquote>

  <h3 style="border-bottom: 2px solid #0078d4; padding-bottom: 8px;">Artikel des Monats</h3>
  <p>Unser Chefredakteur hat einen ausführlichen <a href="#">Vergleich der beliebtesten E-Mail-Clients</a> 
  geschrieben. Besonderes Augenmerk liegt auf der <strong>Barrierefreiheit</strong> und 
  <strong>Screenreader-Kompatibilität</strong>.</p>

  <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
    <tr style="background: #0078d4; color: white;">
      <th style="padding: 10px; text-align: left;">Client</th>
      <th style="padding: 10px; text-align: left;">Plattform</th>
      <th style="padding: 10px; text-align: left;">Bewertung</th>
    </tr>
    <tr style="background: #f9f9f9;">
      <td style="padding: 10px; border-bottom: 1px solid #eee;">Thunderbird</td>
      <td style="padding: 10px; border-bottom: 1px solid #eee;">Windows/Mac/Linux</td>
      <td style="padding: 10px; border-bottom: 1px solid #eee;">⭐⭐⭐⭐⭐</td>
    </tr>
    <tr>
      <td style="padding: 10px; border-bottom: 1px solid #eee;">Outlook</td>
      <td style="padding: 10px; border-bottom: 1px solid #eee;">Windows/Mac</td>
      <td style="padding: 10px; border-bottom: 1px solid #eee;">⭐⭐⭐⭐</td>
    </tr>
    <tr style="background: #f9f9f9;">
      <td style="padding: 10px;">ClearMail</td>
      <td style="padding: 10px;">Windows/Mac/Linux</td>
      <td style="padding: 10px;">⭐⭐⭐⭐⭐ <em>neu!</em></td>
    </tr>
  </table>

  <p style="color: #777; font-size: 13px; border-top: 1px solid #eee; padding-top: 16px; margin-top: 24px;">
  Sie erhalten diese E-Mail, weil Sie den TechMagazin-Newsletter abonniert haben.<br>
  <a href="#">Abmelden</a> | <a href="#">Online ansehen</a>
  </p>
</div>
</body></html>""",
                    "body_text": "TechMagazin Newsletter – Oktober 2024\n\nTop-Themen:\n- KI-Assistenten revolutionieren den Alltag\n- Zero-Trust-Sicherheit\n- Python 3.13 Neue Features\n- Mobile-First\n\nArtikel des Monats: Vergleich der beliebtesten E-Mail-Clients.",
                    "is_read": 0, "size": 4800,
                },
                {
                    "subject": "Ihre Bestellbestätigung – Rechnung #2024-10-887",
                    "sender": "bestellung@beispiel-shop.de",
                    "sender_name": "Beispiel-Shop",
                    "body_html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family: 'Segoe UI', Arial, sans-serif; background: #f4f4f4; padding: 20px;">
<div style="max-width: 580px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
  <div style="background: linear-gradient(135deg, #28a745, #20c997); padding: 24px; text-align: center;">
    <h1 style="color: white; margin: 0; font-size: 22px;">✅ Bestellung erfolgreich!</h1>
    <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0;">Vielen Dank für Ihren Einkauf</p>
  </div>
  <div style="padding: 24px;">
    <p>Sehr geehrter Kunde,</p>
    <p>Ihre Bestellung wurde erfolgreich aufgenommen und wird bearbeitet.</p>

    <div style="background: #f8f9fa; border-radius: 6px; padding: 16px; margin: 16px 0;">
      <h3 style="margin: 0 0 12px; color: #333;">Bestelldetails</h3>
      <p style="margin: 4px 0;"><strong>Bestellnummer:</strong> #2024-10-887</p>
      <p style="margin: 4px 0;"><strong>Datum:</strong> 15. Oktober 2024</p>
      <p style="margin: 4px 0;"><strong>Zahlungsmethode:</strong> PayPal</p>
    </div>

    <table style="width: 100%; border-collapse: collapse;">
      <tr style="background: #343a40; color: white;">
        <th style="padding: 10px; text-align: left;">Artikel</th>
        <th style="padding: 10px; text-align: right;">Menge</th>
        <th style="padding: 10px; text-align: right;">Preis</th>
      </tr>
      <tr>
        <td style="padding: 10px; border-bottom: 1px solid #eee;">USB-C Kabel (2m)</td>
        <td style="padding: 10px; text-align: right; border-bottom: 1px solid #eee;">2×</td>
        <td style="padding: 10px; text-align: right; border-bottom: 1px solid #eee;">15,98 €</td>
      </tr>
      <tr style="background: #f8f9fa;">
        <td style="padding: 10px; border-bottom: 1px solid #eee;">Mechanische Tastatur</td>
        <td style="padding: 10px; text-align: right; border-bottom: 1px solid #eee;">1×</td>
        <td style="padding: 10px; text-align: right; border-bottom: 1px solid #eee;">89,99 €</td>
      </tr>
      <tr>
        <td style="padding: 10px; border-bottom: 1px solid #eee;">Versand</td>
        <td style="padding: 10px; border-bottom: 1px solid #eee;"></td>
        <td style="padding: 10px; text-align: right; border-bottom: 1px solid #eee;">0,00 €</td>
      </tr>
      <tr style="font-weight: bold; background: #e8f5e9;">
        <td style="padding: 12px;" colspan="2">Gesamtbetrag</td>
        <td style="padding: 12px; text-align: right; font-size: 18px; color: #28a745;">105,97 €</td>
      </tr>
    </table>

    <p style="margin-top: 20px;">
      <strong>Lieferung:</strong> 3–5 Werktage<br>
      <strong>Lieferadresse:</strong> Musterstraße 1, 12345 Musterstadt
    </p>

    <div style="text-align: center; margin: 24px 0;">
      <a href="#" style="background: #28a745; color: white; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: bold;">Bestellung verfolgen</a>
    </div>
  </div>
  <div style="background: #f8f9fa; padding: 16px; text-align: center; font-size: 13px; color: #777;">
    Beispiel-Shop GmbH | Musterstraße 42 | 12345 Musterstadt<br>
    <a href="#">Widerrufsrecht</a> | <a href="#">AGB</a> | <a href="#">Impressum</a>
  </div>
</div>
</body></html>""",
                    "body_text": "Bestellbestätigung #2024-10-887\n\nSehr geehrter Kunde,\nIhre Bestellung wurde erfolgreich aufgenommen.\n\nArtikel:\n- USB-C Kabel (2m): 15,98 €\n- Mechanische Tastatur: 89,99 €\nGesamtbetrag: 105,97 €\n\nLieferung: 3–5 Werktage",
                    "is_read": 0, "size": 5200,
                },
                {
                    "subject": "Einladung: Team-Meeting Projektabschluss Q4",
                    "sender": "chef@firma.de",
                    "sender_name": "Dr. Hans Müller",
                    "body_html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family: 'Calibri', Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333; padding: 20px; max-width: 650px;">
<div style="border-left: 4px solid #0078d4; padding-left: 16px; margin-bottom: 20px;">
  <h2 style="color: #0078d4; margin: 0 0 4px;">📅 Meeting-Einladung</h2>
  <p style="margin: 0; color: #555;">Bitte bestätigen Sie Ihre Teilnahme</p>
</div>

<p>Liebe Kolleginnen und Kollegen,</p>

<p>ich lade Sie herzlich zu unserem <strong>Projektabschluss-Meeting Q4 2024</strong> ein.</p>

<div style="background: #f0f7ff; border: 1px solid #b3d4ff; border-radius: 6px; padding: 16px; margin: 16px 0;">
  <table style="width: 100%;">
    <tr>
      <td style="padding: 4px 0; color: #555; width: 120px;">📅 Datum:</td>
      <td style="padding: 4px 0; font-weight: bold;">Mittwoch, 20. November 2024</td>
    </tr>
    <tr>
      <td style="padding: 4px 0; color: #555;">⏰ Uhrzeit:</td>
      <td style="padding: 4px 0; font-weight: bold;">10:00 – 12:00 Uhr</td>
    </tr>
    <tr>
      <td style="padding: 4px 0; color: #555;">📍 Ort:</td>
      <td style="padding: 4px 0; font-weight: bold;">Konferenzraum 3, EG + Online</td>
    </tr>
    <tr>
      <td style="padding: 4px 0; color: #555;">🔗 Link:</td>
      <td style="padding: 4px 0;"><a href="#" style="color: #0078d4;">Teams-Meeting beitreten</a></td>
    </tr>
  </table>
</div>

<h3 style="color: #0078d4; border-bottom: 1px solid #ddd; padding-bottom: 8px;">Tagesordnung</h3>
<ol>
  <li><strong>Rückblick Q4</strong> – Zielerreichung und KPIs (20 Min.)</li>
  <li><strong>Projektpräsentation</strong> – Ergebnisse Team Alpha &amp; Beta (40 Min.)</li>
  <li><strong>Lessons Learned</strong> – Was haben wir gelernt? (20 Min.)</li>
  <li><strong>Planung Q1 2025</strong> – Ausblick und neue Ziele (20 Min.)</li>
  <li><strong>Verschiedenes</strong> (10 Min.)</li>
</ol>

<p>Bitte bereiten Sie eine kurze <strong>Zusammenfassung Ihrer Q4-Arbeit</strong> (max. 5 Folien) vor.</p>

<hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">

<p style="color: #555;">Mit freundlichen Grüßen</p>
<p><strong>Dr. Hans Müller</strong><br>
<em>Abteilungsleiter Entwicklung</em><br>
<span style="color: #0078d4;">📞 +49 30 123-4567</span><br>
<span style="color: #0078d4;">✉ chef@firma.de</span></p>

<div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 10px; margin-top: 16px; font-size: 13px;">
  ⚠️ <strong>Wichtig:</strong> Bitte bestätigen Sie Ihre Teilnahme bis <strong>18. November 2024</strong>.
</div>
</body></html>""",
                    "body_text": "Meeting-Einladung: Projektabschluss Q4 2024\n\nDatum: 20. November 2024\nUhrzeit: 10:00-12:00 Uhr\nOrt: Konferenzraum 3, EG\n\nTagesordnung:\n1. Rückblick Q4\n2. Projektpräsentation\n3. Lessons Learned\n4. Planung Q1 2025\n\nMit freundlichen Grüßen\nDr. Hans Müller",
                    "is_read": 0, "size": 6100,
                },
            ]
            d_html = base_date - timedelta(hours=random.randint(1, 6))
            for hm in html_mails:
                cur.execute(
                    "INSERT INTO mails (folder_id,subject,sender,sender_name,recipients,"
                    "date,body_text,body_html,is_read,size) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (inbox_id, hm["subject"], hm["sender"], hm["sender_name"],
                     "max@example.com",
                     d_html.strftime("%Y-%m-%d %H:%M:%S"),
                     hm["body_text"], hm["body_html"],
                     hm["is_read"], hm["size"])
                )
                d_html -= timedelta(hours=random.randint(2, 8))
            # 3 neue ungelesene HTML-Mails zum Zähler addieren
            conn.execute("UPDATE folders SET unread = unread + 3 WHERE id=?", (inbox_id,))
        conn.commit()

    def _seed_html_demo_mails(self):
        """
        Fügt HTML-Demo-Mails hinzu falls noch nicht vorhanden.
        Idempotent: prüft anhand des Subjects ob bereits vorhanden.
        Wird auch für bestehende Datenbanken ausgeführt.
        """
        conn = self._get_structure_conn()

        # Prüfen ob HTML-Demo-Mails bereits vorhanden
        existing = conn.execute(
            "SELECT COUNT(*) FROM mails WHERE body_html IS NOT NULL AND body_html != ''"
        ).fetchone()[0]
        if existing > 0:
            return  # Bereits vorhanden

        # Alle Posteingänge ermitteln
        inboxes = conn.execute(
            "SELECT f.id, f.mailbox_id FROM folders f "
            "WHERE f.folder_type='inbox'"
        ).fetchall()
        if not inboxes:
            return

        html_mails = [
            {
                "subject": "🎉 Newsletter: Neue Funktionen im Oktober 2024",
                "sender": "newsletter@techmagazin.de",
                "sender_name": "TechMagazin Newsletter",
                "body_text": (
                    "TechMagazin Newsletter – Oktober 2024\n\n"
                    "Top-Themen:\n"
                    "- KI-Assistenten revolutionieren den Alltag\n"
                    "- Zero-Trust-Sicherheit\n"
                    "- Python 3.13 Neue Features\n"
                    "- Mobile-First\n\n"
                    "Artikel des Monats: Vergleich der beliebtesten E-Mail-Clients."
                ),
                "body_html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Newsletter</title></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f9f9f9;">
<div style="background:#0078d4;color:white;padding:24px;border-radius:8px 8px 0 0;">
  <h1 style="margin:0;font-size:24px;">TechMagazin Newsletter</h1>
  <p style="margin:8px 0 0;opacity:0.9;">Oktober 2024 – Neue Funktionen</p>
</div>
<div style="background:white;padding:24px;border-radius:0 0 8px 8px;border:1px solid #ddd;">
  <h2 style="color:#0078d4;">Was ist neu?</h2>
  <p>Liebe Leserin, lieber Leser,</p>
  <p>in dieser Ausgabe stellen wir Ihnen die <strong>neuesten Entwicklungen</strong> aus der Tech-Welt vor.</p>
  <h3 style="border-bottom:2px solid #0078d4;padding-bottom:8px;">Top-Themen</h3>
  <ul>
    <li>🤖 <strong>KI-Assistenten</strong> revolutionieren den Alltag</li>
    <li>🔒 <strong>Zero-Trust-Sicherheit</strong> – Was steckt dahinter?</li>
    <li>🚀 <strong>Python 3.13</strong> – Neue Features im Überblick</li>
    <li>📱 <strong>Mobile-First</strong> – Warum Desktop nicht stirbt</li>
  </ul>
  <blockquote style="border-left:4px solid #0078d4;margin:16px 0;padding:12px 16px;background:#f0f7ff;">
    <em>"Die beste Art, die Zukunft vorherzusagen, ist, sie zu gestalten."</em><br>
    <small>– Peter Drucker</small>
  </blockquote>
  <h3 style="border-bottom:2px solid #0078d4;padding-bottom:8px;">Artikel des Monats</h3>
  <p>Unser Chefredakteur hat einen ausführlichen <a href="#">Vergleich der beliebtesten E-Mail-Clients</a>
  geschrieben – mit besonderem Fokus auf <strong>Barrierefreiheit</strong> und
  <strong>Screenreader-Kompatibilität</strong>.</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0;">
    <tr style="background:#0078d4;color:white;">
      <th style="padding:10px;text-align:left;">Client</th>
      <th style="padding:10px;text-align:left;">Plattform</th>
      <th style="padding:10px;text-align:left;">Bewertung</th>
    </tr>
    <tr style="background:#f9f9f9;">
      <td style="padding:10px;border-bottom:1px solid #eee;">Thunderbird</td>
      <td style="padding:10px;border-bottom:1px solid #eee;">Windows/Mac/Linux</td>
      <td style="padding:10px;border-bottom:1px solid #eee;">⭐⭐⭐⭐⭐</td>
    </tr>
    <tr>
      <td style="padding:10px;border-bottom:1px solid #eee;">Outlook</td>
      <td style="padding:10px;border-bottom:1px solid #eee;">Windows/Mac</td>
      <td style="padding:10px;border-bottom:1px solid #eee;">⭐⭐⭐⭐</td>
    </tr>
    <tr style="background:#f9f9f9;">
      <td style="padding:10px;">ClearMail</td>
      <td style="padding:10px;">Windows/Mac/Linux</td>
      <td style="padding:10px;">⭐⭐⭐⭐⭐ <em>neu!</em></td>
    </tr>
  </table>
</div>
</body></html>""",
                "is_read": 0, "size": 4800,
            },
            {
                "subject": "Bestellbestätigung – Rechnung #2024-10-887",
                "sender": "bestellung@beispiel-shop.de",
                "sender_name": "Beispiel-Shop",
                "body_text": (
                    "Bestellbestätigung #2024-10-887\n\n"
                    "Sehr geehrter Kunde,\n"
                    "Ihre Bestellung wurde erfolgreich aufgenommen.\n\n"
                    "Artikel:\n"
                    "- USB-C Kabel (2m): 15,98 €\n"
                    "- Mechanische Tastatur: 89,99 €\n\n"
                    "Gesamtbetrag: 105,97 €\n"
                    "Lieferung: 3–5 Werktage"
                ),
                "body_html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f4f4;padding:20px;">
<div style="max-width:580px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
  <div style="background:linear-gradient(135deg,#28a745,#20c997);padding:24px;text-align:center;">
    <h1 style="color:white;margin:0;font-size:22px;">✅ Bestellung erfolgreich!</h1>
    <p style="color:rgba(255,255,255,0.9);margin:8px 0 0;">Vielen Dank für Ihren Einkauf</p>
  </div>
  <div style="padding:24px;">
    <p>Sehr geehrter Kunde,</p>
    <p>Ihre Bestellung wurde erfolgreich aufgenommen und wird bearbeitet.</p>
    <div style="background:#f8f9fa;border-radius:6px;padding:16px;margin:16px 0;">
      <h3 style="margin:0 0 12px;color:#333;">Bestelldetails</h3>
      <p style="margin:4px 0;"><strong>Bestellnummer:</strong> #2024-10-887</p>
      <p style="margin:4px 0;"><strong>Datum:</strong> 15. Oktober 2024</p>
      <p style="margin:4px 0;"><strong>Zahlungsmethode:</strong> PayPal</p>
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="background:#343a40;color:white;">
        <th style="padding:10px;text-align:left;">Artikel</th>
        <th style="padding:10px;text-align:right;">Menge</th>
        <th style="padding:10px;text-align:right;">Preis</th>
      </tr>
      <tr>
        <td style="padding:10px;border-bottom:1px solid #eee;">USB-C Kabel (2m)</td>
        <td style="padding:10px;text-align:right;border-bottom:1px solid #eee;">2×</td>
        <td style="padding:10px;text-align:right;border-bottom:1px solid #eee;">15,98 €</td>
      </tr>
      <tr style="background:#f8f9fa;">
        <td style="padding:10px;border-bottom:1px solid #eee;">Mechanische Tastatur</td>
        <td style="padding:10px;text-align:right;border-bottom:1px solid #eee;">1×</td>
        <td style="padding:10px;text-align:right;border-bottom:1px solid #eee;">89,99 €</td>
      </tr>
      <tr style="font-weight:bold;background:#e8f5e9;">
        <td style="padding:12px;" colspan="2">Gesamtbetrag</td>
        <td style="padding:12px;text-align:right;font-size:18px;color:#28a745;">105,97 €</td>
      </tr>
    </table>
    <p style="margin-top:20px;"><strong>Lieferung:</strong> 3–5 Werktage</p>
  </div>
</div>
</body></html>""",
                "is_read": 0, "size": 5200,
            },
            {
                "subject": "Einladung: Team-Meeting Projektabschluss Q4",
                "sender": "chef@firma.de",
                "sender_name": "Dr. Hans Müller",
                "body_text": (
                    "Meeting-Einladung: Projektabschluss Q4 2024\n\n"
                    "Datum: 20. November 2024\n"
                    "Uhrzeit: 10:00-12:00 Uhr\n"
                    "Ort: Konferenzraum 3, EG\n\n"
                    "Tagesordnung:\n"
                    "1. Rückblick Q4\n"
                    "2. Projektpräsentation\n"
                    "3. Lessons Learned\n"
                    "4. Planung Q1 2025\n\n"
                    "Mit freundlichen Grüßen\n"
                    "Dr. Hans Müller"
                ),
                "body_html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Calibri',Arial,sans-serif;font-size:14px;line-height:1.6;color:#333;padding:20px;max-width:650px;">
<div style="border-left:4px solid #0078d4;padding-left:16px;margin-bottom:20px;">
  <h2 style="color:#0078d4;margin:0 0 4px;">📅 Meeting-Einladung</h2>
  <p style="margin:0;color:#555;">Bitte bestätigen Sie Ihre Teilnahme</p>
</div>
<p>Liebe Kolleginnen und Kollegen,</p>
<p>ich lade Sie herzlich zu unserem <strong>Projektabschluss-Meeting Q4 2024</strong> ein.</p>
<div style="background:#f0f7ff;border:1px solid #b3d4ff;border-radius:6px;padding:16px;margin:16px 0;">
  <table style="width:100%;">
    <tr><td style="padding:4px 0;color:#555;width:120px;">📅 Datum:</td>
        <td style="padding:4px 0;font-weight:bold;">Mittwoch, 20. November 2024</td></tr>
    <tr><td style="padding:4px 0;color:#555;">⏰ Uhrzeit:</td>
        <td style="padding:4px 0;font-weight:bold;">10:00 – 12:00 Uhr</td></tr>
    <tr><td style="padding:4px 0;color:#555;">📍 Ort:</td>
        <td style="padding:4px 0;font-weight:bold;">Konferenzraum 3, EG</td></tr>
  </table>
</div>
<h3 style="color:#0078d4;border-bottom:1px solid #ddd;padding-bottom:8px;">Tagesordnung</h3>
<ol>
  <li><strong>Rückblick Q4</strong> – Zielerreichung und KPIs (20 Min.)</li>
  <li><strong>Projektpräsentation</strong> – Ergebnisse Team Alpha &amp; Beta (40 Min.)</li>
  <li><strong>Lessons Learned</strong> – Was haben wir gelernt? (20 Min.)</li>
  <li><strong>Planung Q1 2025</strong> – Ausblick und neue Ziele (20 Min.)</li>
</ol>
<hr style="border:none;border-top:1px solid #ddd;margin:20px 0;">
<p>Mit freundlichen Grüßen</p>
<p><strong>Dr. Hans Müller</strong><br>
<em>Abteilungsleiter Entwicklung</em></p>
<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:10px;margin-top:16px;font-size:13px;">
  ⚠️ <strong>Wichtig:</strong> Bitte bestätigen Sie Ihre Teilnahme bis <strong>18. November 2024</strong>.
</div>
</body></html>""",
                "is_read": 0, "size": 6100,
            },
        ]

        base_date = datetime.now()
        for row in inboxes:
            inbox_id = row[0]
            d_html   = base_date - timedelta(hours=2)
            for hm in html_mails:
                conn.execute(
                    "INSERT INTO mails (folder_id,subject,sender,sender_name,recipients,"
                    "date,body_text,body_html,is_read,size) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (inbox_id, hm["subject"], hm["sender"], hm["sender_name"],
                     "max@example.com",
                     d_html.strftime("%Y-%m-%d %H:%M:%S"),
                     hm["body_text"], hm["body_html"],
                     hm["is_read"], hm["size"])
                )
                d_html -= timedelta(hours=3)
            conn.execute(
                "UPDATE folders SET unread = unread + 3 WHERE id=?", (inbox_id,))
        conn.commit()

    def get_mailboxes(self) -> list:
        conn = self._get_structure_conn()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(mailboxes)").fetchall()]
        if "sort_order" in cols:
            return list(conn.execute("SELECT * FROM mailboxes ORDER BY sort_order,id").fetchall())
        return list(conn.execute("SELECT * FROM mailboxes ORDER BY id").fetchall())

    def get_folders(self, mailbox_id: int) -> list:
        conn = self._get_structure_conn()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(folders)").fetchall()]
        if "sort_order" in cols:
            return list(conn.execute(
                "SELECT * FROM folders WHERE mailbox_id=? ORDER BY sort_order,id",
                (mailbox_id,)).fetchall())
        return list(conn.execute(
            "SELECT * FROM folders WHERE mailbox_id=? ORDER BY folder_type,name",
            (mailbox_id,)).fetchall())

    # ------------------------------------------------------------------ #
    #  Mail-API (Storage-Mode-aware)                                     #
    # ------------------------------------------------------------------ #

    def get_mails(self, folder_id: int) -> list:
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        if mode == STORAGE_FILES:
            return self._get_mails_from_files(folder_id)
        conn = self._mail_conn_for_folder(folder_id)
        return list(conn.execute(
            "SELECT * FROM mails WHERE folder_id=? ORDER BY date DESC",
            (folder_id,)).fetchall())

    def get_mail(self, mail_id: int, folder_id: int = None):
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        if mode == STORAGE_FILES:
            if folder_id:
                return self._get_mail_from_file(mail_id, folder_id)
            # Alle Ordner durchsuchen
            store_dir = os.path.join(self.data_dir, "mailstore")
            if os.path.isdir(store_dir):
                for entry in os.scandir(store_dir):
                    if entry.is_dir():
                        try:
                            r = self._get_mail_from_file(mail_id, int(entry.name))
                            if r: return r
                        except Exception: pass
            return None
        if mode == STORAGE_SQLITE_PER_ACCOUNT:
            if folder_id:
                conn = self._mail_conn_for_folder(folder_id)
                row = conn.execute("SELECT * FROM mails WHERE id=?", (mail_id,)).fetchone()
                if row: return row
            for acc in self.get_accounts():
                conn = self._get_account_mail_conn(acc["id"])
                row = conn.execute("SELECT * FROM mails WHERE id=?", (mail_id,)).fetchone()
                if row: return row
            return None
        # STORAGE_SQLITE_ONE
        return self._get_structure_conn().execute(
            "SELECT * FROM mails WHERE id=?", (mail_id,)).fetchone()

    def mark_mail_read(self, mail_id: int, is_read: bool = True, folder_id: int = None):
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        val  = 1 if is_read else 0
        if mode == STORAGE_FILES and folder_id:
            self._update_mail_file_field(mail_id, folder_id, "is_read", val)
            return
        conn = self._mail_conn_for_folder(folder_id) if folder_id else self._get_structure_conn()
        conn.execute("UPDATE mails SET is_read=? WHERE id=?", (val, mail_id))
        conn.commit()

    def mark_mail_flagged(self, mail_id: int, flagged: bool = True, folder_id: int = None):
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        val  = 1 if flagged else 0
        if mode == STORAGE_FILES and folder_id:
            self._update_mail_file_field(mail_id, folder_id, "is_flagged", val)
            return
        conn = self._mail_conn_for_folder(folder_id) if folder_id else self._get_structure_conn()
        conn.execute("UPDATE mails SET is_flagged=? WHERE id=?", (val, mail_id))
        conn.commit()

    def delete_mail(self, mail_id: int, folder_id: int = None):
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        if mode == STORAGE_FILES and folder_id:
            self._delete_mail_file(mail_id, folder_id)
            return
        conn = self._mail_conn_for_folder(folder_id) if folder_id else self._get_structure_conn()
        conn.execute("DELETE FROM mails WHERE id=?", (mail_id,))
        conn.commit()

    def move_mail(self, mail_id: int, target_folder_id: int, source_folder_id: int = None):
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        if mode == STORAGE_FILES:
            self._move_mail_file(mail_id, source_folder_id, target_folder_id)
            return
        conn = self._mail_conn_for_folder(source_folder_id or target_folder_id)
        conn.execute("UPDATE mails SET folder_id=? WHERE id=?", (target_folder_id, mail_id))
        conn.commit()

    def insert_mail(self, folder_id: int, data: dict) -> int:
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        if mode == STORAGE_FILES:
            return self._insert_mail_file(folder_id, data)
        conn = self._mail_conn_for_folder(folder_id)
        cur = conn.execute("""
            INSERT INTO mails
                (folder_id,subject,sender,sender_name,recipients,cc,bcc,
                 date,body_text,body_html,is_read,has_attach,size,message_id)
            VALUES
                (:folder_id,:subject,:sender,:sender_name,:recipients,:cc,:bcc,
                 :date,:body_text,:body_html,:is_read,:has_attach,:size,:message_id)
        """, {**{"folder_id": folder_id, "cc": "", "bcc": "", "body_html": "",
                 "is_read": 0, "has_attach": 0, "size": 0, "message_id": ""}, **data})
        conn.commit()
        return cur.lastrowid

    def update_folder_unread(self, folder_id: int):
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        if mode == STORAGE_FILES:
            count = 0
            for d in self._all_file_dirs(folder_id):
                if not os.path.isdir(d): continue
                for fn in os.listdir(d):
                    if fn.endswith(".json"):
                        try:
                            with open(os.path.join(d, fn), encoding="utf-8") as f:
                                m = json.load(f)
                            if int(m.get("is_read", 0)) == 0:
                                count += 1
                        except Exception: pass
        elif mode == STORAGE_SQLITE_PER_ACCOUNT:
            conn = self._mail_conn_for_folder(folder_id)
            r = conn.execute(
                "SELECT COUNT(*) FROM mails WHERE folder_id=? AND is_read=0",
                (folder_id,)).fetchone()
            count = r[0] if r else 0
        else:
            conn = self._get_structure_conn()
            r = conn.execute(
                "SELECT COUNT(*) FROM mails WHERE folder_id=? AND is_read=0",
                (folder_id,)).fetchone()
            count = r[0] if r else 0

        sc = self._get_structure_conn()
        sc.execute("UPDATE folders SET unread=? WHERE id=?", (count, folder_id))
        sc.commit()

    # ------------------------------------------------------------------ #
    #  Backup + Migration                                                 #
    # ------------------------------------------------------------------ #

    def create_backup(self, progress_cb=None) -> str:
        import shutil
        ts         = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        backup_dir = os.path.join(self.data_dir, "backups", ts)
        os.makedirs(backup_dir, exist_ok=True)
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)

        if mode == STORAGE_SQLITE_ONE:
            if progress_cb: progress_cb(0, 1, "Sichere structure.db…")
            shutil.copy2(self.structure_db_path,
                         os.path.join(backup_dir, "structure.db"))
            if progress_cb: progress_cb(1, 1, "Backup abgeschlossen.")

        elif mode == STORAGE_SQLITE_PER_ACCOUNT:
            accs = self.get_accounts()
            for i, acc in enumerate(accs):
                db = os.path.join(self.data_dir, f"mailstore_{acc['id']}.db")
                if os.path.exists(db):
                    if progress_cb: progress_cb(i, len(accs), f"Sichere {os.path.basename(db)}…")
                    shutil.copy2(db, os.path.join(backup_dir, os.path.basename(db)))
            if progress_cb: progress_cb(len(accs), len(accs), "Backup abgeschlossen.")

        elif mode == STORAGE_FILES:
            store = os.path.join(self.data_dir, "mailstore")
            if os.path.isdir(store):
                dst = os.path.join(backup_dir, "mailstore")
                if progress_cb: progress_cb(0, 1, "Sichere Mail-Dateien…")
                if os.path.exists(dst): shutil.rmtree(dst)
                shutil.copytree(store, dst)
                if progress_cb: progress_cb(1, 1, "Backup abgeschlossen.")

        return backup_dir

    def _cleanup_old_backend(self, old_mode: str):
        import shutil
        if old_mode == STORAGE_SQLITE_ONE:
            # Mails aus structure.db leeren (Ordner bleiben!)
            c = self._get_structure_conn()
            c.execute("DELETE FROM mails")
            c.commit()

        elif old_mode == STORAGE_SQLITE_PER_ACCOUNT:
            for acc in self.get_accounts():
                db = os.path.join(self.data_dir, f"mailstore_{acc['id']}.db")
                aid = acc["id"]
                if aid in self._per_account_conns:
                    try: self._per_account_conns[aid].close()
                    except Exception: pass
                    del self._per_account_conns[aid]
                if os.path.exists(db):
                    try: os.remove(db)
                    except OSError: pass

        elif old_mode == STORAGE_FILES:
            store = os.path.join(self.data_dir, "mailstore")
            if os.path.isdir(store):
                try: shutil.rmtree(store)
                except OSError: pass
                if os.path.isdir(store):
                    for root, dirs, files in os.walk(store, topdown=False):
                        for f in files:
                            try: os.remove(os.path.join(root, f))
                            except OSError: pass
                        for d in dirs:
                            try: os.rmdir(os.path.join(root, d))
                            except OSError: pass
                    try: os.rmdir(store)
                    except OSError: pass

    def migrate_storage(self, new_mode: str, progress_cb=None):
        old_mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)
        if old_mode == new_mode:
            return

        def _cb(s, t, m):
            if progress_cb: progress_cb(s, t, m)

        _cb(0, 100, "Erstelle Backup…")
        self.create_backup(progress_cb=lambda s, t, m: _cb(int(s/max(t,1)*20), 100, m))

        _cb(20, 100, "Lese Mails aus aktuellem Backend…")
        all_mails = self._export_all_mails(old_mode)
        _cb(30, 100, f"{len(all_mails)} Mail(s) gelesen.")

        self.set_setting("mail_storage", new_mode)

        _cb(35, 100, f"Schreibe ins neue Backend ({new_mode})…")
        self._import_mails_with_progress(all_mails, new_mode, progress_cb)

        _cb(95, 100, "Bereinige altes Backend…")
        self._cleanup_old_backend(old_mode)

        _cb(97, 100, "Aktualisiere Ordner-Zähler…")
        self._recalculate_all_unread(new_mode)

        _cb(100, 100, "Migration abgeschlossen.")

    def _export_all_mails(self, mode: str) -> list:
        if mode == STORAGE_SQLITE_ONE:
            return [dict(r) for r in
                    self._get_structure_conn().execute("SELECT * FROM mails").fetchall()]
        if mode == STORAGE_SQLITE_PER_ACCOUNT:
            result = []
            for acc in self.get_accounts():
                rows = self._get_account_mail_conn(acc["id"]).execute(
                    "SELECT * FROM mails").fetchall()
                result.extend([dict(r) for r in rows])
            return result
        if mode == STORAGE_FILES:
            result = []
            store = os.path.join(self.data_dir, "mailstore")
            if not os.path.isdir(store): return []
            for root, _, files in os.walk(store):
                for fn in files:
                    if fn.endswith(".json"):
                        try:
                            with open(os.path.join(root, fn), encoding="utf-8") as f:
                                m = json.load(f)
                            eml = os.path.join(root, fn.replace(".json", ".eml"))
                            if os.path.exists(eml):
                                with open(eml, encoding="utf-8", errors="replace") as f:
                                    m["body_text"] = self._parse_eml_body(f.read())
                            # Sicherstellen: is_read ist Integer
                            m["is_read"]    = int(m.get("is_read", 0))
                            m["is_flagged"] = int(m.get("is_flagged", 0))
                            m["is_answered"]= int(m.get("is_answered", 0))
                            m["has_attach"] = int(m.get("has_attach", 0))
                            m["size"]       = int(m.get("size", 0))
                            result.append(m)
                        except Exception: pass
            return result
        return []

    def _import_mails_with_progress(self, mails: list, mode: str, progress_cb=None):
        total = max(len(mails), 1)

        if mode == STORAGE_SQLITE_ONE:
            conn = self._get_structure_conn()
            conn.execute("DELETE FROM mails")
            for i, m in enumerate(mails):
                self._insert_mail_row(conn, m)
                if progress_cb and i % 10 == 0:
                    progress_cb(35 + int(i/total*55), 100, f"Schreibe Mail {i+1}/{total}…")
            conn.commit()

        elif mode == STORAGE_SQLITE_PER_ACCOUNT:
            by_acc: dict = {}
            for m in mails:
                aid = self._account_id_for_folder(m.get("folder_id", 0)) or 0
                by_acc.setdefault(aid, []).append(m)
            done = 0
            for aid, ams in by_acc.items():
                conn = self._get_account_mail_conn(aid)
                conn.execute("DELETE FROM mails")
                for m in ams:
                    self._insert_mail_row(conn, m)
                    done += 1
                    if progress_cb and done % 10 == 0:
                        progress_cb(35 + int(done/total*55), 100, f"Schreibe Mail {done}/{total}…")
                conn.commit()

        elif mode == STORAGE_FILES:
            store = os.path.join(self.data_dir, "mailstore")
            os.makedirs(store, exist_ok=True)
            for i, m in enumerate(mails):
                self._write_mail_file(m, store)
                if progress_cb and i % 5 == 0:
                    progress_cb(35 + int(i/total*55), 100, f"Schreibe Datei {i+1}/{total}…")

    def _insert_mail_row(self, conn: sqlite3.Connection, m: dict):
        """Sicheres Einfügen: numerische Felder IMMER als Integer."""
        int_f = {"is_read", "is_flagged", "is_answered", "has_attach", "size"}
        fields = ["folder_id","uid","subject","sender","sender_name","recipients",
                  "cc","bcc","date","body_text","body_html","is_read","is_flagged",
                  "is_answered","has_attach","size","message_id","raw_path"]
        vals = []
        for f in fields:
            v = m.get(f)
            if f in int_f:
                vals.append(int(v) if v is not None and v != "" else 0)
            else:
                vals.append(str(v) if v is not None else "")
        conn.execute(
            f"INSERT INTO mails ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
            vals
        )

    def _recalculate_all_unread(self, mode: str):
        sc  = self._get_structure_conn()
        for (fid,) in sc.execute("SELECT id FROM folders").fetchall():
            if mode == STORAGE_FILES:
                count = 0
                for d in self._all_file_dirs(fid):
                    if not os.path.isdir(d): continue
                    for fn in os.listdir(d):
                        if fn.endswith(".json"):
                            try:
                                with open(os.path.join(d, fn), encoding="utf-8") as f:
                                    m = json.load(f)
                                if int(m.get("is_read", 0)) == 0:
                                    count += 1
                            except Exception: pass
            elif mode == STORAGE_SQLITE_PER_ACCOUNT:
                conn = self._mail_conn_for_folder(fid)
                r    = conn.execute(
                    "SELECT COUNT(*) FROM mails WHERE folder_id=? AND is_read=0",
                    (fid,)).fetchone()
                count = r[0] if r else 0
            else:
                r = sc.execute(
                    "SELECT COUNT(*) FROM mails WHERE folder_id=? AND is_read=0",
                    (fid,)).fetchone()
                count = r[0] if r else 0
            sc.execute("UPDATE folders SET unread=? WHERE id=?", (count, fid))
        sc.commit()

    # ------------------------------------------------------------------ #
    #  File-Backend                                                       #
    # ------------------------------------------------------------------ #

    def _mail_file_dir(self, folder_id: int) -> str:
        """
        Gibt den Verzeichnispfad für die Mails eines Ordners zurück.
        Struktur: mailstore/<account_email>/<folder_name>/
        Fallback: mailstore/<folder_id>/  (wenn Ordner/Konto nicht gefunden)
        """
        sc = self._get_structure_conn()
        row = sc.execute("""
            SELECT f.name, f.folder_type, mb.email, mb.account_id
            FROM folders f
            JOIN mailboxes mb ON f.mailbox_id = mb.id
            WHERE f.id = ?
        """, (folder_id,)).fetchone()

        if row:
            # Ordnername sauber machen (keine Sonderzeichen im Pfad)
            import re as _re
            folder_name = _re.sub(r'[\\/:*?"<>|]', '_', str(row["name"]))
            account_dir = _re.sub(r'[\\/:*?"<>|@]', '_', str(row["email"]))
            d = os.path.join(self.data_dir, "mailstore", account_dir, folder_name)
        else:
            # Fallback: nur folder_id (alte Daten)
            d = os.path.join(self.data_dir, "mailstore", str(folder_id))

        os.makedirs(d, exist_ok=True)
        return d

    def _mail_file_dir_legacy(self, folder_id: int) -> str:
        """Alter Pfad für Rückwärtskompatibilität beim Lesen."""
        return os.path.join(self.data_dir, "mailstore", str(folder_id))

    def _write_mail_file(self, m: dict, store_dir: str):
        """Schreibt JSON-Meta + RFC-2822-.eml-Datei in die korrekte Verzeichnisstruktur."""
        folder_id = int(m.get("folder_id", 0))
        # Nutze _mail_file_dir für korrekte account/folder-Struktur
        folder_dir = self._mail_file_dir(folder_id)

        mail_id = m.get("id") or hashlib.md5(
            f"{m.get('message_id','')}{m.get('date','')}".encode()).hexdigest()[:12]
        eml_path  = os.path.join(folder_dir, f"{mail_id}.eml")
        json_path = os.path.join(folder_dir, f"{mail_id}.json")

        # RFC-2822-Header
        def h(name, val): return f"{name}: {str(val or '').replace(chr(10),' ')}\n"
        sn = str(m.get("sender_name") or "")
        se = str(m.get("sender") or "")
        from_f = f"{sn} <{se}>" if sn else se
        headers  = h("From", from_f)
        headers += h("To",   m.get("recipients"))
        if m.get("cc"):  headers += h("Cc",  m["cc"])
        if m.get("bcc"): headers += h("Bcc", m["bcc"])
        headers += h("Subject",    m.get("subject"))
        headers += h("Date",       m.get("date"))
        if m.get("message_id"): headers += h("Message-ID", m["message_id"])
        headers += "MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n\n"

        with open(eml_path, "w", encoding="utf-8") as f:
            f.write(headers + str(m.get("body_text") or m.get("body_html") or ""))

        meta = {k: v for k, v in m.items() if k not in ("body_text","body_html")}
        # Numerische Felder als Integer speichern
        for int_k in ("is_read","is_flagged","is_answered","has_attach","size"):
            meta[int_k] = int(meta.get(int_k) or 0)
        meta["raw_path"] = eml_path
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, default=str)

    def _get_mails_from_files(self, folder_id: int) -> list:
        """Liest Mails – prüft neuen Pfad (account/folder) UND Legacy-Pfad (folder_id)."""
        dirs_to_check = []
        new_dir = self._mail_file_dir(folder_id)
        legacy_dir = self._mail_file_dir_legacy(folder_id)
        dirs_to_check.append(new_dir)
        if legacy_dir != new_dir and os.path.isdir(legacy_dir):
            dirs_to_check.append(legacy_dir)

        result = []
        for d in dirs_to_check:
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d), reverse=True):
                if fn.endswith(".json"):
                    try:
                        with open(os.path.join(d, fn), encoding="utf-8") as f:
                            meta = json.load(f)
                        meta["is_read"]    = int(meta.get("is_read", 0))
                        meta["is_flagged"] = int(meta.get("is_flagged", 0))
                        eml = os.path.join(d, fn.replace(".json", ".eml"))
                        if os.path.exists(eml):
                            with open(eml, encoding="utf-8", errors="replace") as f:
                                meta["body_text"] = self._parse_eml_body(f.read())
                        result.append(_DictRow(meta))
                    except Exception: pass
        return result

    def _get_mail_from_file(self, mail_id, folder_id: int):
        """Sucht eine Mail – prüft neuen Pfad UND Legacy-Pfad."""
        dirs_to_check = []
        new_dir = self._mail_file_dir(folder_id)
        legacy_dir = self._mail_file_dir_legacy(folder_id)
        dirs_to_check.append(new_dir)
        if legacy_dir != new_dir and os.path.isdir(legacy_dir):
            dirs_to_check.append(legacy_dir)

        for d in dirs_to_check:
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                if fn.endswith(".json"):
                    try:
                        with open(os.path.join(d, fn), encoding="utf-8") as f:
                            meta = json.load(f)
                        if str(meta.get("id")) == str(mail_id):
                            meta["is_read"]    = int(meta.get("is_read", 0))
                            meta["is_flagged"] = int(meta.get("is_flagged", 0))
                            eml = os.path.join(d, fn.replace(".json", ".eml"))
                            if os.path.exists(eml):
                                with open(eml, encoding="utf-8", errors="replace") as f:
                                    meta["body_text"] = self._parse_eml_body(f.read())
                            return _DictRow(meta)
                    except Exception: pass
        return None

    @staticmethod
    def _parse_eml_body(content: str) -> str:
        """Trennt RFC-2822-Header vom Body (durch \\n\\n)."""
        pos = content.find("\n\n")
        return content[pos+2:] if pos != -1 else content

    def _insert_mail_file(self, folder_id: int, data: dict) -> int:
        store = os.path.join(self.data_dir, "mailstore")
        ts  = datetime.now().strftime("%Y%m%d%H%M%S%f")
        mid = int(ts)
        self._write_mail_file({"id": mid, "folder_id": folder_id, **data}, store)
        return mid


    def _all_file_dirs(self, folder_id: int) -> list:
        """Gibt alle zu prüfenden Verzeichnisse zurück (neu + legacy)."""
        dirs = []
        new_dir = self._mail_file_dir(folder_id)
        legacy_dir = self._mail_file_dir_legacy(folder_id)
        dirs.append(new_dir)
        if legacy_dir != new_dir and os.path.isdir(legacy_dir):
            dirs.append(legacy_dir)
        return dirs

    def _update_mail_file_field(self, mail_id, folder_id: int, field: str, value):
        for d in self._all_file_dirs(folder_id):
            if not os.path.isdir(d): continue
            for fn in os.listdir(d):
                if fn.endswith(".json"):
                    path = os.path.join(d, fn)
                    try:
                        with open(path, encoding="utf-8") as f: meta = json.load(f)
                        if str(meta.get("id")) == str(mail_id):
                            meta[field] = value
                            with open(path, "w", encoding="utf-8") as f:
                                json.dump(meta, f, ensure_ascii=False)
                            return
                    except Exception: pass

    def _delete_mail_file(self, mail_id, folder_id: int):
        for d in self._all_file_dirs(folder_id):
            if not os.path.isdir(d): continue
            for fn in list(os.listdir(d)):
                if fn.endswith(".json"):
                    path = os.path.join(d, fn)
                    try:
                        with open(path, encoding="utf-8") as f: meta = json.load(f)
                        if str(meta.get("id")) == str(mail_id):
                            os.remove(path)
                            eml = path.replace(".json", ".eml")
                            if os.path.exists(eml): os.remove(eml)
                            return
                    except Exception: pass

    def _move_mail_file(self, mail_id, src_fid: int, tgt_fid: int):
        if not src_fid: return
        import shutil
        td = self._mail_file_dir(tgt_fid)
        for sd in self._all_file_dirs(src_fid):
            if not os.path.isdir(sd): continue
            for fn in list(os.listdir(sd)):
                if fn.endswith(".json"):
                    path = os.path.join(sd, fn)
                    try:
                        with open(path, encoding="utf-8") as f: meta = json.load(f)
                        if str(meta.get("id")) == str(mail_id):
                            meta["folder_id"] = tgt_fid
                            shutil.move(path, os.path.join(td, fn))
                            eml = path.replace(".json", ".eml")
                            if os.path.exists(eml):
                                shutil.move(eml, os.path.join(td, os.path.basename(eml)))
                            return
                    except Exception: pass

    @staticmethod
    def _parse_eml_body(content: str) -> str:
        pos = content.find("\n\n")
        return content[pos+2:] if pos != -1 else content

    # ------------------------------------------------------------------ #
    #  Konto-API                                                          #
    # ------------------------------------------------------------------ #


    def create_local_account(self, name: str, email: str) -> int:
        """Legt ein lokales Konto mit den 6 Standard-IMAP-Ordnern an."""
        data = {
            "id": None,
            "name": name, "email": email, "protocol": "LOCAL",
            "in_host": "", "in_port": 0, "in_ssl": 0,
            "out_host": "", "out_port": 0, "out_ssl": 0,
            "username": email, "password": "",
        }
        return self.save_account(data)

    def has_accounts(self) -> bool:
        """Gibt True zurück wenn mindestens ein Konto vorhanden ist."""
        row = self._get_accounts_conn().execute(
            "SELECT COUNT(*) FROM accounts"
        ).fetchone()
        return (row[0] if row else 0) > 0

    def get_accounts(self) -> list:
        return list(self._get_accounts_conn().execute(
            "SELECT * FROM accounts ORDER BY id").fetchall())

    def get_account(self, account_id: int):
        return self._get_accounts_conn().execute(
            "SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()

    def save_account(self, data: dict) -> int:
        conn = self._get_accounts_conn()
        if data.get("id"):
            # Bestehendes Konto aktualisieren
            conn.execute("""UPDATE accounts SET name=:name,email=:email,protocol=:protocol,
                in_host=:in_host,in_port=:in_port,in_ssl=:in_ssl,
                out_host=:out_host,out_port=:out_port,out_ssl=:out_ssl,
                username=:username,password=:password WHERE id=:id""", data)
            conn.commit()
            # Postfach-Anzeigenamen synchronisieren
            sc = self._get_structure_conn()
            sc.execute("UPDATE mailboxes SET name=?, email=? WHERE account_id=?",
                       (data["name"], data["email"], data["id"]))
            sc.commit()
            return data["id"]

        # Neues Konto anlegen
        cur = conn.execute("""INSERT INTO accounts
            (name,email,protocol,in_host,in_port,in_ssl,out_host,out_port,out_ssl,username,password)
            VALUES (:name,:email,:protocol,:in_host,:in_port,:in_ssl,
                    :out_host,:out_port,:out_ssl,:username,:password)""", data)
        conn.commit()
        account_id = cur.lastrowid

        # Postfach + IMAP-Standardordner in structure.db anlegen
        sc = self._get_structure_conn()
        sc.execute("INSERT INTO mailboxes (account_id,name,email) VALUES (?,?,?)",
                   (account_id, data["name"], data["email"]))
        mb_id = sc.execute("SELECT last_insert_rowid()").fetchone()[0]

        imap_folders = [
            ("Posteingang", "inbox"),  ("Gesendet",  "sent"),
            ("Entwürfe",    "drafts"), ("Papierkorb","trash"),
            ("Spam",        "spam"),   ("Archiv",    "archive"),
        ]
        for fname, ftype in imap_folders:
            sc.execute(
                "INSERT INTO folders (mailbox_id,parent_id,name,folder_type,unread) "
                "VALUES (?,NULL,?,?,0)",
                (mb_id, fname, ftype)
            )
        sc.commit()
        return account_id

    def delete_account(self, account_id: int):
        """Löscht Konto aus accounts.db und alle zugehörigen Daten aus structure.db."""
        # 1. Mails löschen (aus dem aktiven Backend)
        sc   = self._get_structure_conn()
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)

        # Alle Ordner-IDs für dieses Konto ermitteln
        folder_ids = [row[0] for row in sc.execute(
            "SELECT f.id FROM folders f "
            "JOIN mailboxes mb ON f.mailbox_id=mb.id "
            "WHERE mb.account_id=?", (account_id,)
        ).fetchall()]

        if mode == STORAGE_SQLITE_ONE:
            for fid in folder_ids:
                sc.execute("DELETE FROM mails WHERE folder_id=?", (fid,))
            sc.commit()
        elif mode == STORAGE_SQLITE_PER_ACCOUNT:
            db_file = os.path.join(self.data_dir, f"mailstore_{account_id}.db")
            if account_id in self._per_account_conns:
                try: self._per_account_conns[account_id].close()
                except Exception: pass
                del self._per_account_conns[account_id]
            if os.path.exists(db_file):
                try: os.remove(db_file)
                except OSError: pass
        elif mode == STORAGE_FILES:
            import shutil
            for fid in folder_ids:
                for d in self._all_file_dirs(fid):
                    if os.path.isdir(d):
                        shutil.rmtree(d, ignore_errors=True)

        # 2. Ordner und Postfach aus structure.db entfernen
        mb_ids = [row[0] for row in sc.execute(
            "SELECT id FROM mailboxes WHERE account_id=?", (account_id,)
        ).fetchall()]
        for mb_id in mb_ids:
            sc.execute("DELETE FROM folders WHERE mailbox_id=?", (mb_id,))
        sc.execute("DELETE FROM mailboxes WHERE account_id=?", (account_id,))
        sc.commit()

        # 3. Konto-Datensatz löschen
        self._get_accounts_conn().execute("DELETE FROM accounts WHERE id=?", (account_id,))
        self._get_accounts_conn().commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self._get_accounts_conn().execute(
            "SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self._get_accounts_conn().execute(
            "INSERT OR REPLACE INTO settings (key,value,updated_at) VALUES (?,?,datetime('now'))",
            (key, value))
        self._get_accounts_conn().commit()

    def is_first_run(self) -> bool:
        """True wenn noch keine Konten vorhanden sind (Ersteinrichtung)."""
        conn = self._get_accounts_conn()
        count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        return count == 0

    # ------------------------------------------------------------------ #
    #  Mail-Suche                                                         #
    # ------------------------------------------------------------------ #

    def search_mails(self, query: str, field: str = "all",
                     folder_id: int = None,
                     date_from: str = None, date_to: str = None) -> list:
        """
        Durchsucht Mails nach dem Suchbegriff.

        field: "all" | "subject" | "sender" | "recipient" | "body" | "date"
        folder_id: None = alle Ordner, sonst nur dieser Ordner
        date_from / date_to: "YYYY-MM-DD" Strings (optional, nur bei field="date")
        """
        mode = self.get_setting("mail_storage", STORAGE_SQLITE_ONE)

        if mode == STORAGE_FILES:
            return self._search_mails_files(query, field, folder_id, date_from, date_to)

        if mode == STORAGE_SQLITE_PER_ACCOUNT:
            results = []
            if folder_id:
                conn = self._mail_conn_for_folder(folder_id)
                results = self._search_mails_sql(conn, query, field, folder_id, date_from, date_to)
            else:
                for acc in self.get_accounts():
                    conn = self._get_account_mail_conn(acc["id"])
                    results += self._search_mails_sql(conn, query, field, None, date_from, date_to)
            return results

        # STORAGE_SQLITE_ONE
        conn = self._get_structure_conn()
        return self._search_mails_sql(conn, query, field, folder_id, date_from, date_to)

    def _search_mails_sql(self, conn, query: str, field: str,
                          folder_id: int, date_from: str, date_to: str) -> list:
        q   = f"%{query}%"
        conds = []
        params: list = []

        if field == "subject":
            conds.append("subject LIKE ?"); params.append(q)
        elif field == "sender":
            conds.append("(sender LIKE ? OR sender_name LIKE ?)"); params += [q, q]
        elif field == "recipient":
            conds.append("(recipients LIKE ? OR cc LIKE ?)"); params += [q, q]
        elif field == "body":
            conds.append("(body_text LIKE ? OR body_html LIKE ?)"); params += [q, q]
        elif field == "date":
            if date_from: conds.append("date >= ?"); params.append(date_from)
            if date_to:   conds.append("date <= ?"); params.append(date_to + " 23:59:59")
        else:  # "all"
            conds.append(
                "(subject LIKE ? OR sender LIKE ? OR sender_name LIKE ? "
                "OR recipients LIKE ? OR body_text LIKE ?)")
            params += [q, q, q, q, q]

        if folder_id:
            conds.append("folder_id = ?"); params.append(folder_id)

        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        return list(conn.execute(
            f"SELECT * FROM mails {where} ORDER BY date DESC LIMIT 500",
            params
        ).fetchall())

    def _search_mails_files(self, query: str, field: str,
                            folder_id: int, date_from: str, date_to: str) -> list:
        results = []
        store   = os.path.join(self.data_dir, "mailstore")
        if not os.path.isdir(store):
            return []
        q = query.lower()
        for root, _, files in os.walk(store):
            for fn in files:
                if not fn.endswith(".json"): continue
                try:
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        m = json.load(f)
                    if folder_id and m.get("folder_id") != folder_id:
                        continue
                    # Datum-Filter
                    if date_from or date_to:
                        d = str(m.get("date", ""))[:10]
                        if date_from and d < date_from: continue
                        if date_to   and d > date_to:   continue
                    # Feld-Filter
                    hit = False
                    if field == "subject":
                        hit = q in str(m.get("subject","")).lower()
                    elif field == "sender":
                        hit = q in str(m.get("sender","")).lower() or \
                              q in str(m.get("sender_name","")).lower()
                    elif field == "recipient":
                        hit = q in str(m.get("recipients","")).lower()
                    elif field == "body":
                        hit = q in str(m.get("body_text","")).lower()
                    elif field == "date":
                        hit = True  # Datum-Filter oben bereits angewendet
                    else:  # all
                        hit = any(q in str(m.get(k,"")).lower()
                                  for k in ("subject","sender","sender_name","recipients","body_text"))
                    if hit:
                        results.append(_DictRow(m))
                except Exception:
                    pass
        results.sort(key=lambda m: str(m.get("date") or ""), reverse=True)
        return results[:500]

    # ------------------------------------------------------------------ #
    #  Mail kopieren                                                      #
    # ------------------------------------------------------------------ #

    def copy_mail(self, mail_id: int, target_folder_id: int,
                  source_folder_id: int = None) -> int:
        """
        Kopiert eine Mail in einen anderen Ordner.
        Gibt die ID der neuen Mail zurück.
        """
        mail = self.get_mail(mail_id, source_folder_id)
        if not mail:
            return -1
        data = dict(mail)
        data.pop("id", None)
        data.pop("created_at", None)
        data["folder_id"] = target_folder_id
        return self.insert_mail(target_folder_id, data)


class _DictRow(dict):
    """sqlite3.Row-kompatibler dict für das File-Backend."""
    def __getitem__(self, key):
        return super().get(key)
