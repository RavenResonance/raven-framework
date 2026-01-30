#!/bin/sh
# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# This file is part of the Raven Framework and is proprietary
# to Raven Resonance, Inc. Unauthorized copying, modification,
# or distribution is prohibited without prior written permission.
# ================================================================

set -eu

# Run the app entrypoint.
if [ -f main.pyc ]; then
  exec python3 main.pyc
elif [ -f main.py ]; then
  exec python3 main.py
else
  echo "Error: Neither main.py nor main.pyc found" >&2
  exit 1
fi