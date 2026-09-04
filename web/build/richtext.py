"""Unity rich text -> safe HTML, preserving the game's own colours.

The game's skill descriptions use Unity's rich-text markup:
    <color=#439ed1>Water</color>   element / emphasis colour
    <link=0>...</link>             a game keyword (grid, Blind, airborne ...)
    <u> <b> <i>                    plain formatting
Everything else Unity-specific is dropped, keeping the inner text.
"""
from __future__ import annotations
import html
import re

_HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_TAG = re.compile(r"<[^>]+>")
_NUM = re.compile(r"(?<![\w#])(\d+(?:\.\d+)?%?)")


def _highlight_numbers(htmltext: str) -> str:
    """Wrap numbers in the *text* parts only, never inside an HTML tag."""
    out, pos = [], 0
    for m in _TAG.finditer(htmltext):
        chunk = htmltext[pos:m.start()]
        out.append(_NUM.sub(r'<span class="dnum">\1</span>', chunk))
        out.append(m.group(0))
        pos = m.end()
    out.append(_NUM.sub(r'<span class="dnum">\1</span>', htmltext[pos:]))
    return "".join(out)


def richtext(raw: str) -> str:
    if not raw:
        return ""
    t = html.escape(raw)

    def _color(m):
        c = m.group(1)
        return f'<span style="color:{c}">' if _HEX.match(c) else "<span>"

    t = re.sub(r"&lt;color=(#[0-9a-fA-F]{3,8})&gt;", _color, t)
    t = t.replace("&lt;/color&gt;", "</span>")
    t = re.sub(r"&lt;link=\d+&gt;", '<span class="kw">', t)
    t = t.replace("&lt;/link&gt;", "</span>")
    for tag in ("u", "b", "i"):
        t = t.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    # drop any remaining Unity tags (indent, line-height, size, sprite, ...)
    t = re.sub(r"&lt;/?[a-zA-Z][^&]*?&gt;", "", t)
    t = _highlight_numbers(t)
    return t.strip()
