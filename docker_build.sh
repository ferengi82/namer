#!/bin/bash
set -euo pipefail

repo=${IMAGE_REPO:-ferengi82/namer}
repo=${repo,,}
version=v$(grep -m1 "version = " pyproject.toml | sed 's/.* = //' | sed 's/"//g' | tr -d '[:space:]')
image="ghcr.io/${repo}"

BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
export BUILD_DATE

GIT_HASH=$(git rev-parse --verify HEAD)
export GIT_HASH

PROJECT_VERSION=${version}
export PROJECT_VERSION

docker build . \
    --build-arg "BUILD_DATE=${BUILD_DATE}" \
    --build-arg "GIT_HASH=${GIT_HASH}" \
    --build-arg "PROJECT_VERSION=${PROJECT_VERSION}" \
    -t "${image}:${version}" \
    -t "${image}:latest"

if [ "${PUSH_IMAGE:-false}" = "true" ]; then
    docker push "${image}:${version}"
    docker push "${image}:latest"
fi

printf 'Namer image: %s:%s\n' "${image}" "${version}"
printf 'Namer image: %s:latest\n' "${image}"
