#!/usr/bin/env python3
"""Compatibility wrapper for the Coinbase-aligned witness client."""

import asyncio

from bbt_mvp_client import main


if __name__ == "__main__":
    print("bbt_client.py is deprecated; running bbt_mvp_client.py instead.")
    asyncio.run(main())
