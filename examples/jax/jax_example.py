# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "flax>=0.10.0",
#     "jax[cuda12]>=0.4.0",
#     "marimo>=0.21.1",
#     "matplotlib==3.10.8",
#     "mofresh",
#     "optax>=0.2.0",
#     "polars>=1.0",
# ]
#
# [tool.marimo.runtime]
# auto_instantiate = false
#
# [tool.marimo.k8s]
# storage = "5Gi"
#
# [tool.marimo.k8s.resources]
# limits."nvidia.com/gpu" = 1
#
# [tool.marimo.k8s.nodeSelector]
# "gpu.nvidia.com/class" = "L40"
# ///

import marimo

__generated_with = "0.21.1"
app = marimo.App(width="columns", auto_download=["html"])

with app.setup(hide_code=True):
    import marimo as mo
    import jax
    import jax.numpy as jnp
    import flax.linen as nn
    import optax
    import polars as pl
    import numpy as np


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    marimo's multi-column layout offers a unique live preview as you work.
    """)
    return


@app.cell
def _():
    import matplotlib.pylab as plt
    from mofresh import refresh_matplotlib, ImageRefreshWidget

    widget = ImageRefreshWidget(src="")

    @refresh_matplotlib
    def losschart(data):
        df = pl.DataFrame(data)
        plt.plot(df["epoch"], df["loss_train"])

    widget
    return losschart, widget


@app.cell
def _():
    return


@app.cell(column=1, hide_code=True)
def _():
    mo.md(r"""
    Example network and training with `jax`
    """)
    return


@app.cell
def _(losschart, widget):
    datalogs = []

    def train_identity_network(data, epochs=5000, learning_rate=0.025, iteration=0):
        rng = jax.random.PRNGKey(42)
        x = jnp.array(data, dtype=jnp.float32)

        model = IdentityNetwork()
        params = model.init(rng, x)

        optimizer = optax.sgd(learning_rate)
        opt_state = optimizer.init(params)

        def loss_fn(p, batch):
            return jnp.mean((model.apply(p, batch) - batch) ** 2)

        for epoch in range(epochs):
            loss, grads = jax.value_and_grad(loss_fn)(params, x)
            updates, opt_state = optimizer.update(grads, opt_state)
            params = optax.apply_updates(params, updates)

            if (epoch + 1) % 25 == 0:
                test_data = jnp.array(np.random.rand(n, k), dtype=jnp.float32)
                test_loss = loss_fn(params, test_data)
                datalogs.append({
                    "epoch": epoch + iteration * epochs,
                    "loss_train": float(loss),
                    "loss_test": float(test_loss),
                })
                widget.src = losschart(datalogs)

        return params

    for i in range(1):
        n = 10000
        k = 10
        random_data = np.random.rand(n, k)
        trained_params = train_identity_network(random_data, epochs=5000, iteration=i)
    return


@app.class_definition
class IdentityNetwork(nn.Module):
    @nn.compact
    def __call__(self, x):
        features = x.shape[-1]
        x = nn.relu(nn.Dense(features)(x))
        x = nn.relu(nn.Dense(features)(x))
        return x


if __name__ == "__main__":
    app.run()
