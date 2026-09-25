#!/usr/bin/env python3
"""Backward-compatible entry point for `ring.py dream`."""
import sys

from ring import main

if __name__ == '__main__':
    sys.exit(main(['dream', *sys.argv[1:]]))
