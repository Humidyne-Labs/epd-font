#!/usr/bin/env python3
"""
math_backends/__init__.py (v1.0.23)
===================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Modular Mathematical Abstraction & Hardware-Checked 3D NDRange GPU/CPU Dispatch Package (v1.0.23):
Abstracts all distance-field, polynomial root-finding, luminance linearization, Jump Flooding
Algorithm (`1+JFA`) + Marching Squares (`svg-potrace-jfa`), and thresholding math into dedicated
backend modules (`opencl_kernels.py`, `umat_math.py`, `cpu_math.py`) with automatic runtime
hardware detection, 75% Dynamic Shared Host/GPU RAM (`CL_MEM_ALLOC_HOST_PTR` + `clEnqueueMapBuffer`),
4-queue hardware striping, and deterministic teardown (`hw_dispatch.py`).
"""

from __future__ import annotations

from .cpu_math import (
    eval_adf_biquadratic_cpu,
    eval_jfa_marching_squares_cpu,
    eval_msdf_median3_reconstruct_cpu,
    eval_otsu_linear_threshold_cpu,
    eval_sdf_smoothstep_cpu,
    eval_srgb_to_linear_grayscale_cpu,
)
from .hw_dispatch import (
    MathBackendStatus,
    OpenCLDeviceDescriptor,
    describe_math_backend,
    dispatch_adf_biquadratic,
    dispatch_jfa_marching_squares,
    dispatch_median_blur,
    dispatch_morphology_close,
    dispatch_msdf_median3_reconstruct,
    dispatch_otsu_linear_threshold,
    dispatch_pipeline_batch_3d,
    dispatch_sdf_smoothstep,
    dispatch_srgb_to_linear_grayscale,
    enumerate_opencl_devices,
    get_active_math_backend,
    get_math_backend_telemetry,
    select_math_backend,
    teardown_math_backends,
)
from .opencl_kernels import (
    HAS_PYOPENCL,
    OPENCL_MATH_KERNELS_SOURCE,
    SHARED_RAM_CAP_RATIO,
    OpenCLMathAccelerator,
    SharedHostMemoryArena,
    detect_shared_gpu_memory_mb,
    release_all_opencl_resources,
    validate_sdf_gradient,
)

__all__ = [
    "HAS_PYOPENCL",
    "OPENCL_MATH_KERNELS_SOURCE",
    "SHARED_RAM_CAP_RATIO",
    "OpenCLMathAccelerator",
    "SharedHostMemoryArena",
    "MathBackendStatus",
    "OpenCLDeviceDescriptor",
    "detect_shared_gpu_memory_mb",
    "release_all_opencl_resources",
    "teardown_math_backends",
    "enumerate_opencl_devices",
    "validate_sdf_gradient",
    "get_active_math_backend",
    "get_math_backend_telemetry",
    "select_math_backend",
    "describe_math_backend",
    "dispatch_pipeline_batch_3d",
    "dispatch_srgb_to_linear_grayscale",
    "dispatch_sdf_smoothstep",
    "dispatch_msdf_median3_reconstruct",
    "dispatch_adf_biquadratic",
    "dispatch_otsu_linear_threshold",
    "dispatch_jfa_marching_squares",
    "dispatch_median_blur",
    "dispatch_morphology_close",
    "eval_srgb_to_linear_grayscale_cpu",
    "eval_sdf_smoothstep_cpu",
    "eval_msdf_median3_reconstruct_cpu",
    "eval_adf_biquadratic_cpu",
    "eval_otsu_linear_threshold_cpu",
    "eval_jfa_marching_squares_cpu",
]
