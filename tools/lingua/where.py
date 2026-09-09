"""The one state line, and the one next-action ladder.

"Where am I, and what should I do next" is the question every surface answers
differently today: `status` prints a table with no legend and no next step,
`check` never says "ok", and the CLI's scattered hints contradict the skills
they point at. This module is the single generator; the CLI, the skills and
the SessionStart hook all print what it returns, byte-identical.

The ladder is a precedence list, not a menu. Its last rung is the design in
one string: when production is done, the next thing is study.
"""

from .status import STATES, state_summary

VERBS = ("/ch:mount", "/ch:translate", "/ch:verify", "/ch:calibrate")

STATE_LEGEND = (
    "ok = every anchor pinned to the chapter's current content_hash · "
    "stale = the chapter changed since these entries were anchored · "
    "none = no entries anchored here"
)

def cmd(rest: str) -> str:
    """Voice law 1: every printed hint is runnable exactly as printed.
    `./ch` and `uv run python -m tools.lingua` are the same entry point; the
    short form is what gets printed, because a hint nobody can paste is not
    a hint."""
    return f"./ch {rest}"


MOUNT_HINT = (
    "no corpora mounted under corpora/ — run /ch:mount <repo-url> in Claude "
    "Code to mount one"
)


def _run_state(bundle) -> tuple[bool, bool]:
    """(a triage-worthy failure exists, a redefinition gate is open)."""
    from . import author as authormod
    work = authormod.work_dir(bundle)
    failures = work / "failures.json"
    gated = work / "gated"
    bounced = False
    if failures.exists():
        try:
            newest = max(
                (p.stat().st_mtime for p in (work / "results").glob("*.json")),
                default=0.0)
            bounced = failures.stat().st_mtime >= newest
        except OSError:
            bounced = True
    held = gated.is_dir() and any(gated.glob("*.json"))
    return bounced, held


def next_action(bundle) -> str:
    """The ladder, for one register. Rungs 1-2 are handled by `lines()`."""
    key = f"{bundle.corpus.name}/{bundle.corpus.register}"
    bounced, held = _run_state(bundle)
    if bounced:
        return f"/ch:verify {key}"
    if held:
        return f"/ch:translate {key}   (redefinition gate open)"
    stale = False
    first_none = None
    for chapter in bundle.corpus.chapters:
        for state in bundle.chapter_states(chapter).values():
            if state == "stale":
                stale = True
            elif state == "none" and first_none is None:
                first_none = chapter.id
    if stale:
        return f"/ch:translate {key}"
    if first_none:
        return f"/ch:translate {first_none}"
    return f"/ch:calibrate {key}"


def state_line(bundle) -> str:
    """One register, one line — the string every surface prints."""
    key = f"{bundle.corpus.name}/{bundle.corpus.register}"
    counters = bundle.state_counters()
    parts = [
        f"{slug} {state_summary(counters[slug]) or '-'}"
        for slug in bundle.tracked_modes if slug in counters
    ]
    body = " · ".join(
        [key, f"{len(bundle.corpus.chapters)} chapters", *parts]
        or [key])
    return f"{body} · next: {next_action(bundle)}"


def lines(bundles, warnings: list[str] | None = None) -> list[str]:
    """The full orientation block: one line per register, plus the rungs that
    are about the tree rather than a register (nothing mounted, half-mounted)."""
    out: list[str] = []
    for warning in warnings or []:
        if "run /mount" in warning or "run /ch:mount" in warning:
            out.append(f"incomplete mount · {warning}")
    if not bundles:
        out.append(MOUNT_HINT)
        return out
    out += [state_line(b) for b in bundles]
    return out


def print_where(bundles, warnings: list[str] | None = None) -> int:
    for line in lines(bundles, warnings):
        print(line)
    return 0
