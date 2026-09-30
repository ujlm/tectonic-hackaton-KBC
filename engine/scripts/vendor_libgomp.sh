#!/bin/sh
# Vercel's Python runtime has no libgomp.so.1 (OpenMP), which LightGBM needs. Copy it from the build image
# into app/_native/; app/__init__.py preloads it before LightGBM is imported.
set -e
mkdir -p app/_native
for p in /usr/lib64/libgomp.so.1 /usr/lib/x86_64-linux-gnu/libgomp.so.1 /lib64/libgomp.so.1; do
  if [ -f "$p" ]; then cp -L "$p" app/_native/libgomp.so.1; echo "vendored $p"; exit 0; fi
done
if command -v dnf >/dev/null 2>&1; then
  dnf install -y libgomp >/dev/null 2>&1 && cp -L /usr/lib64/libgomp.so.1 app/_native/libgomp.so.1 && echo "installed and vendored libgomp" && exit 0
fi
echo "libgomp.so.1 not found in the build image" >&2
exit 1
