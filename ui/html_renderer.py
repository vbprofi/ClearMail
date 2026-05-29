"""
html_renderer.py – HTML-Darstellung für Mails

Backends (in Priorität):
  1. wx.html2.WebView  – Edge/WebKit (Windows: Edge WebView2, Linux: WebKitGTK)
  2. wx.html.HtmlWindow – leichtes wx-eigenes HTML-Rendering (HTML3/CSS2)
  3. wx.TextCtrl       – Plaintext-Fallback

Vorschau-Panel:  immer html_to_text()  (reiner Text, kein Widget-Wechsel)
Viewer-Fenster:  HTML-Widget wenn render_html=1 und body_html vorhanden
"""

from __future__ import annotations
import re, html as _html_mod
from html.parser import HTMLParser


# ------------------------------------------------------------------ #
#  HTML → Text (keine externen Bibliotheken)                          #
# ------------------------------------------------------------------ #

class _HtmlToTextParser(HTMLParser):
    # Block-Elemente → Zeilenumbruch
    BLOCK = {"p","div","br","h1","h2","h3","h4","h5","h6",
              "li","tr","blockquote","pre","hr","article","section",
              "header","footer","nav","figure","figcaption","td","th"}

    # Container-Skip: Inhalt UND alle Kind-Tags werden übersprungen
    # NUR echte Container (haben öffnendes UND schließendes Tag)
    SKIP_CONTAINER = {"script","style","head","noscript","iframe",
                      "object","embed","svg","canvas","select"}

    # Void-Elemente: selbst-schließend, kein Endtag, kein Inhalt zu skippen
    VOID = {"area","base","br","col","embed","hr","img","input",
            "link","meta","param","source","track","wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._pre_depth  = 0

    def handle_starttag(self, tag, attrs):
        t = tag.lower()

        # Void-Elemente: niemals skip_depth erhöhen
        if t in self.VOID:
            if not self._skip_depth:
                if t == "br":  self._parts.append("\n")
                if t == "hr":  self._parts.append("\n" + "─"*40 + "\n")
                if t == "img":
                    alt = next((v for n,v in attrs if n=="alt"), "")
                    if alt: self._parts.append(f"[Bild: {alt}]")
            return

        # Container-Skip
        if t in self.SKIP_CONTAINER:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if t == "pre":
            self._pre_depth += 1

        if t in self.BLOCK:
            self._parts.append("\n")

        if t == "a":
            for name, val in attrs:
                if name == "href" and val and val.startswith("http"):
                    self._parts.append(f" [{val}]")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.VOID:
            return  # Void-Elemente haben kein Endtag → ignorieren
        if t in self.SKIP_CONTAINER:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if t == "pre":
            self._pre_depth = max(0, self._pre_depth - 1)
        if t in self.BLOCK:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._pre_depth:
            self._parts.append(data)
        else:
            text = re.sub(r"[ \t]+", " ", data)
            text = re.sub(r"\n+",    " ", text)
            self._parts.append(text)

    def get_text(self) -> str:
        raw   = "".join(self._parts)
        raw   = re.sub(r"\n{3,}", "\n\n", raw)
        lines = [l.strip() for l in raw.splitlines()]
        # Leere Zeilen am Anfang/Ende entfernen, max. 1 Leerzeile zwischen Blöcken
        result = []
        prev_empty = True
        for line in lines:
            if line:
                result.append(line)
                prev_empty = False
            elif not prev_empty:
                result.append("")
                prev_empty = True
        return "\n".join(result).strip()


def html_to_text(html_str: str) -> str:
    if not html_str or not html_str.strip(): return ""
    if "<" not in html_str: return html_str
    try:
        p = _HtmlToTextParser()
        p.feed(html_str)
        result = p.get_text()
        return result if result else html_str
    except Exception:
        return re.sub(r"<[^>]+>", "", html_str).strip()


# ------------------------------------------------------------------ #
#  Backend-Erkennung                                                  #
# ------------------------------------------------------------------ #

def detect_best_backend() -> str:
    """
    Ermittelt das beste verfügbare HTML-Backend.
    Gibt 'webview', 'htmlwindow' oder 'textctrl' zurück.
    Wird einmalig beim Import gecacht.
    """
    try:
        import wx.html2
        # Prüfen ob das Backend tatsächlich initialisierbar ist
        # (auf manchen Systemen importierbar aber nicht nutzbar)
        if hasattr(wx.html2, 'WebView'):
            return "webview"
    except Exception:
        pass
    try:
        import wx.html
        if hasattr(wx.html, 'HtmlWindow'):
            return "htmlwindow"
    except Exception:
        pass
    return "textctrl"


# Einmal erkennen, dann cachen
_BEST_BACKEND: str | None = None

def get_backend() -> str:
    global _BEST_BACKEND
    if _BEST_BACKEND is None:
        _BEST_BACKEND = detect_best_backend()
    return _BEST_BACKEND


# ------------------------------------------------------------------ #
#  Widget erstellen                                                   #
# ------------------------------------------------------------------ #

def create_html_widget(parent) -> tuple:
    """
    Erstellt das HTML-Widget für den angegebenen Parent.
    Gibt (widget, backend_name) zurück.

    WICHTIG: Bei WebView muss SetPage() NACH Show() aufgerufen werden.
    """
    backend = get_backend()

    if backend == "webview":
        try:
            import wx.html2
            ctrl = wx.html2.WebView.New(parent)
            ctrl.SetName("HTML-Darstellung")
            return ctrl, "webview"
        except Exception:
            pass  # Fallback

    if backend in ("webview", "htmlwindow"):
        try:
            import wx.html
            ctrl = wx.html.HtmlWindow(
                parent,
                style=wx.html.HW_SCROLLBAR_AUTO | wx.BORDER_SUNKEN
            )
            ctrl.SetName("HTML-Darstellung")
            # Standard-Schrift anpassen
            ctrl.SetStandardFonts(14)
            return ctrl, "htmlwindow"
        except Exception:
            pass

    # Letzter Fallback: TextCtrl
    import wx
    ctrl = wx.TextCtrl(
        parent,
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN
    )
    ctrl.SetName("Nachrichtentext")
    return ctrl, "textctrl"


# ------------------------------------------------------------------ #
#  Inhalt setzen                                                      #
# ------------------------------------------------------------------ #

def set_html_content(widget, html_str: str, backend: str, base_url: str = ""):
    """Setzt HTML-Inhalt je nach Backend."""
    prepared = _prepare_html(html_str)
    try:
        if backend == "webview":
            widget.SetPage(prepared, base_url or "about:blank")
        elif backend == "htmlwindow":
            widget.SetPage(prepared)
        else:
            # TextCtrl-Fallback
            widget.SetValue(html_to_text(html_str))
            widget.SetInsertionPoint(0)
    except Exception as e:
        # Wenn das Widget das HTML nicht verarbeiten kann → Plaintext
        try:
            if hasattr(widget, 'SetValue'):
                widget.SetValue(html_to_text(html_str))
        except Exception:
            pass


def set_text_content(widget, text: str, backend: str):
    """Setzt reinen Text ins HTML-Widget (als formatiertes HTML verpackt)."""
    escaped = _html_mod.escape(text or "")
    if backend == "webview":
        page = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
                f'body{{font-family:-apple-system,"Segoe UI",Arial,sans-serif;'
                f'font-size:14px;line-height:1.5;padding:12px;white-space:pre-wrap;}}'
                f'</style></head><body>{escaped}</body></html>')
        try: widget.SetPage(page, "about:blank")
        except Exception: pass
    elif backend == "htmlwindow":
        page = f'<html><body><pre style="font-size:12pt">{escaped}</pre></body></html>'
        try: widget.SetPage(page)
        except Exception: pass
    else:
        try: widget.SetValue(text or ""); widget.SetInsertionPoint(0)
        except Exception: pass


# ------------------------------------------------------------------ #
#  HTML aufbereiten (Thunderbird-ähnliches CSS injizieren)           #
# ------------------------------------------------------------------ #

_BASE_CSS = """
<style type="text/css">
body {
  font-family: -apple-system, "Segoe UI", Arial, Helvetica, sans-serif;
  font-size: 14px; line-height: 1.6; color: #222; background: #fff;
  padding: 12px 18px; margin: 0; max-width: 100%;
  word-wrap: break-word; overflow-wrap: break-word;
}
a { color: #0078d4; }
a:visited { color: #551a8b; }
blockquote {
  border-left: 3px solid #999; margin: 8px 0 8px 4px;
  padding: 4px 0 4px 12px; color: #555;
}
pre, code {
  font-family: "Cascadia Code", Consolas, "Courier New", monospace;
  font-size: 13px; background: #f4f4f4;
  padding: 2px 4px; border-radius: 3px;
}
pre { padding: 10px; overflow-x: auto; white-space: pre-wrap; }
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; max-width: 100%; }
td, th { padding: 4px 8px; }
hr { border: none; border-top: 1px solid #ddd; margin: 12px 0; }
</style>
"""

_CHARSET = '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'


def _prepare_html(html_str: str) -> str:
    """Bereitet HTML-Mail für die Anzeige vor (CSS + Charset injizieren)."""
    if not html_str:
        return "<html><body></body></html>"

    has_html = bool(re.search(r"<html[\s>]", html_str, re.IGNORECASE))
    has_head = bool(re.search(r"<head[\s>]",  html_str, re.IGNORECASE))

    if has_html and has_head:
        # CSS nach <head> injizieren
        return re.sub(
            r"(<head[^>]*>)",
            r"\1\n" + _CHARSET + "\n" + _BASE_CSS,
            html_str, count=1, flags=re.IGNORECASE
        )
    elif has_html:
        # <html> ohne <head>
        return re.sub(
            r"(<html[^>]*>)",
            r"\1\n<head>\n" + _CHARSET + "\n" + _BASE_CSS + "\n</head>\n",
            html_str, count=1, flags=re.IGNORECASE
        )
    else:
        # Nur Fragment
        return (f"<!DOCTYPE html><html><head>\n{_CHARSET}\n{_BASE_CSS}"
                f"</head><body>\n{html_str}\n</body></html>")
