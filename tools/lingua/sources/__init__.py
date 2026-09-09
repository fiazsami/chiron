"""Reusable building blocks for corpus adapters.

Each mounted corpus carries a per-register adapter at
corpora/<name>/<vN>/tools/adapter.py exposing scan(cfg, root) -> Corpus.
Most adapters delegate to a module here (markdown for doc corpora, codetree
for undocumented code repos) in four lines; bespoke corpora write their own
scan against tools/lingua/model.py.
"""
