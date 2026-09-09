"""Render one curated flow lane as a standalone SVG document.

Lanes are strictly linear step sequences; the only non-linear constructs are
row wrapping (when a lane is wider than the content area) and dashed loop
back-edges. Layout is computed in plain Python so output is deterministic.
"""

from dataclasses import dataclass

# Palette inherited from the original notes design; kept for continuity.
PINE = "#1f5d4c"
STONE = "#f6f4ef"
NODE_FILL = "#eae6da"
AMBER = "#c17c3a"
INK = "#23211c"
PINE_TINT = "#d9e5df"
AMBER_TINT = "#f0dcc3"
PAPER = "#fbfaf7"

NODE_H = 56
GAP = 36
MAX_ROW_W = 920
LM = 30  # left margin: channel for wrap and loop routing
RM = 30
LINE_H = 15
CHAR_W = 7.0


@dataclass
class _Node:
    label: str
    kind: str
    lines: list[str]
    w: float = 0
    x: float = 0
    y: float = 0
    row: int = 0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + NODE_H / 2


def _wrap(label: str, limit: int = 22) -> list[str]:
    if len(label) <= limit + 2:
        return [label]
    lines, current = [], ""
    for word in label.split():
        if current and len(current) + 1 + len(word) > limit:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines[:3]


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _node_shape(n: _Node) -> str:
    x, y, w, h = n.x, n.y, n.w, NODE_H
    base = f'stroke-width="1.5"'
    if n.kind == "model":
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{PINE}" stroke="{PINE}" {base}/>'
    if n.kind == "agent":
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{PINE_TINT}" stroke="{PINE}" stroke-width="2"/>'
    if n.kind in ("input", "output"):
        fill, stroke = ("#ffffff", PINE) if n.kind == "input" else (AMBER_TINT, AMBER)
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{fill}" stroke="{stroke}" {base}/>'
    if n.kind == "store":
        ry = 9
        body = (
            f'M {x},{y + ry} A {w / 2},{ry} 0 0 1 {x + w},{y + ry} '
            f'L {x + w},{y + h - ry} A {w / 2},{ry} 0 0 1 {x},{y + h - ry} Z'
        )
        rim = f'M {x},{y + ry} A {w / 2},{ry} 0 0 0 {x + w},{y + ry}'
        return (
            f'<path d="{body}" fill="{NODE_FILL}" stroke="{PINE}" {base}/>'
            f'<path d="{rim}" fill="none" stroke="{PINE}" {base}/>'
        )
    if n.kind == "guard":
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{AMBER_TINT}" stroke="{AMBER}" stroke-width="2"/>'
    if n.kind == "decision":
        c = 14
        pts = (
            f"{x + c},{y} {x + w - c},{y} {x + w},{y + h / 2} "
            f"{x + w - c},{y + h} {x + c},{y + h} {x},{y + h / 2}"
        )
        return f'<polygon points="{pts}" fill="{NODE_FILL}" stroke="{PINE}" {base}/>'
    if n.kind == "data":
        fold = 12
        doc = f'M {x},{y} L {x + w - fold},{y} L {x + w},{y + fold} L {x + w},{y + h} L {x},{y + h} Z'
        crease = f'M {x + w - fold},{y} L {x + w - fold},{y + fold} L {x + w},{y + fold}'
        return (
            f'<path d="{doc}" fill="{PAPER}" stroke="{PINE}" {base}/>'
            f'<path d="{crease}" fill="none" stroke="{PINE}" stroke-width="1"/>'
        )
    if n.kind == "tool":
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{NODE_FILL}" stroke="{PINE}" {base}/>'
            f'<line x1="{x + 6}" y1="{y}" x2="{x + 6}" y2="{y + h}" stroke="{PINE}" stroke-width="1"/>'
            f'<line x1="{x + w - 6}" y1="{y}" x2="{x + w - 6}" y2="{y + h}" stroke="{PINE}" stroke-width="1"/>'
        )
    if n.kind in ("server", "external"):
        stroke = PINE if n.kind == "server" else "#8a8577"
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{STONE}" '
            f'stroke="{stroke}" stroke-width="1.5" stroke-dasharray="5 3"/>'
        )
    if n.kind == "embed":
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{PINE_TINT}" stroke="{PINE}" {base}/>'
    # process and anything else
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{NODE_FILL}" stroke="{PINE}" {base}/>'


def _node_text(n: _Node) -> str:
    color = STONE if n.kind == "model" else INK
    count = len(n.lines)
    spans = []
    for i, line in enumerate(n.lines):
        y = n.cy + (i - (count - 1) / 2) * LINE_H + 4.5
        spans.append(
            f'<tspan x="{n.cx}" y="{y}">{_esc(line)}</tspan>'
        )
    return (
        f'<text text-anchor="middle" font-size="13" fill="{color}" '
        f'font-family="ui-sans-serif, system-ui, sans-serif">{"".join(spans)}</text>'
    )


def render_lane(lane: dict, uid: str) -> str:
    steps = lane["steps"]
    loops = lane.get("loops") or []
    nodes = []
    for step in steps:
        lines = _wrap(step["label"])
        w = max(96.0, min(250.0, 28 + CHAR_W * max(len(line) for line in lines)))
        nodes.append(_Node(step["label"], step["kind"], lines, w=w))

    # Row layout with wrapping.
    top_pad = 40 if loops else 10
    row_pitch = NODE_H + 44 + (26 if loops else 0)
    x, row = LM, 0
    for n in nodes:
        if x > LM and x + n.w > LM + MAX_ROW_W:
            row += 1
            x = LM
        n.x, n.row = x, row
        n.y = top_pad + row * row_pitch
        x = n.x + n.w + GAP

    marker = f"ah-{uid}"
    parts = [
        f'<defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{AMBER}"/></marker></defs>'
    ]
    edge_attrs = f'fill="none" stroke="{AMBER}" stroke-width="1.8" marker-end="url(#{marker})"'

    # Edges between consecutive nodes.
    for a, b in zip(nodes, nodes[1:]):
        if a.row == b.row:
            parts.append(
                f'<line x1="{a.x + a.w}" y1="{a.cy}" x2="{b.x - 2}" y2="{b.cy}" {edge_attrs}/>'
            )
        else:
            mid_y = a.y + NODE_H + 22
            pts = (
                f"{a.x + a.w},{a.cy} {a.x + a.w + 14},{a.cy} {a.x + a.w + 14},{mid_y} "
                f"{LM - 14},{mid_y} {LM - 14},{b.cy} {b.x - 2},{b.cy}"
            )
            parts.append(f'<polyline points="{pts}" {edge_attrs}/>')

    # Dashed loop back-edges.
    loop_attrs = (
        f'fill="none" stroke="{AMBER}" stroke-width="1.6" stroke-dasharray="6 4" '
        f'marker-end="url(#{marker})"'
    )
    for loop in loops:
        src, dst = nodes[loop["from"]], nodes[loop["to"]]
        label = loop.get("label", "")
        if src.row == dst.row:
            top = src.y - 24
            pts = f"{src.cx},{src.y} {src.cx},{top} {dst.cx},{top} {dst.cx},{dst.y - 3}"
            label_x, label_y = (src.cx + dst.cx) / 2, top - 7
        else:
            below = src.y + NODE_H + 16
            above = dst.y - 18
            pts = (
                f"{src.cx},{src.y + NODE_H} {src.cx},{below} {LM - 22},{below} "
                f"{LM - 22},{above} {dst.cx},{above} {dst.cx},{dst.y - 3}"
            )
            label_x, label_y = (LM - 22 + src.cx) / 2, below + 13
        parts.append(f'<polyline points="{pts}" {loop_attrs}/>')
        if label:
            parts.append(
                f'<text x="{label_x}" y="{label_y}" text-anchor="middle" font-size="11.5" '
                f'font-style="italic" fill="{AMBER}" '
                f'font-family="ui-sans-serif, system-ui, sans-serif">{_esc(label)}</text>'
            )

    for n in nodes:
        parts.append(_node_shape(n))
        parts.append(_node_text(n))

    width = max(n.x + n.w for n in nodes) + RM
    height = max(n.y for n in nodes) + NODE_H + (34 if loops else 14)
    # Standalone-file requirements: xmlns (inline SVG inherits it, files don't),
    # explicit width/height for <img> sizing, and an opaque background so the
    # diagram stays legible on dark-mode viewers like GitHub.
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" '
        f'aria-label="Flow: {_esc(lane["name"])}">'
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{PAPER}"/>'
        f'{"".join(parts)}</svg>'
    )


def kinds_used(flow_entry: dict) -> list[str]:
    seen: list[str] = []
    for lane in flow_entry.get("flows") or []:
        for step in lane["steps"]:
            if step["kind"] not in seen:
                seen.append(step["kind"])
    return seen
