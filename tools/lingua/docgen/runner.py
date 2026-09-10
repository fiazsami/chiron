"""Run a generator in a pinned container: instantiate, run, destroy.

stdlib subprocess only, argv lists, never a shell — the same discipline
gittree.py uses for git, which is the only other external binary chiron
touches. The difference is that git is optional and degrades; this one does
not. There is no host fallback, because a host toolchain would make a derived
tree's bytes depend on the machine that produced it, and those bytes are what
every anchor is pinned to.

The container gets: no network, a read-only bind of the corpus source, one
writable output directory, a tmpfs, and nothing else. The read-only mount is
worth naming — it turns "never modify anything under corpora/*/source/" from a
convention the tooling asks for into something the kernel enforces.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import SCHEMA_VERSION
from .recipe import Recipe

# No image is published yet, so there is no default to pin to. A fake digest
# here would fail at pull time with a confusing message; None fails at the top
# with an actionable one. Set this to the published digest when there is one.
DEFAULT_IMAGE_ENV = "CHIRON_DOCGEN_IMAGE"
DEFAULT_IMAGE: str | None = None
SCHEMA_LABEL = "org.chiron.recipe-schema"
RUN_TIMEOUT = 1800  # 30 minutes; a generator slower than this needs narrowing


class DockerError(Exception):
    """Docker is unavailable, or the run failed. Always exit 2 at the CLI."""


@dataclass(frozen=True)
class Limits:
    memory: str = "2g"
    cpus: str = "2"
    pids: str = "512"


def image_ref() -> str:
    """The image to run. A tag is allowed here — `resolve_image` pins whatever
    it is given to the exact bytes before the recipe records it."""
    ref = os.environ.get(DEFAULT_IMAGE_ENV) or DEFAULT_IMAGE
    if not ref:
        raise DockerError(
            "no docgen image. Build one and point chiron at it:\n"
            "  docker build -t chiron-docgen:dev containers/docgen/\n"
            "  export CHIRON_DOCGEN_IMAGE=chiron-docgen:dev\n"
            "See containers/docgen/README.md for publishing a pinned image."
        )
    return ref


def resolve_image(ref: str, binary: str, *, echo=None) -> str:
    """Pin a reference to the exact image bytes that will run.

    A recipe records how a tree was produced, so recording a tag would record
    a moving target. A pulled image pins to its registry digest and stays
    pullable; a locally built one has no registry digest, so it pins to its
    image id — not fetchable elsewhere, but exact, and visibly a local build.
    This is what makes CHIRON_DOCGEN_IMAGE usable for image development
    without putting a floating tag into a promoted tree.
    """
    if "@sha256:" in ref:
        return ref
    fmt = "{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}"
    for attempt in ("inspect", "pull-then-inspect"):
        probe = subprocess.run(
            [binary, "image", "inspect", "--format", fmt, ref],
            capture_output=True, text=True,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            pinned = probe.stdout.strip()
            return pinned if "@sha256:" in pinned else f"{ref}@{pinned}"
        if attempt == "inspect":
            if echo:
                echo(f"pulling {ref} …")
            pull = subprocess.run([binary, "pull", "--quiet", ref],
                                  capture_output=True, text=True)
            if pull.returncode != 0:
                raise DockerError(
                    f"could not pull {ref}: "
                    + (pull.stderr or "").strip().splitlines()[-1:][0]
                    if (pull.stderr or "").strip() else f"could not pull {ref}"
                )
    raise DockerError(f"could not resolve {ref} to a digest")


def require_docker() -> str:
    """The docker binary, or a DockerError that says what to do about it."""
    binary = shutil.which("docker")
    if binary is None:
        raise DockerError(
            "docker is not on PATH. `ch doc` is the one chiron verb that needs "
            "it — everything else (./ch, ./ch check, the tests) runs without. "
            "Install Docker Desktop or the engine, or mount against source/ "
            "instead and skip generation."
        )
    probe = subprocess.run(
        [binary, "version", "--format", "{{.Server.Version}}"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        detail = next(
            (line.strip() for line in (probe.stderr or "").splitlines() if line.strip()),
            "no reason given",
        )
        raise DockerError(
            f"docker is installed but the daemon is not answering: {detail} "
            f"Start Docker and re-run."
        )
    return binary


def build_argv(recipe: Recipe, source: Path, out: Path, *,
               image: str | None = None, limits: Limits = Limits(),
               binary: str = "docker") -> list[str]:
    """The exact command a run will make. Pure — no side effects, so a test
    can assert the whole isolation posture without a daemon anywhere."""
    return [
        binary, "run",
        "--rm",                       # destroy on exit; the third verb
        "--network", "none",          # a generator cannot fetch or phone home
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--read-only",                # the container's own filesystem too
        "--mount", f"type=bind,src={source.resolve()},dst=/src,ro",
        "--mount", f"type=bind,src={out.resolve()},dst=/out",
        "--tmpfs", "/tmp:exec",       # generators need a scratch they can run from
        "--memory", limits.memory,
        "--cpus", limits.cpus,
        "--pids-limit", limits.pids,
        "--workdir", "/work",
        image or image_ref(),
        recipe.tool,
    ]


def check_image_schema(image: str, binary: str) -> None:
    """Refuse an image that speaks a different recipe schema.

    The recipe is the only contract between chiron and the image. Running an
    image that reads it differently would produce a tree neither side can
    account for, which is worse than not running at all.
    """
    probe = subprocess.run(
        [binary, "image", "inspect", "--format",
         f"{{{{index .Config.Labels \"{SCHEMA_LABEL}\"}}}}", image],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        return  # not pulled yet; `run` will pull, and a bad label fails there
    label = probe.stdout.strip()
    if label and label != str(SCHEMA_VERSION):
        raise DockerError(
            f"image {image} speaks recipe schema {label}, this chiron speaks "
            f"{SCHEMA_VERSION} — update one of them"
        )


def generate(recipe: Recipe, source: Path, out: Path, *,
             image: str | None = None, echo=None) -> str:
    """Generate into `out`, which must exist and should be empty.

    Returns the container's stdout. Raises DockerError with the generator's own
    words on failure — a tool's complaint about a missing tsconfig is more
    useful than anything this layer could say instead.
    """
    binary = require_docker()
    # Pin here rather than at the call site: the recipe must record the bytes
    # that ran, and this is the only place that knows they did.
    ref = resolve_image(image or recipe.image or image_ref(), binary, echo=echo)
    recipe.image = ref
    check_image_schema(ref, binary)
    out.mkdir(parents=True, exist_ok=True)
    # The image reads the recipe chiron already validated; there is no second
    # schema and no flags on the command line to disagree with it.
    (out / ".recipe.json").write_text(json.dumps(recipe.to_dict(), indent=2))

    argv = build_argv(recipe, source, out, image=ref, binary=binary)
    if echo:
        echo("  " + " ".join(argv))
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=RUN_TIMEOUT
        )
    except subprocess.TimeoutExpired as exc:
        raise DockerError(
            f"{recipe.tool} did not finish within {RUN_TIMEOUT // 60} minutes "
            f"— narrow the recipe's scope and re-stage"
        ) from exc
    except OSError as exc:
        raise DockerError(f"could not run docker: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise DockerError(
            f"{recipe.tool} failed in the container (exit {proc.returncode}):\n"
            + "\n".join("  " + line for line in detail.splitlines()[-30:])
        )
    (out / ".recipe.json").unlink(missing_ok=True)
    return proc.stdout
