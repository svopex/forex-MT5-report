#!/usr/bin/env python3
"""
Spouštěč aplikace pro tvorbu PDF reportů z historie obchodování MetaTrader 5.

Příklad:
    python report.py ReportHistory-498754.xlsx month=last
"""

import sys

from forexreport.cli import main

if __name__ == "__main__":
    sys.exit(main())
