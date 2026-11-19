# Vigilo
#
# Multi-stage build: installs Python deps + security tools in builder,
# copies venv and tool binaries to runtime.
# Runtime has Claude Code, Playwright, security tools, and the pipeline code.
#
# Built by the platform compose: docker compose -f deploy/docker-compose.full.yml build worker

# ── Stage 1: Builder ─────────────────────────────────────────────
FROM cgr.dev/chainguard/wolfi-base:latest AS builder

RUN apk update && apk add --no-cache \
    build-base git curl wget ca-certificates \
    libpcap-dev linux-headers \
    go nodejs-22 npm \
    python3 py3-pip \
    ruby ruby-dev \
    bash

# Go tools
ENV GOPATH=/go
ENV PATH=$GOPATH/bin:/usr/local/go/bin:$PATH
ENV CGO_ENABLED=1
RUN mkdir -p $GOPATH/bin && \
    go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@v2.13.0

# WhatWeb (Ruby-based web fingerprinter)
RUN curl -sL https://github.com/urbanadventurer/WhatWeb/archive/refs/tags/v0.6.3.tar.gz | tar xz -C /opt && \
    mv /opt/WhatWeb-0.6.3 /opt/whatweb && \
    chmod +x /opt/whatweb/whatweb && \
    gem install addressable -v 2.8.9 && \
    echo '#!/bin/bash' > /usr/local/bin/whatweb && \
    echo 'cd /opt/whatweb && exec ./whatweb "$@"' >> /usr/local/bin/whatweb && \
    chmod +x /usr/local/bin/whatweb

# Python dependencies into an isolated venv
WORKDIR /app
COPY pyproject.toml .
COPY src/ ./src/
COPY scripts/ ./scripts/
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -e .

# Python-based API testing tool
RUN /app/venv/bin/pip install --no-cache-dir schemathesis==4.13.0

# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM cgr.dev/chainguard/wolfi-base:latest

# Runtime dependencies
USER root
RUN apk update && apk add --no-cache \
    git bash curl ca-certificates \
    libpcap \
    nodejs-22 npm \
    python3 ruby \
    # Chromium and dependencies for Playwright
    chromium \
    nss freetype harfbuzz \
    libx11 libxcomposite libxdamage libxext libxfixes libxrandr \
    mesa-gbm fontconfig

# WhatWeb Ruby dependencies (needed at runtime)
RUN gem install addressable -v 2.8.9

# Claude Code, Codex CLI, and Playwright CLI (skill-based browser automation).
# Both LLM CLIs are baked in; VIGILO_EXECUTOR (in .env) selects one at runtime.
# --allow-scripts is REQUIRED for claude-code: recent npm blocks global install
# scripts by default, so its postinstall (which downloads the native binary)
# won't run otherwise, leaving a stub that fails with "Exec format error".
RUN npm install -g --allow-scripts=@anthropic-ai/claude-code \
    @anthropic-ai/claude-code @openai/codex@0.142.5 @playwright/cli@0.1.1
# OpenCode CLI 2.x — official static glibc binary. wolfi-base:latest is glibc,
# not musl (/lib/ld-linux-aarch64.so.1 exists, /lib/ld-musl-*.so.1 does not,
# and installing musl conflicts with glibc), so the glibc asset runs natively,
# no patchelf. Verified in-container: the musl asset fails ("not found"), the
# glibc asset starts (opencode v2.3.0).
# npm "opencode-ai" only ships 1.x and its postinstall leaves a dead stub on
# npm>=12, hence the pinned release tarball + SHA256 check (upstream SHA256SUMS).
ARG OPENCODE_VERSION=2.3.0
RUN ARCH=$(uname -m) && \
    case "$ARCH" in \
      aarch64) OC_ARCH=arm64; OC_SHA=3207fb5cdec448d479242c0f1a14f4f7bdfcad3a79209b5eb8f9003725e93711 ;; \
      x86_64)  OC_ARCH=x64;   OC_SHA=fc0f81522aceeabac47693d88389efa2bc517ce74c2c38fd6967819fcc6e4d3b ;; \
      *) echo "unsupported arch $ARCH" >&2; exit 1 ;; \
    esac && \
    curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${OC_ARCH}.tar.gz" -o /tmp/oc.tar.gz && \
    echo "${OC_SHA}  /tmp/oc.tar.gz" | sha256sum -c - && \
    mkdir -p /usr/local/bin && \
    tar xzf /tmp/oc.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/opencode && rm /tmp/oc.tar.gz && \
    opencode --version
# The playwright-cli skill must live under EACH CLI's own skill-discovery path,
# else the executor not matching the install path never sees it and falls back
# to raw HTTP. Claude scans /tmp/.claude/skills; Codex scans $CODEX_HOME/skills
# (=/tmp/.codex/skills). SKILL.md is a cross-compatible standard, so the same
# skill dir works for both — copy it into both paths.
RUN mkdir -p /tmp/.claude/skills /tmp/.codex/skills && \
    playwright-cli install --skills && \
    cp -r .claude/skills/playwright-cli /tmp/.claude/skills/ && \
    cp -r .claude/skills/playwright-cli /tmp/.codex/skills/ && \
    rm -rf .claude

# Copy Go binaries from builder
COPY --from=builder /go/bin/subfinder /usr/local/bin/

# Copy WhatWeb from builder
COPY --from=builder /opt/whatweb /opt/whatweb
COPY --from=builder /usr/local/bin/whatweb /usr/local/bin/whatweb

# Copy Python venv from builder (includes schemathesis)
COPY --from=builder /app/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

WORKDIR /app

# Copy application code
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY scripts/ ./scripts/
COPY configs/ ./configs/
COPY pyproject.toml .

# Install the package in editable mode (sources already present)
RUN /app/venv/bin/pip install --no-cache-dir -e .

# Make CLI tools available on PATH
RUN ln -sf /app/scripts/save_deliverable.py /usr/local/bin/save-deliverable && \
    chmod +x /app/scripts/save_deliverable.py && \
    ln -sf /app/scripts/vigilo_record.py /usr/local/bin/vigilo-record && \
    chmod +x /app/scripts/vigilo_record.py && \
    ln -sf /app/scripts/generate_totp.py /usr/local/bin/generate-totp && \
    chmod +x /app/scripts/generate_totp.py && \
    ln -sf /app/scripts/config_codex.sh /usr/local/bin/config-codex && \
    chmod +x /app/scripts/config_codex.sh

# System-level git config (survives UID changes)
RUN git config --system user.email "agent@localhost" && \
    git config --system user.name "Vigilo Agent" && \
    git config --system --add safe.directory '*'

# Non-root scanner user
RUN addgroup -g 1001 scanner && \
    adduser -u 1001 -G scanner -s /bin/bash -D scanner && \
    mkdir -p /repos/target && \
    mkdir -p /tmp/.cache /tmp/.config /tmp/.npm /tmp/.codex && \
    chmod 777 /app /tmp/.cache /tmp/.config /tmp/.npm /tmp/.codex && \
    chown -R scanner:scanner /app /repos /tmp/.claude /tmp/.cache /tmp/.config /tmp/.npm /tmp/.codex

# Copy entrypoint for optional UID remapping
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Playwright uses system Chromium — no download needed
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV PLAYWRIGHT_MCP_EXECUTABLE_PATH=/usr/bin/chromium-browser
# Belt-and-suspenders: Wolfi Chromium works without this, but ensures no sandbox issues
ENV CHROMIUM_FLAGS="--no-sandbox --disable-setuid-sandbox"
ENV VIGILO_DOCKER=true
ENV HOME=/tmp
ENV CODEX_HOME=/tmp/.codex
ENV XDG_CACHE_HOME=/tmp/.cache
ENV XDG_CONFIG_HOME=/tmp/.config
ENV npm_config_cache=/tmp/.npm

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python3", "-m", "src.temporal.worker"]
