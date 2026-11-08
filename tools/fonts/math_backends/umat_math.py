#!/usr/bin/env python3
"""
umat_math.py (v1.0.19c)
=======================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

OpenCV Transparent API (`cv2.UMat` OpenCL) Secondary GPU Math Backend (v1.0.19c):
Accelerates morphological operations, median filtering, and distance-field resizing
via OpenCV's `cv2.UMat` OpenCL transparent queue when `pyopencl` is not installed
but `cv2.ocl.useOpenCL()` is active.
"""

from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np

from .cpu_math import (
    eval_adf_biquadratic_cpu,
    eval_msdf_median3_reconstruct_cpu,
    eval_otsu_linear_threshold_cpu,
    eval_sdf_smoothstep_cpu,
    eval_srgb_to_linear_grayscale_cpu,
)


def is_opencv_umat_opencl_active() -> bool:
    try:
        if hasattr(cv2, "ocl") and cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(True)
            return bool(cv2.ocl.useOpenCL())
    except Exception:
        pass
    return False


def umat_median_blur(arr: np.ndarray, ksize: int) -> np.ndarray:
    if ksize <= 1 or arr.size == 0:
        return arr
    try:
        u = cv2.UMat(arr)
        res = cv2.medianBlur(u, ksize)
        return res.get()
    except Exception:
        return cv2.medianBlur(arr, ksize)


def umat_morphology_close(arr: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    try:
        u = cv2.UMat(arr)
        res = cv2.morphologyEx(u, cv2.MORPH_CLOSE, kernel)
        return res.get()
    except Exception:
        return cv2.morphologyEx(arr, cv2.MORPH_CLOSE, kernel)


__all__ = [
    "is_opencv_umat_opencl_active",
    "umat_median_blur",
    "umat_morphology_close",
    "eval_srgb_to_linear_grayscale_cpu",
    "eval_sdf_smoothstep_cpu",
    "eval_msdf_median3_reconstruct_cpu",
    "eval_adf_biquadratic_cpu",
    "eval_otsu_linear_threshold_cpu",
]
