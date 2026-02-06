#!/usr/bin/env bash
set -euo pipefail

TAG_PREFIX=${TAG_PREFIX:-"x402"}

echo "Building facilitator image..."
docker build \
  -t "${TAG_PREFIX}-facilitator:permit2" \
  -f bbt-x402-facilitator/Dockerfile.bbt \
  bbt-x402-facilitator

echo "Building store API image..."
docker build \
  -t "${TAG_PREFIX}-store-api:latest" \
  -f Dockerfile.store-api \
  .

echo "Building store web image..."
docker build \
  -t "${TAG_PREFIX}-store-web:latest" \
  -f Dockerfile.store-web \
  .

echo "Done."
