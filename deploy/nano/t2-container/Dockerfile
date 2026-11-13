# T2 probe: Python 3.12 with the CSI camera inside an L4T container.
# The NVIDIA runtime mounts the host's Argus and nv* GStreamer plugins (l4t.csv);
# run with --runtime nvidia -v /tmp/argus_socket:/tmp/argus_socket.
# Build context: this Dockerfile, deploy/nano/camera_probe.py and the uv 0.13.1
# aarch64 musl binary (checksum verified beforehand).
FROM nvcr.io/nvidia/l4t-base:r32.7.1

# The base image already ships gst-launch-1.0 and the base plugins.
COPY uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_CACHE_DIR=/tmp/uv-cache
RUN uv python install 3.12.15 \
    && uv venv --python 3.12.15 /opt/venv \
    && uv pip install --python /opt/venv --only-binary :all: numpy==2.5.4 \
    && rm -rf /tmp/uv-cache

COPY camera_probe.py /opt/camera_probe.py
ENTRYPOINT ["/opt/venv/bin/python", "/opt/camera_probe.py"]
