"""
Protokoll-Stubs – Platzhalter für IMAP, POP3 und SMTP
Diese Dateien definieren die Schnittstellen, die später implementiert werden.

Dateistruktur:
  protocols/
    __init__.py
    imap_handler.py   (diese Datei als Vorlage)
    pop3_handler.py
    smtp_handler.py
    base_handler.py
"""

# =====================================================================
# base_handler.py (Inhalt)
# =====================================================================

BASE_HANDLER_CODE = '''"""
BaseHandler – Abstrakte Basisklasse für alle Protokoll-Handler
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BaseIncomingHandler(ABC):
    """Abstrakte Basisklasse für Eingangs-Protokolle (IMAP, POP3)."""

    def __init__(self, host: str, port: int, username: str, password: str, use_ssl: bool = True):
        self.host     = host
        self.port     = port
        self.username = username
        self.password = password
        self.use_ssl  = use_ssl
        self._conn    = None

    @abstractmethod
    def connect(self) -> bool:
        """Verbindung zum Server herstellen. Gibt True bei Erfolg zurück."""
        pass

    @abstractmethod
    def disconnect(self):
        """Verbindung trennen."""
        pass

    @abstractmethod
    def list_folders(self) -> List[Dict]:
        """Gibt eine Liste aller Ordner zurück."""
        pass

    @abstractmethod
    def fetch_mail_list(self, folder: str, since=None) -> List[Dict]:
        """Gibt eine Liste der Mail-Metadaten zurück."""
        pass

    @abstractmethod
    def fetch_mail(self, uid: str, folder: str) -> Optional[Dict]:
        """Lädt den vollständigen Inhalt einer Mail."""
        pass

    @abstractmethod
    def mark_read(self, uid: str, folder: str):
        pass

    @abstractmethod
    def delete_mail(self, uid: str, folder: str):
        pass


class BaseOutgoingHandler(ABC):
    """Abstrakte Basisklasse für Ausgangs-Protokolle (SMTP)."""

    def __init__(self, host: str, port: int, username: str, password: str, use_ssl: bool = True):
        self.host     = host
        self.port     = port
        self.username = username
        self.password = password
        self.use_ssl  = use_ssl

    @abstractmethod
    def send(self, from_addr: str, to_addrs: List[str], message) -> bool:
        """Sendet eine Mail. Gibt True bei Erfolg zurück."""
        pass
'''
