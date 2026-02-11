#!/usr/bin/env python3
"""Compatibility entrypoint for the Coinbase-aligned v2 MVP server."""

import os

import uvicorn

from bbt_mvp_server import app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
