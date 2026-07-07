# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# This file is part of the Raven Framework and is proprietary
# to Raven Resonance, Inc. Unauthorized copying, modification,
# or distribution is prohibited without prior written permission.
#
# ================================================================
#
# Pytest discovers and loads `conftest.py` automatically for this directory; tests
# do not import it. This file:
# - Sets QT_QPA_PLATFORM=offscreen before PySide6 is imported, so Qt can run
#   headless (CI, SSH, or any environment without a display).
# - Defines shared fixtures (`tiny_png_path`, `tiny_obj_path`) that tests request
#   by name for on-disk PNG/OBJ samples (MediaViewer, cards, model loader).
#
# ================================================================
# Raven Framework — test configuration
# ================================================================

from __future__ import annotations

import os

import pytest

# Headless Qt on CI and local runs (must be set before PySide6 import).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def tiny_png_path(tmp_path) -> str:
    """Minimal PNG on disk for MediaViewer / media cards."""
    from PIL import Image

    path = tmp_path / "tiny.png"
    Image.new("RGB", (64, 64), color=(200, 10, 10)).save(path)
    return str(path)


@pytest.fixture
def tiny_obj_path(tmp_path) -> str:
    """Minimal valid OBJ (triangle) for model_viewer.load_obj_mesh."""
    path = tmp_path / "triangle.obj"
    path.write_text(
        "\n".join(
            [
                "o tri",
                "v 0 0 0",
                "v 1 0 0",
                "v 0 1 0",
                "f 1 2 3",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return str(path)
