"""
auto_fetch.py – Hintergrund-Thread für automatisches Mail-Abrufen.

Pro IMAP/POP3-Konto läuft ein eigener Thread der in konfigurierbaren
Intervallen neue Mails abruft und das Ergebnis via wx.CallAfter
an den Haupt-Thread übergibt (UI-Thread-sicher).
"""

from __future__ import annotations
import threading
import time
import wx
from core.protocol_runner import log


class AutoFetchThread(threading.Thread):
    """
    Prüft in regelmäßigen Abständen ob neue Mails vorhanden sind.
    Läuft als Daemon-Thread – wird beim App-Ende automatisch beendet.
    """

    def __init__(self, controller, account_id: int, interval_min: int,
                 on_new_mails):
        """
        controller:    AppController-Instanz
        account_id:    ID des Kontos (None = alle)
        interval_min:  Prüfintervall in Minuten
        on_new_mails:  Callable(count: int) – wird im Haupt-Thread aufgerufen
        """
        super().__init__(daemon=True)
        self.controller   = controller
        self.account_id   = account_id
        self.interval_min = max(1, interval_min)
        self.on_new_mails = on_new_mails
        self._stop_event  = threading.Event()

    def stop(self):
        """Thread sanft beenden."""
        self._stop_event.set()

    def run(self):
        acc_name = self.account_id or "all"
        log("info", f"AutoFetch start: account={acc_name} interval={self.interval_min}min")
        while not self._stop_event.is_set():
            # Warten – in 5s-Schritten damit stop() schnell reagiert
            for _ in range(self.interval_min * 12):  # 12 × 5s = 1 Minute
                if self._stop_event.is_set():
                    break
                time.sleep(5)

            if self._stop_event.is_set():
                break

            log("info", f"AutoFetch check: account={acc_name}")
            try:
                count = self.controller.fetch_new_mails(
                    account_id=self.account_id
                )
                if count > 0:
                    log("info", f"AutoFetch: {count} neue Mail(s) für account={acc_name}")
                    wx.CallAfter(self.on_new_mails, count)
            except Exception as e:
                log("error", f"AutoFetch error (account={acc_name}): {e}")

        log("info", f"AutoFetch stopped: account={acc_name}")


class AutoFetchManager:
    """
    Verwaltet alle AutoFetch-Threads.
    Startet/stoppt Threads wenn Einstellungen geändert werden.
    """

    def __init__(self):
        self._threads: dict[int | None, AutoFetchThread] = {}

    def start(self, controller, interval_min: int, on_new_mails):
        """
        Startet Auto-Fetch-Threads für alle IMAP/POP3-Konten.
        Bestehende Threads werden zuerst gestoppt.
        """
        self.stop_all()

        accs = [
            dict(a) for a in controller.get_accounts()
            if dict(a).get("protocol", "LOCAL") not in ("LOCAL",)
            and dict(a).get("in_host")
        ]

        if not accs:
            log("info", "AutoFetchManager: keine Mail-Konten → kein Auto-Fetch")
            return

        for acc in accs:
            t = AutoFetchThread(
                controller=controller,
                account_id=acc["id"],
                interval_min=interval_min,
                on_new_mails=on_new_mails,
            )
            t.start()
            self._threads[acc["id"]] = t
            log("info", f"AutoFetch started for account={acc['name']} ({interval_min}min)")

    def stop_all(self):
        """Alle laufenden Threads beenden."""
        for t in self._threads.values():
            t.stop()
        self._threads.clear()

    def is_running(self) -> bool:
        return bool(self._threads)
