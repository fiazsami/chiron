"""The language census: what a corpus is made of, before anything is generated.

This exists so tool selection is grounded rather than guessed. The planning
agent reads the census and picks from the closed registry; the gate prints the
same census so the human is judging the same evidence the agent judged.

It is a file read, so it is the CLI's job — not the model's. Read-only,
stdlib, and cheap enough to run at a gate.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..gittree import SKIP_DIRS
from . import TOOLS, ToolSpec

# Doc-comment openers, per extension family. Presence, not correctness — the
# census answers "does this repo document itself at all", which is exactly the
# question that decides whether generating docs is worth doing.
DOC_MARKERS: dict[str, tuple[str, ...]] = {
    ".ts": ("/**", "///"), ".tsx": ("/**", "///"),
    ".mts": ("/**",), ".cts": ("/**",),
    ".js": ("/**",), ".jsx": ("/**",),
    ".py": ('"""', "'''"), ".pyi": ('"""',),
    ".go": ("//",),
    ".rs": ("///", "//!"),
    ".java": ("/**",), ".kt": ("/**",),
    ".c": ("/**", "///"), ".h": ("/**", "///"),
    ".cc": ("/**", "///"), ".cpp": ("/**", "///"), ".cxx": ("/**", "///"),
    ".hpp": ("/**", "///"), ".hh": ("/**", "///"), ".hxx": ("/**", "///"),
}
# Enough to judge density without reading a whole monorepo.
SAMPLE_CAP = 400
PROSE_EXTENSIONS = (".md", ".mdx", ".rst", ".adoc", ".txt")


@dataclass
class Candidate:
    tool: str
    label: str
    files: int  # source files this tool would serve
    documented: int  # how many of them carry a doc comment
    manifests: list[str] = field(default_factory=list)

    @property
    def density(self) -> float:
        return self.documented / self.files if self.files else 0.0

    def to_dict(self) -> dict:
        return {
            "tool": self.tool, "label": self.label, "files": self.files,
            "documented": self.documented, "density": round(self.density, 3),
            "manifests": self.manifests,
        }


@dataclass
class Census:
    root: Path
    extensions: dict[str, int]
    prose_files: int
    prose_bytes: int
    code_files: int
    code_bytes: int
    manifests: list[str]
    candidates: list[Candidate]
    truncated: bool = False

    @property
    def prose_ratio(self) -> float:
        """Prose bytes as a share of prose+code. The number that answers
        'is this repo already documented enough to mount as-is'."""
        total = self.prose_bytes + self.code_bytes
        return self.prose_bytes / total if total else 0.0

    def to_dict(self) -> dict:
        return {
            "extensions": self.extensions,
            "prose": {"files": self.prose_files, "bytes": self.prose_bytes},
            "code": {"files": self.code_files, "bytes": self.code_bytes},
            "prose_ratio": round(self.prose_ratio, 3),
            "manifests": self.manifests,
            "candidates": [c.to_dict() for c in self.candidates],
            "truncated": self.truncated,
        }


def _documented(path: Path, markers: tuple[str, ...]) -> bool:
    try:
        with path.open("r", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 800:
                    return False
                if line.lstrip().startswith(markers):
                    return True
    except OSError:
        return False
    return False


def census(root: Path) -> Census:
    """Walk a source tree and report what a generator would find in it."""
    extensions: dict[str, int] = {}
    manifests: set[str] = set()
    per_tool_files: dict[str, list[Path]] = {slug: [] for slug in TOOLS}
    prose_files = prose_bytes = code_files = code_bytes = 0

    manifest_names = {m for spec in TOOLS.values() for m in spec.manifests}
    by_ext: dict[str, list[ToolSpec]] = {}
    for spec in TOOLS.values():
        for ext in spec.extensions:
            by_ext.setdefault(ext, []).append(spec)

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(p.startswith(".") or p in SKIP_DIRS for p in rel.parts[:-1]):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        if path.name in manifest_names:
            manifests.add(rel.as_posix())
        ext = path.suffix.lower()
        extensions[ext] = extensions.get(ext, 0) + 1
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if ext in PROSE_EXTENSIONS:
            prose_files += 1
            prose_bytes += size
        elif ext in by_ext:
            code_files += 1
            code_bytes += size
            for spec in by_ext[ext]:
                per_tool_files[spec.slug].append(path)

    truncated = False
    candidates: list[Candidate] = []
    for slug, files in per_tool_files.items():
        if not files:
            continue
        spec = TOOLS[slug]
        sample = files[:SAMPLE_CAP]
        truncated = truncated or len(sample) < len(files)
        documented = sum(
            1 for p in sample
            if _documented(p, DOC_MARKERS.get(p.suffix.lower(), ()))
        )
        # Scale the sampled count back up so `documented` reads against `files`.
        if sample and len(sample) < len(files):
            documented = round(documented * len(files) / len(sample))
        candidates.append(Candidate(
            tool=slug, label=spec.label, files=len(files), documented=documented,
            manifests=sorted(m for m in manifests if Path(m).name in spec.manifests),
        ))

    # Most files first, then better-documented — the order a human should read.
    candidates.sort(key=lambda c: (-c.files, -c.density))
    return Census(
        root=root, extensions=dict(sorted(extensions.items())),
        prose_files=prose_files, prose_bytes=prose_bytes,
        code_files=code_files, code_bytes=code_bytes,
        manifests=sorted(manifests), candidates=candidates, truncated=truncated,
    )


def render(c: Census, name: str) -> str:
    """The census as the gate prints it. Every tool slug shown here is a slug
    a recipe may name — the registry is closed, and this is where it is
    published to the agent that must choose from it."""
    out = [f"census {name} · {c.root}", ""]
    top = [f"{ext or '(none)'} {n}" for ext, n in
           sorted(c.extensions.items(), key=lambda kv: -kv[1])[:12]]
    out.append(f"  files      {sum(c.extensions.values())} · " + " · ".join(top))
    out.append(
        f"  prose      {c.prose_files} files, {c.prose_bytes:,} bytes "
        f"({c.prose_ratio:.0%} of prose+code)"
    )
    out.append(f"  code       {c.code_files} files, {c.code_bytes:,} bytes")
    out.append(f"  manifests  {', '.join(c.manifests) if c.manifests else '(none)'}")
    out.append("")
    if not c.candidates:
        out.append("  no candidate tool serves this tree — mount against source/")
        return "\n".join(out)
    out.append("  candidates (tool · files · documented · manifests)")
    for cand in c.candidates:
        out.append(
            f"    {cand.tool:<15} {cand.files:>5}  {cand.density:>5.0%}  "
            f"{', '.join(cand.manifests) or '—'}"
        )
    out.append("")
    out.append("  options per tool")
    for cand in c.candidates:
        spec = TOOLS[cand.tool]
        for opt_name, opt in sorted(spec.options.items()):
            flag = "required" if opt.required else f"default {opt.default!r}"
            out.append(f"    {cand.tool}.{opt_name:<20} {opt.kind.__name__:<5} {flag}")
    if c.truncated:
        out.append("")
        out.append(f"  note: doc density sampled over the first {SAMPLE_CAP} files per tool")
    return "\n".join(out)


def render_json(c: Census) -> str:
    return json.dumps(c.to_dict(), indent=2, sort_keys=False)
