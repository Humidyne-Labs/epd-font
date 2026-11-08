import pyopencl as cl

def inspect_pyopencl():
    platforms = cl.get_platforms()
    if not platforms:
        print("No OpenCL platforms detected. Check your GPU/CPU runtime drivers.")
        return

    for p_idx, platform in enumerate(platforms):
        print(f"\n================ Platform {p_idx}: {platform.name} ================")
        print(f"  Vendor:  {platform.vendor}")
        print(f"  Version: {platform.version}")
        print(f"  Profile: {platform.profile}")

        devices = platform.get_devices()
        for d_idx, device in enumerate(devices):
            dev_type = cl.device_type.to_string(device.type)
            print(f"\n  --- Device {d_idx}: {device.name} [{dev_type}] ---")
            print(f"  Driver Version:               {device.driver_version}")
            print(f"  OpenCL C Version:             {device.opencl_c_version}")
            print(f"  Compute Units:                {device.max_compute_units}")
            print(f"  Max Clock Frequency:          {device.max_clock_frequency} MHz")
            print(f"  Global Memory:                {device.global_mem_size / (1024**2):.2f} MB")
            print(f"  Local / Shared Memory:        {device.local_mem_size / 1024:.2f} KB")
            print(f"  Max Work-Group Size:          {device.max_work_group_size}")
            print(f"  Max Work-Item Dimensions:     {device.max_work_item_dimensions}")
            print(f"  Max Work-Item Sizes:          {device.max_work_item_sizes}")
            print(f"  Double Precision (FP64):      {'cl_khr_fp64' in device.extensions}")
            print(f"  Half Precision (FP16):        {'cl_khr_fp16' in device.extensions}")

if __name__ == "__main__":
    inspect_pyopencl()