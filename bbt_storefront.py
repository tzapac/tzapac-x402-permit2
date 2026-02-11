#!/usr/bin/env python3
"""Compatibility wrapper for the Coinbase-aligned store API."""

import os

import uvicorn

from bbt_mvp_server import app


if __name__ == "__main__":
    print("bbt_storefront.py is deprecated; running bbt_mvp_server.py app instead.")
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
