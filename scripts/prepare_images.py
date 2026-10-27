#!/usr/bin/env python3
"""Generate the 'photo' benchmark inputs (binary PPM) from a standard test image.

Source: the public-domain 'grace_hopper.jpg' (512x600, US Navy photograph) that
ships with matplotlib (matplotlib/mpl-data/sample_data). No download needed.

Deterministic recipe, so every machine produces byte-identical inputs:
  * target <= 512 on both sides: area-resample (cv2.INTER_AREA) a centred crop
    with the target aspect ratio down to the target size;
  * larger targets: take the centred 512x512 crop at native resolution and
    mirror-tile it (numpy 'symmetric' padding) to the target size. This keeps
    real photographic local statistics (edges, texture, colour distribution) at
    every size instead of producing an artificially smooth up-scaled image.
The SHA-256 of every generated file is written to data/photo_manifest.csv.

Usage: python scripts/prepare_images.py [--config benchmarks/benchmark_config.json] [--out data]
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    sys.exit("OpenCV for Python (cv2) is required: pip install opencv-python")
import matplotlib
import matplotlib.cbook as cbook


def load_source():
    path = cbook.get_sample_data("grace_hopper.jpg", asfileobj=False)
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        sys.exit(f"cannot read {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), str(path)


def make_photo(src, w, h):
    sh, sw = src.shape[:2]
    if w <= 512 and h <= 512:
        # centred crop with the target aspect ratio, then area resampling
        scale = min(sw / w, sh / h)
        cw, ch = int(round(w * scale)), int(round(h * scale))
        x0, y0 = (sw - cw) // 2, (sh - ch) // 2
        crop = src[y0:y0 + ch, x0:x0 + cw]
        return cv2.resize(crop, (w, h), interpolation=cv2.INTER_AREA)
    y0 = (sh - 512) // 2
    tile = src[y0:y0 + 512, 0:512]
    reps_y = -(-h // 512)
    reps_x = -(-w // 512)
    # symmetric mirror tiling (no seams), then crop to size
    pad = np.pad(tile, ((0, (reps_y - 1) * 512), (0, (reps_x - 1) * 512), (0, 0)), mode="symmetric")
    return np.ascontiguousarray(pad[:h, :w])


def write_ppm(path, rgb):
    h, w = rgb.shape[:2]
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
        f.write(rgb.astype(np.uint8).tobytes())


def sizes_from_config(cfg_path):
    with open(cfg_path, encoding="utf-8") as f:
        text = "\n".join(line for line in f if not line.lstrip().startswith("//"))
    cfg = json.loads(text)
    sizes = set()
    for suite in cfg["suites"].values():
        if "photo" not in suite.get("images", cfg.get("defaults", {}).get("images", [])):
            continue
        for s in suite.get("sizes", []):
            w, h = (s, s) if isinstance(s, (int, float)) else s
            sizes.add((int(w), int(h)))
    return sorted(sizes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="benchmarks/benchmark_config.json")
    ap.add_argument("--out", default="data")
    ap.add_argument("--sizes", help="comma list like 512x512,1920x1080 (overrides config)")
    args = ap.parse_args()

    src, src_path = load_source()
    if args.sizes:
        sizes = [tuple(int(v) for v in s.split("x")) for s in args.sizes.split(",")]
    else:
        sizes = sizes_from_config(args.config)
    os.makedirs(args.out, exist_ok=True)
    rows = []
    for w, h in sizes:
        path = os.path.join(args.out, f"photo_{w}x{h}.ppm")
        img = make_photo(src, w, h)
        assert img.shape == (h, w, 3)
        write_ppm(path, img)
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        rows.append((os.path.basename(path), w, h, digest))
        print(f"wrote {path} ({w}x{h}, sha256 {digest[:16]}...)")
    with open(os.path.join(args.out, "photo_manifest.csv"), "w", encoding="utf-8") as f:
        f.write(f"# source: {os.path.basename(src_path)} from matplotlib {matplotlib.__version__}; "
                f"opencv {cv2.__version__}; numpy {np.__version__}\n")
        f.write("file,width,height,sha256\n")
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")


if __name__ == "__main__":
    main()
