# MailClient

Screenreader-optimierter E-Mail-Client in Python 3.12 + wxPython.  
Outlook-Express/Thunderbird-ähnliches Layout, MVC-Architektur, modular und erweiterbar.

---

## Projektstruktur

```
mailclient/
├── main.py                     ← Einstiegspunkt
├── requirements.txt
│
├── core/
│   ├── app_controller.py       ← MVC-Controller
│   └── addon_manager.py        ← Addon-System
│
├── database/
│   └── db_manager.py           ← SQLite-Datenbankmanager
│                                  (accounts.db + mailstore.db)
│
├── ui/
│   ├── main_frame.py           ← Hauptfenster (MVC-View)
│   ├── folder_panel.py         ← Linke Seite: Ordnerbaum
│   ├── mail_list_panel.py      ← Rechts oben: Mail-Liste
│   ├── mail_preview_panel.py   ← Rechts unten: Mail-Vorschau
│   └── dialogs.py              ← Alle Dialoge
│
├── protocols/
│   ├── imap_handler.py         ← IMAP (Grundstruktur, vorbereitet)
│   └── pop3_smtp_handler.py    ← POP3 + SMTP (vorbereitet)
│
└── addons/
    └── mail_logger/            ← Beispiel-Addon
        └── __init__.py
```

---

## Installation

```bash
pip install wxPython
```

Optional für erweiterte IMAP-Funktionen:
```bash
pip install imapclient
```

## Starten

```bash
cd mailclient
python main.py
```

---

## Tastaturbedienung (Screenreader-optimiert)

| Taste            | Funktion                                          |
|------------------|---------------------------------------------------|
| **F6**           | Nächsten Bereich fokussieren (Ordner → Liste → Vorschau) |
| **Shift+F6**     | Vorherigen Bereich fokussieren                    |
| **Tab**          | In der Vorschau: zwischen Von/An/CC/Betreff/Text  |
| **F5**           | Aktuellen Ordner aktualisieren                    |
| **F9**           | E-Mails abrufen (wenn IMAP/POP3 implementiert)    |
| **Entf**         | Ausgewählte Mail löschen                          |
| **Ctrl+N**       | Neue Mail verfassen                               |
| **Ctrl+R**       | Antworten                                         |
| **Ctrl+Shift+R** | Allen antworten                                   |
| **Ctrl+L**       | Weiterleiten                                      |
| **Ctrl+S**       | Als .email speichern                              |
| **Ctrl+O**       | .email-Datei öffnen                               |
| **Ctrl+P**       | Druckansicht                                      |
| **Ctrl+F**       | Suchen (noch nicht implementiert)                 |
| **Applikationstaste** | Kontextmenü in Mail-Liste                    |

---

## Datenbanken

Beide SQLite-Datenbanken liegen in `~/.mailclient/`:

### `accounts.db` – Konten & Einstellungen
- `accounts` – Konto-Daten inkl. verschlüsseltem Passwort
- `settings` – Key-Value-Einstellungen
- `addon_registry` – registrierte Addons

### `mailstore.db` – Mails, Postfächer, Ordner
- `mailboxes` – Postfächer (je Konto)
- `folders`   – Ordnerstruktur (INBOX, Gesendet, Entwürfe, Papierkorb, Spam, Archiv + benutzerdefinierte)
- `mails`     – E-Mails mit allen Metadaten und Body
- `attachments` – Anhänge (BLOB)

---

## Protokoll-Implementierung

### IMAP (`protocols/imap_handler.py`)
- Grundstruktur vorhanden (`IMAPHandler`)
- Hilfsmethoden `decode_header_value()` und `parse_email_message()` bereits implementiert
- Zu implementierende Methoden sind mit `raise NotImplementedError` markiert
- Nutzung in `AppController.fetch_new_mails()`

### POP3 (`protocols/pop3_smtp_handler.py`)
- `POP3Handler.connect()` und `disconnect()` implementiert
- `fetch_mail()` noch zu implementieren

### SMTP (`protocols/pop3_smtp_handler.py`)
- `SMTPHandler.send()` vollständig vorbereitet
- `_build_message()` (MIME, Anhänge) implementiert
- Kann direkt mit echten Zugangsdaten getestet werden

---

## Addon-System

Addons liegen in `~/.mailclient/addons/<name>/__init__.py`  
und definieren eine Klasse `Addon(AddonBase)`.

### Verfügbare Hooks

```python
from core.addon_manager import AddonBase

class Addon(AddonBase):
    NAME        = "MeinAddon"
    VERSION     = "1.0.0"
    DESCRIPTION = "Beschreibung"

    def on_load(self): ...
    def on_unload(self): ...
    def on_mail_read(self, data): ...
    def on_mail_deleted(self, data): ...
    def on_mail_moved(self, data): ...
    def on_mail_sent(self, data): ...
    def on_mail_received(self, data): ...

    def get_menu_items(self) -> list:
        return [{"label": "Mein Menüeintrag", "handler": callable}]

    def on_pgp_decrypt(self, mail_data): return mail_data
    def on_pgp_encrypt(self, mail_data): return mail_data
```

### Beispiel-Addon
Das Addon `addons/mail_logger/` demonstriert das System.  
Kopieren Sie es nach `~/.mailclient/addons/mail_logger/`.

---

## Datei-Formate

| Format | Beschreibung |
|--------|-------------|
| `.email` | JSON-Datei mit allen Mail-Feldern (öffnen/speichern via Menü) |
| `.txt`   | Klartext-Export einer Mail |

---

## Geplante Erweiterungen

- [ ] IMAP-Synchronisation (Ordner + Mails)
- [ ] POP3-Abruf
- [ ] SMTP-Versand mit UI-Feedback
- [ ] OpenPGP via python-gnupg
- [ ] HTML-Mail-Rendering (wx.html2.WebView)
- [ ] Volltextsuche in Mails
- [ ] Druckunterstützung (wx.Printer)
- [ ] Benachrichtigungen bei neuen Mails
- [ ] IMAP IDLE (Push-Benachrichtigungen)
- [ ] Adressbuch / Kontakte
