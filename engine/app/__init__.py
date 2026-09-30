"""Kate engine."""
import ctypes
import os
import sys

# LightGBM needs OpenMP (libgomp.so.1). Vercel's Python runtime doesn't ship it, so the build vendors a copy
# (scripts/vendor_libgomp.sh) and we load it globally before anything imports LightGBM.
_GOMP = os.path.join(os.path.dirname(__file__), "_native", "libgomp.so.1")
if sys.platform.startswith("linux") and os.path.exists(_GOMP):
    ctypes.CDLL(_GOMP, mode=ctypes.RTLD_GLOBAL)
