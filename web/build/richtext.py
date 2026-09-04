"""Unity rich text -> safe HTML, preserving the game's own colours.

Skill descriptions use Unity rich-text markup:
    <color=#439ed1>Water</color>   element / emphasis colour
    <link=N>...</link>             a game keyword, explained by the skill's
                                   HyperLinkDatas[N] -> entry table row
    <u> <b> <i>                    plain formatting

A keyword is only highlighted when we can actually explain it; otherwise it
renders as ordinary text rather than promising a tooltip that isn't there.
"""
from __future__ import annotations
import html
import re

_HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_TAG = re.compile(r"<[^>]+>")
_NUM = re.compile(r"(?<![\w#])(\d+(?:\.\d+)?%?)")
_LINK = re.compile(r"&lt;link=(\d+)&gt;(.*?)&lt;/link&gt;", re.S)


def _highlight_numbers(htmltext: str) -> str:
    """Wrap numbers in the text parts only, never inside an HTML tag."""
    out, pos = [], 0
    for m in _TAG.finditer(htmltext):
        out.append(_NUM.sub(r'<span class="dnum">\1</span>', htmltext[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_NUM.sub(r'<span class="dnum">\1</span>', htmltext[pos:]))
    return "".join(out)


def _inner_tags(t: str) -> str:
    """Convert the non-link markup inside an already-escaped fragment."""
    def _color(m):
        c = m.group(1)
        return f'<span style="color:{c}">' if _HEX.match(c) else "<span>"
    t = re.sub(r"&lt;color=(#[0-9a-fA-F]{3,8})&gt;", _color, t)
    t = t.replace("&lt;/color&gt;", "</span>")
    for tag in ("u", "b", "i"):
        t = t.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return re.sub(r"&lt;/?[a-zA-Z][^&]*?&gt;", "", t)


def richtext(raw: str, links=None) -> str:
    if not raw:
        return ""
    links = links or []
    t = html.escape(raw)

    def _link(m):
        n = int(m.group(1))
        inner = _inner_tags(m.group(2))
        target = links[n] if n < len(links) else None
        if not target or not target.get("name"):
            return inner                      # nothing to explain: plain text
        tip = target["name"]
        if target.get("desc"):
            tip += " — " + target["desc"]
        return (f'<span class="kw" tabindex="0" role="note" '
                f'data-tip="{html.escape(tip, quote=True)}">{inner}</span>')

    t = _LINK.sub(_link, t)
    t = _inner_tags(t)
    return _highlight_numbers(t).strip()
