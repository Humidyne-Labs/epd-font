"""Preserved 2D Gaussian EPD Point-Spread Function (PSF), Betti & Michelson Contrast Math."""

from __future__ import annotations

import cv2
import numpy as np

EPD_DEFAULT_R_BG: float = 190.0
EPD_DEFAULT_R_INK: float = 23.0
EPD_DPI: float = 188.15
PIXEL_PITCH_UM: float = 135.0


def simulate_epd_gaussian_psf(
    binary_arr: np.ndarray,
    sigma_px: float = 1.0,
    r_bg: float = EPD_DEFAULT_R_BG,
    r_ink: float = EPD_DEFAULT_R_INK,
    pad_px: int = 6,
) -> tuple[np.ndarray, np.ndarray, int]:
    """
    Map a 1-bpp array (1=ink, 0=bg) to empirical EPD panel reflectance (r_bg, r_ink)
    and convolve with a 2D Gaussian PSF at sigma_px.
    """
    if binary_arr is None or binary_arr.size == 0:
        empty = np.full((pad_px * 2 + 1, pad_px * 2 + 1), float(r_bg), dtype=np.float32)
        return empty, empty.copy(), pad_px
    fg = (binary_arr > 0).astype(np.uint8)
    padded = np.pad(fg, pad_px, mode="constant", constant_values=0)
    raw_lum = np.where(padded > 0, float(r_ink), float(r_bg)).astype(np.float32)
    if float(sigma_px) > 0.05:
        psf_lum = cv2.GaussianBlur(
            raw_lum,
            (0, 0),
            sigmaX=float(sigma_px),
            sigmaY=float(sigma_px),
            borderType=cv2.BORDER_REPLICATE,
        )
    else:
        psf_lum = raw_lum.copy()
    return psf_lum, raw_lum, pad_px


def compute_stroke_centerline_mask(fg_pad: np.ndarray) -> np.ndarray:
    """Return boolean L2 distance-transform medial-ridge mask of active ink strokes."""
    fg_u8 = (fg_pad > 0).astype(np.uint8)
    if np.count_nonzero(fg_u8) == 0:
        return np.zeros_like(fg_u8, dtype=bool)
    dt = cv2.distanceTransform(fg_u8, cv2.DIST_L2, 5)
    local_max = cv2.dilate(dt, np.ones((3, 3), dtype=np.uint8))
    ridge = (fg_u8 > 0) & (dt >= (local_max - 0.45))
    return ridge if np.any(ridge) else (fg_u8 > 0)


def compute_betti_numbers(binary_arr: np.ndarray) -> tuple[int, int]:
    """Return (beta_0_8connected_fg, beta_1_4connected_holes)."""
    if binary_arr is None or binary_arr.size == 0 or np.count_nonzero(binary_arr) == 0:
        return 0, 0
    fg = (binary_arr > 0).astype(np.uint8)
    num_fg, _ = cv2.connectedComponents(fg, connectivity=8)
    b0 = max(0, int(num_fg) - 1)

    padded = np.pad(fg, 1, mode="constant", constant_values=0)
    bg = (1 - padded).astype(np.uint8)
    num_bg, labels = cv2.connectedComponents(bg, connectivity=4)
    ext_label = int(labels[0, 0])
    b1 = sum(1 for lbl in range(1, int(num_bg)) if lbl != ext_label and int(np.sum(labels == lbl)) >= 1)
    return b0, b1


def compute_psf_contrast_retention(
    binary_arr: np.ndarray,
    sigma_um: float = 135.0,
    pixel_pitch_um: float = PIXEL_PITCH_UM,
    r_bg: float = EPD_DEFAULT_R_BG,
    r_ink: float = EPD_DEFAULT_R_INK,
) -> dict[str, float]:
    """Compute Michelson contrast retention (%) under EPD Gaussian PSF scatter."""
    cm_0 = (r_bg - r_ink) / max(1e-5, r_bg + r_ink)
    if binary_arr is None or binary_arr.size == 0 or np.count_nonzero(binary_arr) == 0:
        return {"cm_0": cm_0, "cm_psf": 0.0, "retention_pct": 0.0, "sigma_px": sigma_um / pixel_pitch_um}

    sigma_px = float(sigma_um) / float(pixel_pitch_um)
    pad_px = 6
    psf_lum, _, _ = simulate_epd_gaussian_psf(binary_arr, sigma_px=sigma_px, r_bg=r_bg, r_ink=r_ink, pad_px=pad_px)
    fg_pad = np.pad((binary_arr > 0).astype(np.uint8), pad_px, mode="constant", constant_values=0)
    ridge = compute_stroke_centerline_mask(fg_pad)
    lum_ink = float(np.mean(psf_lum[ridge]))
    cm_psf = max(0.0, (r_bg - lum_ink) / max(1e-5, r_bg + lum_ink))
    ret_pct = (cm_psf / max(1e-5, cm_0)) * 100.0
    return {
        "cm_0": round(cm_0, 4),
        "cm_psf": round(cm_psf, 4),
        "retention_pct": round(ret_pct, 2),
        "sigma_px": round(sigma_px, 3),
    }
