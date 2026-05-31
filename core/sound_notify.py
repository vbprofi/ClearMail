"""
sound_notify.py – Ton-Benachrichtigung bei neuen Mails.

Unterstützte Modi:
  1. WAV-Datei  – beliebige .wav über Dateipfad
  2. Systemton  – plattformspezifischer Standard-Benachrichtigungston
  3. Einfacher Piepton – winsound.Beep(freq, ms) / ALSA beep

Plattform-Matrix:
  Windows  – winsound.PlaySound (WAV) / winsound.MessageBeep / winsound.Beep
  macOS    – afplay (WAV) / osascript beep
  Linux    – aplay / paplay / pacat (WAV) / beep / print \a

Alle Operationen laufen in Daemon-Threads (fire-and-forget),
blockieren die UI nie und schlucken Fehler still.
"""

from __future__ import annotations
import sys
import os
import threading
from core.protocol_runner import log


def play_notification(controller) -> None:
    """
    Spielt den konfigurierten Benachrichtigungston ab.
    Liest Einstellungen aus dem Controller und startet einen Daemon-Thread.
    NUR aufrufen wenn tatsächlich neue Mails eingegangen sind.
    """
    mode     = controller.get_setting("sound_mode",    "none")  # none|system|beep|wav
    if mode == "none":
        return

    wav_path = controller.get_setting("sound_wav_path", "")
    freq     = int(controller.get_setting("sound_beep_freq",   "880"))
    duration = int(controller.get_setting("sound_beep_dur_ms", "200"))

    def _play():
        try:
            if mode == "wav" and wav_path and os.path.isfile(wav_path):
                _play_wav(wav_path)
            elif mode == "system":
                _play_system()
            elif mode == "beep":
                _play_beep(freq, duration)
        except Exception as e:
            log("warning", f"sound_notify: {e}")

    threading.Thread(target=_play, daemon=True).start()


# ------------------------------------------------------------------ #
#  Interne Abspielfunktionen                                          #
# ------------------------------------------------------------------ #

def _play_wav(path: str) -> None:
    """Spielt eine WAV-Datei plattformübergreifend ab."""
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["afplay", path])
    else:
        # Linux: aplay → paplay → pacat → sox play
        import subprocess
        for cmd in (["aplay", "-q", path],
                    ["paplay", path],
                    ["pacat", "--playback", path]):
            try:
                subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue
        log("warning", "sound_notify: kein WAV-Player gefunden (aplay/paplay/pacat)")


def _play_system() -> None:
    """Plattform-Systemton (wie E-Mail-Eingang in Thunderbird)."""
    if sys.platform == "win32":
        import winsound
        # MB_ICONASTERISK = 0x40 → Informations-Systemton
        winsound.MessageBeep(0x00000040)
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["osascript", "-e", "beep 1"])
    else:
        # Linux: pacat mit kurzer Sinuswelle, Fallback auf \a
        try:
            import subprocess, struct, math
            rate   = 22050
            dur_s  = 0.18
            freq   = 880
            n      = int(rate * dur_s)
            data   = bytes(
                struct.pack("<h", int(32767 * math.sin(2 * math.pi * freq * i / rate)))
                for i in range(n)
            )
            # raw signed 16-bit mono → pacat
            proc = subprocess.Popen(
                ["pacat", "--playback", "--format=s16le",
                 "--rate=22050", "--channels=1"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            proc.communicate(data)
        except Exception:
            # Letzter Fallback: Terminal-Beep
            print("\a", end="", flush=True)


def _play_beep(freq: int, duration_ms: int) -> None:
    """Einfacher Piepton mit konfigurierbarer Frequenz und Länge."""
    if sys.platform == "win32":
        import winsound
        winsound.Beep(max(37, min(32767, freq)), max(10, duration_ms))
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["osascript", "-e", f"beep 1"])
    else:
        try:
            import subprocess
            subprocess.Popen(
                ["beep", "-f", str(freq), "-l", str(duration_ms)],
                stderr=subprocess.DEVNULL
            )
        except FileNotFoundError:
            # Fallback: pacat mit synthetischem Ton (gleiche Logik wie _play_system)
            try:
                import struct, math, subprocess
                rate = 22050
                n    = int(rate * duration_ms / 1000)
                data = bytes(
                    struct.pack("<h", int(32767 * math.sin(2 * math.pi * freq * i / rate)))
                    for i in range(n)
                )
                proc = subprocess.Popen(
                    ["pacat", "--playback", "--format=s16le",
                     "--rate=22050", "--channels=1"],
                    stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
                )
                proc.communicate(data)
            except Exception:
                print("\a", end="", flush=True)


def test_sound(mode: str, wav_path: str = "",
               freq: int = 880, duration_ms: int = 200) -> None:
    """
    Spielt einen Testton ab – direkt ohne Controller.
    Wird aus dem Einstellungsdialog aufgerufen.
    """
    def _play():
        try:
            if mode == "wav":
                if wav_path and os.path.isfile(wav_path):
                    _play_wav(wav_path)
                else:
                    log("warning", f"sound_notify test: WAV nicht gefunden: {wav_path!r}")
            elif mode == "system":
                _play_system()
            elif mode == "beep":
                _play_beep(freq, duration_ms)
        except Exception as e:
            log("warning", f"sound_notify test: {e}")
    threading.Thread(target=_play, daemon=True).start()
