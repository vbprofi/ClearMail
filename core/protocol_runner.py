"""
protocol_runner.py – Thread-basierter Runner für IMAP/POP3/SMTP-Operationen.

Verhindert das Einfrieren der UI bei Netzwerk-Operationen.
Schreibt optional ein Debug-Log (einstellbar in Einstellungen → Entwickler).
"""

import threading
import logging
import os
import sys
from datetime import datetime
from typing import Callable, Optional

import wx


# ------------------------------------------------------------------ #
#  Logging                                                            #
# ------------------------------------------------------------------ #

_logger: Optional[logging.Logger] = None


def setup_logging(log_path: str):
    """Aktiviert das Verbindungs-Logging in eine Datei."""
    global _logger
    _logger = logging.getLogger("clearmail.protocol")
    _logger.setLevel(logging.DEBUG)
    _logger.handlers.clear()
    try:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        _logger.addHandler(fh)
        _logger.info("=== ClearMail Protokoll-Log gestartet ===")
    except OSError:
        _logger = None


def disable_logging():
    global _logger
    if _logger:
        for h in _logger.handlers[:]:
            h.close()
            _logger.removeHandler(h)
    _logger = None


def log(level: str, msg: str):
    """Schreibt einen Log-Eintrag wenn Logging aktiv."""
    if _logger:
        getattr(_logger, level, _logger.info)(msg)


def get_log_path(data_dir: str) -> str:
    return os.path.join(data_dir, "protocol.log")


# ------------------------------------------------------------------ #
#  Worker-Thread                                                      #
# ------------------------------------------------------------------ #

class ProtocolWorker(threading.Thread):
    """
    Führt eine Netzwerk-Operation in einem Hintergrund-Thread aus.
    Meldet Fortschritt und Ergebnis thread-sicher via wx.CallAfter.

    on_progress(msg: str)                  – Statuszeile aktualisieren
    on_done(count: int)                    – Erfolg
    on_error(error: str, is_auth: bool)    – Fehler (is_auth=True bei Auth-Fehlern)
    """

    def __init__(self,
                 fn: Callable,
                 on_progress: Callable[[str], None],
                 on_done:     Callable[[int], None],
                 on_error:    Callable[[str, bool], None]):
        super().__init__(daemon=True)
        self.fn          = fn
        self.on_progress = on_progress
        self.on_done     = on_done
        self.on_error    = on_error

    def run(self):
        try:
            result = self.fn(progress_cb=self._progress)
            wx.CallAfter(self.on_done, result)
        except Exception as e:
            msg     = str(e)
            is_auth = any(w in msg.lower() for w in
                          ("authentication", "login", "password",
                           "credentials", "auth", "anmeld", "passwort",
                           "unauthorized", "535", "534", "430"))
            log("error", f"Protokoll-Fehler: {msg}")
            wx.CallAfter(self.on_error, msg, is_auth)

    def _progress(self, msg: str, pct: int = -1, total: int = 0):
        """pct=-1 → kein Prozentwert verfügbar (unbestimmt)."""
        log("info", msg)
        wx.CallAfter(self.on_progress, msg, pct, total)
