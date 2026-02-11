#!/usr/bin/env python3
"""Deprecated legacy SDK proof entrypoint.

Use playbook_permit2_flow.py for the supported Coinbase-aligned witness flow.
"""

import os
import sys


if __name__ == "__main__":
    print("sdk_payment_proof.py is deprecated; running playbook_permit2_flow.py instead.")
    cmd = [sys.executable, "playbook_permit2_flow.py"]
    os.execv(sys.executable, cmd)
