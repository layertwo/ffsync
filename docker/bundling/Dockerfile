# Vendored from uv-python-lambda (resources/Dockerfile) so we own the build
# context and can attach BuildKit cache (cacheFrom/cacheTo type=gha) via the
# CDK DockerImage.fromBuild escape hatch in lib/stacks/service.ts.
#
# shortcut: AL2023 ships no python3.15 and AWS publishes no 3.15 build image,
# so uv fetches the standalone CPython built for AL2023's glibc.
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv
FROM amazonlinux:2023

# rsync is required by uv-python-lambda's bundling command.
RUN dnf install -y rsync && \
    dnf clean all

COPY --from=uv /uv /uvx /usr/local/bin/

RUN UV_PYTHON_INSTALL_DIR=/usr/local/python UV_PYTHON_BIN_DIR=/usr/local/bin \
    uv python install 3.15.2 && \
    rm -rf /root/.cache/uv

# CDK runs bundling as an unprivileged uid, so the cache must be writable.
RUN mkdir -p /tmp/uv-cache && chmod 0777 /tmp/uv-cache
ENV UV_CACHE_DIR=/tmp/uv-cache

CMD [ "python3.15" ]
