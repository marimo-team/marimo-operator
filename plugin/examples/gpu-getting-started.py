# /// script
# dependencies = ["marimo", "torch"]
#
# [tool.marimo.k8s]
# storage = "1Gi"
#
# [tool.marimo.k8s.resources]
# limits."nvidia.com/gpu" = 1
# ///

import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    mo.md("""
    # GPU Computing with marimo

    This notebook demonstrates GPU access and **caching** for expensive
    computations.
    """)
    return (mo,)


@app.cell
def _(mo):
    import torch

    gpu_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if gpu_available else "N/A"
    device = "cuda" if gpu_available else "cpu"

    mo.md(f"""
    ## GPU Status

    | Property | Value |
    |----------|-------|
    | CUDA Available | {gpu_available} |
    | Device | {device_name} |
    | PyTorch Version | {torch.__version__} |
    """)
    return device, torch


@app.cell
def _(mo):
    size_slider = mo.ui.slider(100, 2000, value=500, step=100, label="Matrix size")
    size_slider
    return (size_slider,)


@app.cell
def _(device, mo, size_slider, torch):
    @mo.persistent_cache
    def matrix_multiply(n: int, device: str):
        """Cached matrix multiplication — results saved to disk."""
        a = torch.randn(n, n, device=device)
        b = torch.randn(n, n, device=device)
        result = torch.mm(a, b)
        return result.shape, str(result.device)

    shape, result_device = matrix_multiply(size_slider.value, device)

    mo.md(f"""
    ## Persistent Cache

    Matrix multiplication: **{size_slider.value}×{size_slider.value}**

    - Result shape: `{shape}`
    - Computed on: `{result_device}`

    The `@mo.persistent_cache` decorator saves results to disk. This means:

    1. **Results survive notebook restarts** — no need to re-run expensive
       computations when you reopen the notebook
    2. **Evaluate without GPU** — compute results on GPU once, then analyze
       on cheaper CPU instances by reading from cache
    3. **Share results** — cached data persists in storage, accessible
       across sessions
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Caching strategies

    | Decorator | Persists | Use case |
    |-----------|----------|----------|
    | `@mo.cache` | In memory only | Fast, repeated calls in same session |
    | `@mo.persistent_cache` | To disk | Expensive GPU ops, survive restarts |

    **Tip**: Run expensive training/inference on GPU, then switch to a CPU
    instance for visualization and analysis — the persistent cache lets you
    access results without re-computing.

    See [marimo caching docs](https://docs.marimo.io/api/caching/) for more.
    """)
    return


if __name__ == "__main__":
    app.run()
