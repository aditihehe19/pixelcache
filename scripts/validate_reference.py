#!/usr/bin/env python3
"""Numerical validation of the C++ conversions (outside every timed region).

For each test image the C++ binary dumps its outputs (row-major traversal;
the C++ tests separately prove every other traversal is bit-identical), and
this script compares them with two references:

  1. "numpy64": an independent float64 NumPy transcription of the documented
     formulas (docs/methodology.md). This checks the implementation.
  2. "opencv":  cv2.cvtColor on float32 input in [0, 1]. This checks the
     conventions against a widely used library. OpenCV's constants are not
     identical to ours for every conversion (see notes in the output), so its
     differences are reported and explained rather than assumed to be zero.

Writes results/validation/validation_summary.csv and validation_summary.md.

Usage: python scripts/validate_reference.py [--bench build/cachevision_bench_native]
"""
import argparse
import csv
import os
import subprocess
import sys

import numpy as np
import cv2

OPS = ["unpack", "yuv", "hsv", "lab"]
CHANNELS = {"unpack": ("R", "G", "B"), "yuv": ("Y", "U", "V"), "hsv": ("H", "S", "V"), "lab": ("L", "a", "b")}
# Tolerances vs the float64 transcription (justified in tests/test_conversion.cpp).
TOL_NUMPY = {"unpack": (1e-7,) * 3, "yuv": (3e-7,) * 3, "hsv": (2e-3, 1e-6, 1e-6), "lab": (1e-3, 1e-3, 1e-3)}
# Tolerances vs OpenCV, derived (not fitted):
#  * unpack/yuv: same formulas, so a few float32 ulps.
#  * hsv: OpenCV computes S = C / (V + FLT_EPSILON) and H with 60 / (C + FLT_EPSILON).
#    The relative perturbation is FLT_EPSILON / V (resp. / C) <= 255 * FLT_EPSILON for
#    8-bit input (smallest non-zero V or C is 1/255), so |dS| <= 255 eps and
#    |dH| <= 360 * 255 eps (~1.1e-2 degrees).
#  * lab: None -> OpenCV's float Lab path is an approximation (see characterise_opencv_lab);
#    the gap is reported, not judged.
FLT_EPS = float(np.finfo(np.float32).eps)
TOL_OPENCV = {"unpack": (1e-7,) * 3, "yuv": (1e-6,) * 3,
              "hsv": (360 * 255 * FLT_EPS, 255 * FLT_EPS, 1e-6), "lab": None}
NOTES = {
    "yuv": "OpenCV COLOR_RGB2YUV (float) uses the same BT.601 coefficients (0.299/0.587/0.114, U 0.492, V 0.877, offset 0.5).",
    "hsv": "OpenCV adds FLT_EPSILON to denominators and multiplies by 60/C instead of dividing; differences are rounding-level.",
    "lab": "OpenCV's float RGB2Lab is an approximation: re-implementing it with OpenCV's own constants "
           "(matrix 0.412453..., Xn=0.950456, Zn=1.088754, 7.787/903.3 linear segment) does NOT remove the gap, and "
           "on the grey axis the error is a sawtooth (see the characterisation below), the signature of table/"
           "interpolation-based evaluation. The gap is therefore reported, not used as a pass/fail criterion; the "
           "implementation itself is validated against the float64 reference.",
    "unpack": "Normalisation c/255.",
}


def read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    parts, pos = [], 0
    while len(parts) < 4:  # magic, w, h, maxval (comments not produced by our writer)
        while data[pos:pos + 1].isspace():
            pos += 1
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        parts.append(data[pos:end])
        pos = end
    pos += 1
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(data[pos:pos + w * h * 3], dtype=np.uint8).reshape(h, w, 3)


def srgb_eotf(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def numpy64(op, rgb8):
    c = rgb8.astype(np.float64) / 255.0
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    if op == "unpack":
        return c
    if op == "yuv":
        y = 0.299 * r + 0.587 * g + 0.114 * b
        return np.stack([y, 0.492 * (b - y) + 0.5, 0.877 * (r - y) + 0.5], -1)
    if op == "hsv":
        v = c.max(-1)
        mn = c.min(-1)
        ch = v - mn
        safe = np.where(ch > 0, ch, 1.0)
        h = np.where(v == r, 60 * (g - b) / safe, np.where(v == g, 60 * (b - r) / safe + 120, 60 * (r - g) / safe + 240))
        h = np.where(ch > 0, h, 0.0)
        h = np.where(h < 0, h + 360, h)
        s = np.where(v > 0, ch / np.where(v > 0, v, 1.0), 0.0)
        return np.stack([h, s, v], -1)
    if op == "lab":
        lin = srgb_eotf(c)
        m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                      [0.0193339, 0.1191920, 0.9503041]])
        xyz = lin @ m.T
        xyz = xyz / np.array([0.95047, 1.0, 1.08883])
        eps, kappa = 216 / 24389, 24389 / 27
        f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
        return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)
    raise ValueError(op)


def opencv(op, rgb8):
    x = rgb8.astype(np.float32) / np.float32(255.0)
    if op == "unpack":
        return x.astype(np.float64)
    code = {"yuv": cv2.COLOR_RGB2YUV, "hsv": cv2.COLOR_RGB2HSV, "lab": cv2.COLOR_RGB2Lab}[op]
    return cv2.cvtColor(x, code).astype(np.float64)


def characterise_opencv_lab():
    """Error of OpenCV float Lab L* along the grey axis vs the exact CIE formula."""
    g = np.arange(256, dtype=np.uint8)
    rgb8 = np.stack([g, g, g], -1).reshape(1, 256, 3)
    ocv = cv2.cvtColor(rgb8.astype(np.float32) / np.float32(255), cv2.COLOR_RGB2Lab)[0, :, 0].astype(np.float64)
    exact = numpy64("lab", rgb8)[0, :, 0]
    e = ocv - exact
    return e


def errors(op, got, ref):
    e = np.abs(got.astype(np.float64) - ref)
    if op == "hsv":
        e[..., 0] = np.minimum(e[..., 0], 360.0 - e[..., 0])  # hue is circular
    return e


def main():
    ap = argparse.ArgumentParser()
    exe = "cachevision_bench_native.exe" if os.name == "nt" else "cachevision_bench_native"
    ap.add_argument("--bench", default=os.path.join("build", exe))
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default=os.path.join("results", "validation"))
    ap.add_argument("--images", default="photo:512x512,noise:512x512,gradient:512x512,mixed:333x217")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    manifest = os.path.join(args.out, "dump_manifest.csv")
    if os.path.exists(manifest):
        os.remove(manifest)

    for spec in args.images.split(","):
        kind, size = spec.split(":")
        subprocess.run([args.bench, "--dump", "--image", kind, "--size", size, "--data", args.data, "--out", args.out],
                       check=True)

    rows = []
    with open(manifest, newline="") as f:
        for variant, kind, w, h, op, path, inp in csv.reader(f):
            w, h = int(w), int(h)
            rgb8 = read_ppm(inp)
            got = np.fromfile(path, dtype=np.float32).reshape(h, w, 3)
            for ref_name, ref_fn, tol in (("numpy64", numpy64, TOL_NUMPY), ("opencv", opencv, TOL_OPENCV)):
                e = errors(op, got, ref_fn(op, rgb8))
                for c in range(3):
                    ec = e[..., c]
                    t = tol[op][c] if tol[op] is not None else None
                    rows.append({
                        "build_variant": variant, "image": kind, "width": w, "height": h, "op": op,
                        "reference": ref_name, "channel": CHANNELS[op][c],
                        "max_abs_err": f"{ec.max():.3e}", "mean_abs_err": f"{ec.mean():.3e}",
                        "p99_abs_err": f"{np.percentile(ec, 99):.3e}",
                        "tolerance": f"{t:.2e}" if t is not None else "n/a",
                        "pass": (int(ec.max() <= t) if t is not None else "n/a"),
                    })
            # free the large dump files once compared (they are reproducible)
            os.remove(path)

    out_csv = os.path.join(args.out, "validation_summary.csv")
    with open(out_csv, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    md = ["# Numerical validation", "",
          "Outputs of the row-major traversal (all traversals are bit-identical, see tests) compared with an "
          "independent float64 NumPy transcription of the documented formulas and with OpenCV "
          f"{cv2.__version__} `cvtColor` on float32 input. Errors are absolute, in output units "
          "(H in degrees, L in 0..100).", "",
          "| image | op | reference | channel | max abs err | mean abs err | tolerance | pass |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        verdict = "n/a" if r["pass"] == "n/a" else ("yes" if r["pass"] else "NO")
        md.append(f"| {r['image']} {r['width']}x{r['height']} | {r['op']} | {r['reference']} | {r['channel']} | "
                  f"{r['max_abs_err']} | {r['mean_abs_err']} | {r['tolerance']} | {verdict} |")
    md += ["", "Notes on OpenCV conventions:", ""] + [f"* **{k}**: {v}" for k, v in NOTES.items()]
    e = characterise_opencv_lab()
    md += ["", "OpenCV float Lab, L* error on the grey axis (OpenCV - exact), every 16th code:", "",
           "| code | " + " | ".join(str(i) for i in range(0, 256, 16)) + " |",
           "|---|" + "---|" * 16,
           "| err | " + " | ".join(f"{v:+.3f}" for v in e[::16]) + " |", "",
           f"Max |error| on the grey axis: {np.abs(e).max():.3f} L* units."]
    with open(os.path.join(args.out, "opencv_lab_grey_axis.csv"), "w", encoding="utf-8") as f:
        f.write("code,opencv_minus_exact_L" + chr(10) + "".join(f"{i},{v:.6f}" + chr(10) for i, v in enumerate(e)))
    with open(os.path.join(args.out, "validation_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    failed = [r for r in rows if r["pass"] == 0]
    judged = [r for r in rows if r["pass"] != "n/a"]
    print(f"validation: {len(judged) - len(failed)}/{len(judged)} judged checks within tolerance "
          f"({len(rows) - len(judged)} reported only) -> {out_csv}")
    for r in failed:
        print(f"  outside tolerance: {r['image']} {r['op']} vs {r['reference']} {r['channel']}: "
              f"max {r['max_abs_err']} > {r['tolerance']}")
    return 1 if any(r["reference"] == "numpy64" for r in failed) else 0


if __name__ == "__main__":
    sys.exit(main())
