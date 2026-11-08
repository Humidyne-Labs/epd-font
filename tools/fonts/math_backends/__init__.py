#!/usr/bin/env python3
"""
math_backends/__init__.py (v1.0.19c)
====================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Modular Mathematical Abstraction & Hardware-Checked GPU/CPU Dispatch Package (v1.0.19c):
Abstracts all distance-field, polynomial root-finding, luminance linearization, and
thresholding math into dedicated backend modules (`opencl_kernels.py`, `umat_math.py`,
`cpu_math.py`) with automatic runtime hardware detection and fallback (`hw_dispatch.py`).
"""

from __future__ import annotations

from .cpu_math import (
    distance_sq_to_bezier_yuksel_cpu,
    eval_adf_biquadratic_cpu,
    eval_msdf_median3_reconstruct_cpu,
    eval_otsu_linear_threshold_cpu,
    eval_sdf_smoothstep_cpu,
    eval_srgb_to_linear_grayscale_cpu,
)
from .hw_dispatch import (
    MathBackendStatus,
    describe_math_backend,
    dispatch_adf_biquadratic,
    dispatch_bezier_sdf_yuksel,
    dispatch_median_blur,
    dispatch_morphology_close,
    dispatch_msdf_median3_reconstruct,
    dispatch_otsu_linear_threshold,
    dispatch_sdf_smoothstep,
    dispatch_srgb_to_linear_grayscale,
    get_active_math_backend,
    select_math_backend,
)
from .opencl_kernels import (
    HAS_PYOPENCL,
    OPENCL_MATH_KERNELS_SOURCE,
    OpenCLMathAccelerator,
    validate_sdf_gradient,
)

__all__ = [
    "HAS_PYOPENCL",
    "OPENCL_MATH_KERNELS_SOURCE",
    "OpenCLMathAccelerator",
    "MathBackendStatus",
    "validate_sdf_gradient",
    "get_active_math_backend",
    "select_math_backend",
    "describe_math_backend",
    "dispatch_srgb_to_linear_grayscale",
    "dispatch_sdf_smoothstep",
    "dispatch_msdf_median3_reconstruct",
    "dispatch_adf_biquadratic",
    "dispatch_otsu_linear_threshold",
    "dispatch_median_blur",
    "dispatch_morphology_close",
    "dispatch_bezier_sdf_yuksel",
    "distance_sq_to_bezier_yuksel_cpu",
    "eval_srgb_to_linear_grayscale_cpu",
    "eval_sdf_smoothstep_cpu",
    "eval_msdf_median3_reconstruct_cpu",
    "eval_adf_biquadratic_cpu",
    "eval_otsu_linear_threshold_cpu",
]
