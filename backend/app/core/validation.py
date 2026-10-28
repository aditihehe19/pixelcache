"""Vocabulary and limits shared by request schemas and the engine runner.

These mirror exactly what the C++ engine accepts (parse_op, parse_mapping,
parse_variant, parse_synthetic_kind, parse_condition in the engine sources).
Anything outside these sets is rejected before a process is ever started.
"""
from __future__ import annotations

import re
from enum import Enum


class Operation(str, Enum):
    yuv = "yuv"
    hsv = "hsv"
    lab = "lab"
    unpack = "unpack"          # memory-bound reference kernel
    index_only = "index_only"  # address generation only (no pixel memory)


class Mapping(str, Enum):
    identity = "identity"
    rotate90 = "rotate90"


class Strategy(str, Enum):
    row_major = "row_major"
    column_major = "column_major"
    tiled = "tiled"
    morton = "morton"
    adaptive_model = "adaptive_model"
    adaptive_calib = "adaptive_calib"


class ImageSource(str, Enum):
    gradient = "gradient"
    noise = "noise"
    mixed = "mixed"
    photo = "photo"     # matplotlib's public-domain test photo, prepared by scripts/prepare_images.py
    upload = "upload"   # user-supplied image, decoded server-side


class CacheCondition(str, Enum):
    warm = "warm"
    flushed = "flushed"


OPERATION_LABELS = {
    Operation.yuv: "RGB → YUV (BT.601)",
    Operation.hsv: "RGB → HSV",
    Operation.lab: "RGB → CIELAB (sRGB, D65)",
    Operation.unpack: "RGB888 → float (memory-bound reference)",
    Operation.index_only: "address generation only (no memory)",
}

STRATEGY_LABELS = {
    Strategy.row_major: "Row-major (baseline)",
    Strategy.column_major: "Column-major (negative control)",
    Strategy.tiled: "Spatial tiling",
    Strategy.morton: "Morton / Z-order",
    Strategy.adaptive_model: "Adaptive tile (model only)",
    Strategy.adaptive_calib: "Adaptive tile (model + calibration)",
}

MIN_EDGE, MAX_EDGE = 16, 8192
MIN_TILE, MAX_TILE = 1, 4096
MIN_REPS, MAX_REPS = 3, 51
MAX_VARIANTS = 12
UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".ppm", ".tif", ".tiff"}

# Variant tokens the engine understands; used to double-check every argument
# right before it is handed to subprocess.
VARIANT_TOKEN = re.compile(r"^(row_major|column_major|morton|adaptive_model|adaptive_calib|tiled:\d{1,4}x\d{1,4})$")


def variant_token(strategy: Strategy, tile_w: int | None = None, tile_h: int | None = None) -> str:
    if strategy == Strategy.tiled:
        return f"tiled:{tile_w}x{tile_h}"
    return strategy.value


def variant_label(token: str) -> str:
    """Engine label for a variant token (`tiled:32x32` -> `tiled_32x32`)."""
    return token.replace(":", "_")
