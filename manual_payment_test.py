#!/usr/bin/env python3
"""Deprecated legacy manual test entrypoint.

Use playbook_permit2_flow.py for the supported Coinbase-aligned witness flow.
"""

import os
import subprocess
import sys


if __name__ == "__main__":
    print("manual_payment_test.py is deprecated; running playbook_permit2_flow.py instead.")
    cmd = [sys.executable, "playbook_permit2_flow.py"]
    os.execv(sys.executable, cmd)
