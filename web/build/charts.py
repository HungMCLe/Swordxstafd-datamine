"""Small inline-SVG chart helpers. No library, no external requests."""
from __future__ import annotations
import html


def _nice(v):
    a = abs(v)
    if a >= 1_000_000:
        return f"{v/1_000_000:.1f}M".replace(".0M", "M")
    if a >= 1_000:
        return f"{v/1_000:.0f}K"
    if a >= 10:
        return f"{v:.0f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def line_chart(series, *, width=680, height=300, xlabel="", ylabel="",
               xticks=None, yfmt=_nice, xfmt=_nice, pad=(52, 16, 38, 16),
               marks=None, ymin=None, ymax=None, caption=""):
    """series: [{"name","colour","points":[(x,y),...],"dash":bool}]"""
    pl, pr, pb, pt = pad
    W, H = width, height
    xs = [x for s in series for x, _ in s["points"]]
    ys = [y for s in series for _, y in s["points"]]
    if not xs:
        return ""
    x0, x1 = min(xs), max(xs)
    y0 = 0 if ymin is None else ymin
    y1 = (max(ys) if ymax is None else ymax) or 1
    y1 *= 1.08
    if x1 == x0:
        x1 = x0 + 1

    def px(x):
        return pl + (x - x0) / (x1 - x0) * (W - pl - pr)

    def py(y):
        return H - pb - (y - y0) / (y1 - y0) * (H - pb - pt)

    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" '
           f'aria-label="{html.escape(caption or ylabel)}">']
    # horizontal gridlines
    for i in range(5):
        y = y0 + (y1 - y0) * i / 4
        out.append(f'<line class="grid" x1="{pl}" x2="{W-pr}" y1="{py(y):.1f}" y2="{py(y):.1f}"/>')
        out.append(f'<text class="tick" x="{pl-8}" y="{py(y)+4:.1f}" text-anchor="end">{yfmt(y)}</text>')
    # x ticks
    for x in (xticks if xticks is not None else
              [x0 + (x1 - x0) * i / 5 for i in range(6)]):
        out.append(f'<text class="tick" x="{px(x):.1f}" y="{H-pb+18}" text-anchor="middle">{xfmt(x)}</text>')
    out.append(f'<line class="axis" x1="{pl}" x2="{W-pr}" y1="{H-pb}" y2="{H-pb}"/>')
    for s in series:
        d = " ".join(("M" if i == 0 else "L") + f"{px(x):.1f} {py(y):.1f}"
                     for i, (x, y) in enumerate(s["points"]))
        dash = ' stroke-dasharray="5 4"' if s.get("dash") else ""
        out.append(f'<path d="{d}" fill="none" stroke="{s["colour"]}" stroke-width="2.2"{dash}/>')
    for m in (marks or []):
        out.append(f'<line class="mark" x1="{px(m["x"]):.1f}" x2="{px(m["x"]):.1f}" '
                   f'y1="{pt}" y2="{H-pb}"/>')
        out.append(f'<text class="marklabel" x="{px(m["x"])+6:.1f}" y="{pt+13}">'
                   f'{html.escape(m["label"])}</text>')
    if ylabel:
        out.append(f'<text class="axlabel" x="{pl}" y="{pt-2}">{html.escape(ylabel)}</text>')
    if xlabel:
        out.append(f'<text class="axlabel" x="{W-pr}" y="{H-4}" text-anchor="end">{html.escape(xlabel)}</text>')
    out.append("</svg>")
    legend = "".join(
        f'<span class="key"><i style="background:{s["colour"]}"></i>{html.escape(s["name"])}</span>'
        for s in series if s.get("name"))
    return (f'<figure class="chartbox">{"".join(out)}'
            + (f'<div class="legend">{legend}</div>' if legend else "")
            + (f'<figcaption>{caption}</figcaption>' if caption else "")
            + "</figure>")


def bar_chart(rows, *, width=680, barh=30, gap=11, fmt=_nice, caption="", labelw=190):
    """rows: [{"label","value","colour","note"}] — horizontal bars."""
    if not rows:
        return ""
    mx = max(abs(r["value"]) for r in rows) or 1
    H = len(rows) * (barh + gap) + 8
    inner = width - labelw - 76
    out = [f'<svg viewBox="0 0 {width} {H}" class="chart" role="img" '
           f'aria-label="{html.escape(caption)}">']
    for i, r in enumerate(rows):
        y = i * (barh + gap) + 4
        w = max(1.0, abs(r["value"]) / mx * inner)
        out.append(f'<text class="barlabel" x="{labelw-10}" y="{y+barh*0.68:.0f}" '
                   f'text-anchor="end">{html.escape(r["label"])}</text>')
        out.append(f'<rect x="{labelw}" y="{y}" width="{w:.1f}" height="{barh}" rx="4" '
                   f'fill="{r.get("colour", "var(--gold-rail)")}"/>')
        out.append(f'<text class="barval" x="{labelw + w + 9:.1f}" y="{y+barh*0.68:.0f}">'
                   f'{html.escape(fmt(r["value"]))}</text>')
    out.append("</svg>")
    return (f'<figure class="chartbox">{"".join(out)}'
            + (f'<figcaption>{caption}</figcaption>' if caption else "") + "</figure>")
