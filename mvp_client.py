#!/usr/bin/env python3
"""Compatibility entrypoint for the Coinbase-aligned v2 MVP client."""

import asyncio

from bbt_mvp_client import main


if __name__ == "__main__":
    asyncio.run(main())
