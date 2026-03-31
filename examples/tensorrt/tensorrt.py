# /// script
# dependencies = ["marimo>=0.21.1", "setuptools"]
#
# [tool.marimo.k8s]
# image = "ghcr.io/marimo-team/marimo-operator/tensorrt:latest"
# storage = "20Gi"
#
# [tool.marimo.k8s.resources]
# limits."nvidia.com/gpu" = 1
#
# [tool.marimo.k8s.nodeSelector]
# "gpu.nvidia.com/class" = "L40"
#
# ///

import marimo

__generated_with = "0.21.1"
app = marimo.App(width="medium")

with app.setup:
    import gc
    import io
    import logging

    import marimo as mo
    import torch
    from tensorrt_llm import LLM, SamplingParams


@app.cell
def _():
    # Collect TRT-LLM / torch log lines emitted during model load so we can
    # surface them in the notebook rather than losing them to pod stdout.
    log_stream = io.StringIO()
    logging.basicConfig(stream=log_stream, level=logging.WARNING)

    models = {
        "TinyLlama 1.1B (fast)": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        "Phi-3.5-mini 3.8B": "microsoft/Phi-3.5-mini-instruct",
        "Mistral 7B": "mistralai/Mistral-7B-Instruct-v0.3",
        "Llama-3.1 8B FP8 (NVIDIA)": "nvidia/Llama-3.1-8B-Instruct-FP8",
        "Minitron 8B (NVIDIA)": "nvidia/Mistral-NeMo-Minitron-8B-Instruct",
    }

    prompts = [
        "Hello, my name is",
        "The capital of France is",
        "The future of AI is",
    ]

    prompt = mo.ui.dropdown(
        label="Select a Prompt",
        options=prompts,
        value=prompts[0],
    )

    model_picker = mo.ui.dropdown(
        label="Model",
        options=models,
        value="TinyLlama 1.1B (fast)",
    )

    mo.vstack([
        mo.md("## TensorRT-LLM Inference Example, select a model to download and run"),
        model_picker,
    ])
    return log_stream, model_picker, models, prompt, prompts


@app.cell
def _(log_stream, model_picker):
    mo.stop(model_picker.value is None)

    # Free the previous model's GPU memory before loading the next one.
    # Without this, two models can coexist briefly and OOM a 48 GB L40.
    gc.collect()
    torch.cuda.empty_cache()

    # Model can be a HuggingFace model name, a local path, or a quantized
    # checkpoint such as nvidia/Llama-3.1-8B-Instruct-FP8 on HF.
    llm = LLM(model=model_picker.value)

    # Show any WARNING+ log lines collected during model load.
    logs = log_stream.getvalue()
    mo.accordion({"Model load logs": mo.plain_text(logs) if logs else mo.md("_No warnings._")})
    return (llm,)


@app.cell(hide_code=True)
def _(llm, prompt):
    sampling_params = SamplingParams(temperature=0.8, top_p=0.95)

    results = []
    for output in llm.generate([prompt.value], sampling_params):
        results.append(
            mo.md(
                f"**Prompt:** {output.prompt}  \n"
                f"**Generated:** {output.outputs[0].text}"
            )
        )

    mo.vstack([prompt, mo.vstack(results)])


if __name__ == "__main__":
    app.run()
