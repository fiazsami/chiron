# chiron docgen — every supported generator, one pinned image.
#
# Why one image and no host fallback: a derived tree's bytes feed every
# chapter's content_hash, and doxygen 1.9 and 1.11 do not agree on those bytes.
# A host binary would make drift mean "you changed machines". One digest-pinned
# image is what lets generated material participate in the state model at all.
#
# The image is run with --network none, a read-only bind of the corpus source
# at /src, and a writable /out. It reads /out/.recipe.json — the same recipe
# chiron validated — and decides for itself how to invoke the tool. That one
# schema is the whole contract between them; there is no second flag table to
# drift apart.

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    npm_config_update_notifier=false \
    npm_config_fund=false \
    npm_config_audit=false \
    GOTOOLCHAIN=local \
    GOPATH=/opt/go \
    PATH=/opt/go/bin:/usr/local/go/bin:$PATH

# Versions are pinned because the image digest is only as reproducible as what
# went into it. Bump deliberately, and re-verify determinism when you do.
# doxygen itself comes from the base image's apt, so the debian tag above is
# what pins it — bookworm-slim ships 1.9.4.
ARG MOXYGEN_VERSION=2.1.19
ARG TYPEDOC_VERSION=0.27.6
ARG TYPEDOC_MARKDOWN_VERSION=4.4.1
ARG PYDOC_MARKDOWN_VERSION=4.8.2
ARG GOMARKDOC_VERSION=v1.1.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git \
        python3 python3-pip python3-venv \
        nodejs npm \
        golang-go \
        doxygen graphviz \
        clang libclang-dev \
    && rm -rf /var/lib/apt/lists/*

# --- TypeScript/JavaScript, and C/C++'s XML -> Markdown converter -------
# moxygen rather than doxybook2: doxybook2 publishes an amd64-only binary, and
# this image must build on arm64 too. moxygen is JavaScript, so it runs
# wherever node does — and node is already here for typedoc.
RUN npm install -g --no-save \
      "typedoc@${TYPEDOC_VERSION}" \
      "typedoc-plugin-markdown@${TYPEDOC_MARKDOWN_VERSION}" \
      "moxygen@${MOXYGEN_VERSION}" \
      typescript

# --- Python --------------------------------------------------------------
RUN python3 -m venv /opt/pydoc \
    && /opt/pydoc/bin/pip install --no-cache-dir \
       "pydoc-markdown==${PYDOC_MARKDOWN_VERSION}" \
    && ln -s /opt/pydoc/bin/pydoc-markdown /usr/local/bin/pydoc-markdown

# --- Go -------------------------------------------------------------------
RUN go install "github.com/princjef/gomarkdoc/cmd/gomarkdoc@${GOMARKDOC_VERSION}"

COPY entrypoint.py /usr/local/bin/chiron-docgen
RUN chmod +x /usr/local/bin/chiron-docgen

# The runner passes --user, so this is a default rather than a guarantee.
# Nothing here should ever need root: /src is read-only and /out is bound.
RUN useradd --create-home --uid 1000 docgen
USER docgen
WORKDIR /work

# The recipe schema this image speaks. `ch doc` refuses an image that does not
# match its own SCHEMA_VERSION rather than generating something it cannot read.
LABEL org.chiron.recipe-schema="1"

ENTRYPOINT ["/usr/local/bin/chiron-docgen"]
