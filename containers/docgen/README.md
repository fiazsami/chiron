# containers/docgen

The image `ch doc` runs. It is the only part of chiron that needs Docker —
`./ch`, `./ch check` and the test suite all run without it.

## Why a container, and why no host fallback

A derived tree's bytes feed every chapter's `content_hash`, and every anchor
is pinned to that hash. doxygen 1.9 and 1.11 do not agree on those bytes;
typedoc stamps its own version into a footer. If chiron fell back to whatever
was on your PATH, "stale" would come to mean "you changed machines", and the
drift signal would stop meaning anything.

One digest-pinned image is what lets generated material participate in the
state model at all. `ch doc` refuses to run without one rather than producing
a tree it cannot account for.

## What is in it

| Tool | Serves | Output |
|---|---|---|
| `typedoc` + `typedoc-plugin-markdown` | TypeScript, JavaScript | Markdown natively |
| `pydoc-markdown` | Python | Markdown natively |
| `gomarkdoc` | Go | Markdown natively |
| `doxygen` → XML → `moxygen` | C, C++ | Markdown via one converter |

All four are verified end to end against real code, each proving determinism
by generating twice: pydoc-markdown, typedoc, doxygen→moxygen, and gomarkdoc.

`moxygen` rather than the more common `doxybook2`: doxybook2 publishes an
amd64-only binary, and this image has to build on arm64 too. moxygen is
JavaScript, so it runs wherever node does — and node is already here.

**Doxide** is the other credible C++ path and emits Markdown natively, but it
needs a source build (cmake, libclang, yaml-cpp, ICU) this image does not
carry. It is left out of the tool registry rather than listed-and-broken.

## Build it

```bash
docker build -t chiron-docgen:dev containers/docgen/
export CHIRON_DOCGEN_IMAGE=chiron-docgen:dev
```

Roughly 2.6 GB and a few minutes. `CHIRON_DOCGEN_IMAGE` accepts a plain tag:
`ch doc` resolves whatever it is given to a concrete digest before the recipe
records it, so a locally built image pins to its image id and a pulled one
pins to its registry digest. Either way the recipe records the bytes that ran,
never a moving name.

## Things the tools insist on

Three constraints cost a rebuild each to discover, and are load-bearing:

- **Generators must own their output directory.** typedoc deletes and
  recreates it before writing, which cannot work on a bind-mount point — it
  warns "Could not empty the output directory" and then silently produces
  nothing. So every tool writes to `/tmp/gen` and the entrypoint copies the
  result into `/out`. For the same reason the recipe is mounted at
  `/recipe.json`, never placed inside `/out`.
- **typedoc's `--disableGit` requires `--sourceLinkTemplate`.** Using
  `{path}#L{line}` gives source-relative links with no checkout state in
  them, which is both reproducible and exactly what chiron parses back into
  an upstream URL.
- **moxygen must not be given `--groups`** unless the project uses
  `@defgroup`; it exits 1 when asked for groups it cannot find. `--classes
  --anchors --noindex` gives one page per class and no giant `api.md`.

## Publish one

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t ghcr.io/<owner>/chiron-docgen:<version> --push containers/docgen/
docker buildx imagetools inspect ghcr.io/<owner>/chiron-docgen:<version>
```

Take the digest and set `DEFAULT_IMAGE` in `tools/lingua/docgen/runner.py`.
Until one is published that constant is `None`, and `ch doc` says so.

## The contract with chiron

The recipe is the whole interface. chiron validates it against the closed
registry in `tools/lingua/docgen/__init__.py`, mounts it read-only at `/recipe.json`,
and the entrypoint decides how to invoke the tool. One schema between them —
versioned, and stamped on the image as `org.chiron.recipe-schema`. `ch doc`
refuses an image whose label disagrees with its own `SCHEMA_VERSION`.

This is also the injection boundary: a planning agent proposes a recipe, never
a command. Nothing free-form reaches a shell on either side.

## How it is run

```
docker run --rm --network none --user <uid>:<gid> --read-only \
  --mount type=bind,src=<corpus>/source,dst=/src,ro \
  --mount type=bind,src=<corpus>/.staging/<recipe>,dst=/out \
  --tmpfs /tmp:exec --memory 2g --cpus 2 --pids-limit 512 \
  <image@sha256:...> <tool>
```

`--rm` is the destroy half of instantiate/run/destroy. `--network none` means
a generator cannot fetch dependencies mid-run; everything it needs is baked
in. The read-only source bind is worth naming: it turns chiron's "never modify
anything under `corpora/*/source/`" from a convention the tooling asks for
into something the kernel enforces.

## Changing versions

The `ARG` pins at the top of the Dockerfile are the reproducibility surface —
the image digest is only as stable as what went into it. doxygen itself comes
from the base image's apt, so the `debian:bookworm-slim` tag is what pins it
(1.9.4 today).

After any bump, re-stage a corpus you have already generated. If the digest
`ch doc` reports has changed, every register on that tree will go stale on its
next regeneration, and that is the moment to decide whether the new output is
worth re-authoring for.
