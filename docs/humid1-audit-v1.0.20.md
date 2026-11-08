# Humid1 Audit (rev++ v1.0.20)
- So, I'm not seeing all the compute cores being used on the GPU when testing.
       - test script says, "Max Work-Item Dimensions: 3", but only one was used.
	   - task manager says we have 15GB worth of shared ram available, can we use it?
	   - task manager shows 2GB being used after terminating the application script.
	   - Is this due to a deinit issue or leak? it 'should' let go of the alloc mem durring taredown.
- I was unable to test the revision fully, it was taking too long.
       - I did however install all depends, and everything is 'working'
       - When I "CRTL+C", is the terminal suposed to say stuff? see attached log.
	   
# Runtime for OpenCL Installed
- installed, [Intel CPU Runtime for OpenCL Applications](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html)
       - says, "[0] Platform 0, Device 0: Ellesmere (ALL | GPU) - 32 CUs", "[1] Platform 1, Device 0: AMD Ryzen 5 5600G with Radeon Graphics (ALL | CPU) - 12 CUs"