import time

import numpy as np

from raven_framework.core.waveguide_halo import (
    HaloSettings,
    apply_waveguide_halo,
)


def _spot(size=101, value=255):
    img = np.zeros((size, size, 3), dtype=np.uint8)
    c = size // 2
    img[c, c] = value
    return img


def test_disabled_is_exact_identity():
    src = _spot()
    out = apply_waveguide_halo(src, HaloSettings(enabled=False))
    assert np.array_equal(out, src)


def test_halo_preserves_sharp_core_and_adds_wide_energy():
    src = np.zeros((101, 101, 3), dtype=np.uint8)
    c = src.shape[0] // 2
    src[:, c - 1 : c + 2] = 255
    settings = HaloSettings(
        enabled=True,
        primary_radius=12,
        primary_strength=0.30,
        secondary_radius=30,
        secondary_strength=0.10,
    )
    out = apply_waveguide_halo(src, settings)
    assert out[c, c, 0] == 255
    assert out[c, c + 8, 0] > 0
    assert out[c, c + 20, 0] > 0


def test_zero_strengths_are_identity_even_when_enabled():
    src = _spot()
    settings = HaloSettings(
        enabled=True,
        primary_radius=15,
        primary_strength=0.0,
        secondary_radius=40,
        secondary_strength=0.0,
    )
    out = apply_waveguide_halo(src, settings)
    assert np.array_equal(out, src)


def test_output_is_uint8_and_clamped():
    src = np.full((31, 31, 3), 255, dtype=np.uint8)
    settings = HaloSettings(
        enabled=True,
        primary_radius=10,
        primary_strength=1.0,
        secondary_radius=20,
        secondary_strength=1.0,
    )
    out = apply_waveguide_halo(src, settings)
    assert out.dtype == np.uint8
    assert out.min() >= 0
    assert out.max() <= 255


def test_invalid_values_are_sanitized():
    settings = HaloSettings(
        enabled=True,
        primary_radius=-5,
        primary_strength=-1.0,
        secondary_radius=0,
        secondary_strength=9.0,
    ).sanitized()
    assert settings.primary_radius >= 1
    assert settings.secondary_radius >= 1
    assert 0.0 <= settings.primary_strength <= 1.0
    assert 0.0 <= settings.secondary_strength <= 1.0


def test_the_downscaled_blur_matches_a_full_resolution_one():
    """The optimisation must be invisible, not merely fast.

    A wide halo is low-frequency by construction, so blurring it at
    quarter resolution should be indistinguishable from blurring it at
    full resolution.
    """
    import cv2

    hud = np.zeros((720, 720, 3), np.uint8)
    cv2.rectangle(hud, (140, 220), (580, 500), (255, 255, 255), 2)
    cv2.putText(
        hud,
        "Deploy production",
        (170, 300),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2,
    )

    settings = HaloSettings(enabled=True)
    reference = hud.astype(np.float32)
    source_peak = float(hud.max())
    for radius, strength in (
        (settings.primary_radius, settings.primary_strength),
        (settings.secondary_radius, settings.secondary_strength),
    ):
        layer = cv2.GaussianBlur(
            hud.astype(np.float32),
            (0, 0),
            sigmaX=radius,
            sigmaY=radius,
            borderType=cv2.BORDER_REFLECT_101,
        )
        # Same peak normalisation the module applies, or this compares
        # the optimisation against a different algorithm.
        reference += layer * (source_peak / float(layer.max())) * strength
    reference = np.clip(reference, 0, 255).astype(np.uint8)

    fast = apply_waveguide_halo(hud, settings)
    difference = np.abs(fast.astype(int) - reference.astype(int))

    assert difference.max() <= 3
    assert difference.mean() < 0.05


def test_the_halo_is_fast_enough_to_reach_the_screen():
    """The bug this version exists to fix.

    The simulator shows only the newest blended frame and discards
    anything late. A halo slower than the queue is computed perfectly and
    thrown away, which is what happened in v1: the screen never changed.
    """
    hud = np.zeros((720, 720, 3), np.uint8)
    hud[300:320, 100:600] = 255
    settings = HaloSettings(enabled=True)

    apply_waveguide_halo(hud, settings)  # warm up
    start = time.perf_counter()
    for _ in range(5):
        apply_waveguide_halo(hud, settings)
    per_frame_ms = (time.perf_counter() - start) / 5 * 1000
    print(f"      ({per_frame_ms:.1f} ms per frame)")

    # A deliberately loose ceiling. On a normal machine this runs in
    # 15-35 ms; the point of the check is to catch an order-of-magnitude
    # regression, not to hold a tight bound that flakes on a slow CI
    # runner. v1, which this version replaces, took 234 ms here.
    assert per_frame_ms < 120, f"halo takes {per_frame_ms:.1f} ms per frame"


def test_a_thin_line_gets_a_halo_the_control_can_actually_reach():
    """The bug peak normalisation fixes.

    A Gaussian blur preserves energy, so blurring a two-pixel line leaves
    about three percent of its brightness -- and this interface is two-pixel
    lines. Before normalising, the Glow control at maximum produced 3.7%
    beside an edge where the approved look has 33%, with no setting able to
    close the gap.
    """
    import cv2

    hud = np.zeros((256, 256, 3), np.uint8)
    hud[:, 127:129] = 255

    out = apply_waveguide_halo(
        hud,
        HaloSettings(
            enabled=True,
            primary_strength=0.20,
            primary_radius=8,
            secondary_strength=0.0,
        ),
    ).astype(float)

    row = out[128]
    beside = row[127 - 4, 0] / 255.0
    assert 0.10 < beside < 0.30, f"halo beside the line is {beside:.1%}"


def test_the_default_settings_match_the_reference_falloff():
    """The four defaults are a fit, not a taste.

    Measured from the approved reference imagery: the falloff outward from
    a card outline, converted to simulator pixels at 720/482. Measured
    through blend_frame rather than off the raw halo layer, because the
    blend's linear-light LUT is part of what produces the look and the
    numbers below were read off a finished picture.

    If someone changes the defaults, this says how far they moved.
    """
    from raven_framework.core.raven_simulator import blend_frame

    hud = np.zeros((720, 720, 3), np.uint8)
    hud[:, 360:362] = 255
    background = np.full((720, 720, 3), 40, np.uint8)

    blended = blend_frame(
        background, hud, halo_settings=HaloSettings(enabled=True)
    ).astype(float)
    row = blended[360, :, 2]
    floor = float(np.median(row[50:150]))
    peak = row[360] - floor

    reference = {3: 33.2, 9: 25.8, 15: 19.3, 30: 11.6, 60: 5.3}
    errors = []
    for distance, expected in reference.items():
        got = 100.0 * (row[360 - distance] - floor) / peak
        errors.append(abs(got - expected))

    mean_error = sum(errors) / len(errors)
    assert mean_error < 3.0, f"mean error {mean_error:.1f} percentage points"


if __name__ == "__main__":
    # Run directly:  python tests/test_waveguide_halo.py
    #
    # The test functions are plain and fixture-free, so they also collect
    # under pytest wherever the rest of the suite runs; this block just
    # makes the file self-contained for a quick check in a bare checkout.
    import sys
    import traceback

    failures = 0
    for name, fn in sorted(dict(globals()).items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ok    {name}")
        except Exception:
            failures += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    total = sum(
        1 for n, f in globals().items() if n.startswith("test_") and callable(f)
    )
    print(f"\n{total - failures} of {total} passed")
    sys.exit(1 if failures else 0)
