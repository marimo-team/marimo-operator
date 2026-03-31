# TensorRT-LLM Example

Interactive [TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM) inference notebook running on the marimo operator. Includes a model picker with several open-weight models and a reactive prompt selector.

Requires a GPU node with ≥ 24 GB VRAM. The included models range from ~3 GB (TinyLlama 1.1B) up to ~16 GB (Mistral 7B / Minitron 8B).

## Files

| File | Purpose |
|---|---|
| `tensorrt.py` | marimo notebook — deploy with the `kubectl-marimo` plugin |
| `tensorrt.yaml` | Plain `MarimoNotebook` manifest — deploy with `kubectl apply` |
| `Dockerfile` | Thin layer over the NVIDIA NGC TRT-LLM container |

## Deploy with the plugin

```bash
uv tool install kubectl-marimo

kubectl marimo edit tensorrt.py -n <namespace>
```

## Deploy with kubectl

```bash
# Edit nodeSelector if needed, then apply
kubectl apply -f tensorrt.yaml -n <namespace>

# Get the access token
kubectl logs -n <namespace> tensorrt -c marimo | grep access_token

# Port-forward to access locally
kubectl port-forward -n <namespace> svc/tensorrt 2718:2718
```

## Build the image

The pre-built image is at `ghcr.io/marimo-team/marimo-operator/tensorrt:latest` and is rebuilt on every push to main. To build your own:

```bash
docker build --platform linux/amd64 -t <your-registry>/tensorrt:latest .
docker push <your-registry>/tensorrt:latest
```

If your registry is private, create an image pull secret:

```bash
kubectl create secret docker-registry registry-secret \
  --docker-server=<registry> \
  --docker-username=<user> \
  --docker-password=<token> \
  -n <namespace>

kubectl patch serviceaccount default -n <namespace> \
  -p '{"imagePullSecrets":[{"name":"registry-secret"}]}'
```

## Further reading

- [TensorRT-LLM documentation](https://nvidia.github.io/TensorRT-LLM/)
- [FP8 quantization guide](https://nvidia.github.io/TensorRT-LLM/performance/performance-tuning-guide/fp8-quantization.html)
- [marimo operator](https://github.com/marimo-team/marimo-operator)
