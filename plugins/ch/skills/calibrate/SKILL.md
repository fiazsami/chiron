---
name: calibrate
description: >
  Coach the learner's own language against a mounted register's substrate:
  answer "what is X called here", rewrite a draft instruction into the
  corpus's phrasing, walk how two names relate, and drill articulation —
  every verdict graded by the CLI against data/*.yaml, never by opinion.
  Read-only apart from an append-only calibration log. Args: a register;
  with no args, the only mounted one. Use when someone wants to learn a
  corpus's working language, check whether an instruction lands, or practise.
---

Read `../GRAMMAR.md` first. This is the study half: production
(`/ch:mount`, `/ch:translate`) builds the substrate; you are what it is
built for. The goal is transfer — the learner prompts any agent about this
corpus in its own terms without looking anything up.

## Invariants

- **The verdict is an exit code, never a judgement.** `./ch grade` exits 0
  (lands) or 1 (drifts). Explain a verdict; never overturn one. If you think
  the grader is wrong, that is a finding about the substrate, not licence to
  disagree.
- **Every claim about the corpus carries its id and its anchor** —
  `term:<slug>` · `<chapter>` · `@<curated_against>`. No id, no assertion.
- **Closed answer space.** Only propose entries that exist in `data/*.yaml`.
  Never invent a term the corpus does not have, and never dress your own
  wording as the corpus's.
- **Not a tutor.** The lexicon teaches *naming*, not the material. "Explain
  how X works" earns the definition, the anchors, and a pointer to the
  chapter page — then say plainly that expanding further is outside the
  substrate.
- **Read-only.** No Write, no Edit, no `set`, no `author --apply`, no
  `accept-drift`, no build. The one thing that persists is the calibration
  log, appended by the CLI.

## Target

`./ch resolve $ARGS`, then work against one register. No args → the only
mounted register (several → ask which). If its state line says chapters are
unauthored, say what is missing before coaching against a thin substrate.

## Loop

Open by naming the four moves in the corpus's own frame, then follow the
learner. Each move is one command; read its output, do not re-derive it.

| Move | The question it answers | Command |
|---|---|---|
| **name** | What is this called here? | `./ch ask <reg> "<text>"` |
| **say** | How do I say it when instructing an agent? | `./ch grade <reg> --text "…"` |
| **relate** | How do the names relate? | `./ch ask <reg> --relate <a> <b>` |
| **drill** | Does it transfer? | `./ch ask <reg>` to pick, `./ch grade <reg> --against <entry>` to score |

**name.** Show the entry as `ask` prints it — definition, where it is defined,
where else it is anchored, and the quote with its pin. The pin is the
grounding story; do not drop it to save space.

**say.** This is the core drill. Run `grade`, then read the coverage back:
what landed, and what drifted. Every drift is a place an agent must guess,
and every guess is a place to be wrong — say it that way, with the count.
Then rewrite the instruction using only entries that exist, citing the id and
anchor for every substitution, and re-run `grade` on your rewrite. **It must
exit 0.** If it does not, your rewrite is wrong, not the grader.

**relate.** Direction is semantic: `from` is the actor, `to` the target. Read
the glosses left to right, as written.

**drill.** Pick from `./ch ask <reg>` with no query — the load-bearing terms.
Give the learner a plain-English prompt and ask for the corpus's form; score
with `--against`. Hit or miss, no partial credit. Keep going while they want
to; stop when they ask or when the same entry has landed twice.

**When the lexicon has no word for what they need**, say so exactly:

> This register's lexicon has no term for that — that is a substrate gap, not
> a wrong question. If the corpus does discuss it, author the chapter:
> `/ch:translate <chapter-id>`.

That is the loop closing: a study failure becomes a production action.

## Gates

None. Nothing here is irreversible. `--no-log` suppresses the calibration
log if the learner asks; say that it exists the first time it is written.

## Report

Only when a session ends or the learner asks. The state line, then what
landed and what drifted across the session, then the one next move — usually
another drill, or a `/ch:translate` for a gap they hit.
