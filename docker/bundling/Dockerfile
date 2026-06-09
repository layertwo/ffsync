# Vendored from uv-python-lambda (resources/Dockerfile) so we own the build
# context and can attach BuildKit cache (cacheFrom/cacheTo type=gha) via the
# CDK DockerImage.fromBuild escape hatch in lib/stacks/service.ts.
ARG IMAGE=public.ecr.aws/sam/build-python3.14
FROM $IMAGE

ARG UV_VERSION=0.11.19

ENV PIP_CACHE_DIR=/tmp/pip-cache
ENV UV_CACHE_DIR=/tmp/uv-cache

RUN mkdir /tmp/pip-cache && \
    chmod -R 777 /tmp/pip-cache && \
    pip install uv==$UV_VERSION && \
    rm -rf /tmp/pip-cache/*

CMD [ "python" ]
