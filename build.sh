#!/usr/bin/env bash
# Multi-arch build helper for gmail-attachments-mcp
#
# Usage:
#   ./build.sh local             # build for current arch only, load into local docker
#   ./build.sh multi             # build linux/arm64 + linux/amd64 (push to registry)
#   ./build.sh push <registry>   # push to registry (e.g. ghcr.io/roman/gmail-mcp)

set -euo pipefail

IMAGE="${IMAGE:-gmail-attachments-mcp}"
TAG="${TAG:-latest}"

case "${1:-local}" in
  local)
    echo "Building for current architecture only..."
    docker build -t "$IMAGE:$TAG" .
    echo "Done: $IMAGE:$TAG"
    ;;

  multi)
    REGISTRY="${2:-ghcr.io/yourname}"
    echo "Building multi-arch image for $REGISTRY/$IMAGE:$TAG..."
    # Vyžaduje docker buildx setup - jednorazovo:
    #   docker buildx create --name mcp-builder --use
    #   docker buildx inspect --bootstrap
    docker buildx build \
      --platform linux/arm64,linux/amd64 \
      -t "$REGISTRY/$IMAGE:$TAG" \
      --push \
      .
    echo "Done: pushed to $REGISTRY/$IMAGE:$TAG"
    ;;

  push)
    if [ -z "${2:-}" ]; then
      echo "Usage: $0 push <registry>"
      exit 1
    fi
    REGISTRY="$2"
    docker tag "$IMAGE:$TAG" "$REGISTRY/$IMAGE:$TAG"
    docker push "$REGISTRY/$IMAGE:$TAG"
    ;;

  *)
    echo "Unknown command: $1"
    echo "Usage: $0 {local|multi|push} [registry]"
    exit 1
    ;;
esac
