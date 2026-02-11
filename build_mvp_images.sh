#!/usr/bin/env bash
set -euo pipefail

echo "Building facilitator image..."
docker build \
  -t "bbt-x402-facilitator:permit2" \
  -f bbt-x402-facilitator/Dockerfile.bbt \
  bbt-x402-facilitator

echo "Building store API image..."
docker build \
  -t "bbt-store-api:latest" \
  -f Dockerfile.store-api \
  .

if [[ "${BUILD_STORE_WEB:-0}" == "1" ]]; then
  echo "Building optional store web image..."
  docker build \
    -t "bbt-store-web:latest" \
    -f Dockerfile.store-web \
    .
fi

echo "Done (images aligned with docker-compose files)."
