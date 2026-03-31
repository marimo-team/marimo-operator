FROM nvcr.io/nvidia/tritonserver:25.01-trtllm-python-py3

# The marimo operator requires:
# 1. uv  — setup-venv init container runs: uv venv /opt/venv
# 2. marimo binary in PATH — main container command is: marimo run/edit ...
RUN pip install uv "marimo>=0.21.1"

# The operator launches the container without running the NVIDIA entrypoint, so
# env vars it would normally set must be baked in here instead.

# uv is pip-installed to /usr/local/bin; operator hardcodes /usr/bin
ENV UV="/usr/local/bin/uv"

# TensorRT-LLM is in dist-packages (Ubuntu pip convention); operator venv lands at /opt/venv
ENV PYTHONPATH="/usr/local/lib/python3.12/dist-packages:/opt/venv/lib/python3.12/site-packages"

# TensorRT/cuBLAS .so files (entrypoint normally adds these to LD_LIBRARY_PATH)
ENV LD_LIBRARY_PATH="/usr/local/tensorrt/targets/x86_64-linux-gnu/lib:/usr/local/cuda/lib64:/usr/local/cuda/compat/lib:/usr/local/lib/python3.12/dist-packages/tensorrt_llm/libs:/usr/local/lib/python3.12/dist-packages/torch/lib:/usr/local/lib/python3.12/dist-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/dist-packages/nvidia/cuda_runtime/lib"

# Reduce TRT-LLM log noise by default; notebooks can override if needed.
ENV TRTLLM_LOG_LEVEL="WARNING"
