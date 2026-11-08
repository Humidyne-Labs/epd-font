import pyopencl as cl

def list_all_devices():
    available = []
    for p_idx, platform in enumerate(cl.get_platforms()):
        for d_idx, device in enumerate(platform.get_devices()):
            dev_type = cl.device_type.to_string(device.type)
            available.append((p_idx, d_idx, device.name, dev_type, device.max_compute_units))
            print(f"[{len(available)-1}] Platform {p_idx}, Device {d_idx}: {device.name} ({dev_type}) - {device.max_compute_units} CUs")
    return available

if __name__ == "__main__":
    list_all_devices()