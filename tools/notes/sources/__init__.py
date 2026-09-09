"""Shared building blocks for corpus adapters.

Each mounted corpus carries a per-register adapter at
corpora/<name>/<vN>/tools/adapter.py (exposing scan(cfg, root) -> Corpus),
authored by the /mount skill and loaded dynamically by
tools.notes.corpora.load_adapter. The modules here are the reusable pieces
adapters import:

- base: frontmatter/H1/mermaid/paragraph extraction, text fingerprinting
- markdown: a complete generic adapter for <group>/<doc>.md shaped repos
"""
