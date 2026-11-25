"""Estimate the locally matched width of two symmetric strips in a homogeneous grounded box."""

import argparse
import math

import numpy as np


def modal_impedances(width, gap, box_width, lower, upper, er, panels):
    """Galerkin solution for zero-thickness strips. All five dimensions use the same units."""
    if width <= 0 or width + gap / 2 >= box_width / 2:
        raise ValueError("Strip width must leave clearance to the enclosure")
    k = np.arange(1, 6145) * np.pi / box_width
    pitch = width / panels
    # Average each sine over a constant-charge panel on the strip on the right.
    centers = box_width / 2 + gap / 2 + (np.arange(panels) + 0.5) * pitch
    basis = np.sin(centers[:, None] * k) * np.sinc(k * pitch / (2 * np.pi))
    # Grounded planes at both z limits give the Fourier-domain potential due to sheet charge.
    green = 4 / (box_width * k * (1 / np.tanh(k * lower) + 1 / np.tanh(k * upper)))
    basis *= np.sqrt(green)
    result = []
    for parity in (0, 1):
        # Mirror symmetry selects odd sine harmonics for even drive and vice versa.
        modes = basis[:, parity::2]
        charge = np.linalg.solve(modes @ modes.T, np.ones(panels)).sum()
        result.append(376.730313668 / (np.sqrt(er) * charge))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gaps", type=float, nargs="+", default=[0.12, 1.16, 2.20], help="mm")
    parser.add_argument("--panels", type=int, default=80, help="charge panels per strip")
    args = parser.parse_args()
    if not 2 <= args.panels <= 512 or any(not 0 < gap < 6.42 for gap in args.gaps):
        parser.error("Use 2–512 panels and gaps strictly between 0 and 6.42 mm")
    print("gap_mm  width_mm   Ze_ohm   Zo_ohm")
    for gap in args.gaps:
        low, high = 0.0, (6.42 - gap) / 2
        for _ in range(24):
            width = (low + high) / 2
            even, odd = modal_impedances(width, gap, 6.42, 0.508, 2.0, 3.48, args.panels)
            if math.sqrt(even * odd) > 50:
                low = width
            else:
                high = width
        if abs(math.sqrt(even * odd) - 50) > 0.01:
            raise ValueError(f"No resolved 50 ohm match for gap {gap:g} mm")
        print(f"{gap:6.3f}  {width:8.4f}  {even:7.2f}  {odd:7.2f}")


if __name__ == "__main__":
    main()
