# /// script
# dependencies = ["marimo"]
#
# [tool.marimo.k8s]
# storage = "1Gi"
# ///

import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Welcome to marimo on Kubernetes!

    This notebook introduces marimo's **reactive execution model** — if you're
    coming from Jupyter, this is the key difference to understand.
    """)
    return


@app.cell
def _(mo):
    slider = mo.ui.slider(1, 10, value=5, label="Pick a number")
    slider
    return (slider,)


@app.cell(hide_code=True)
def _(mo, slider):
    mo.md(
        f"""
    ## Reactive execution

    You picked **{slider.value}**. Try moving the slider above!

    Unlike Jupyter, marimo automatically re-runs cells when their dependencies
    change. When you moved that slider, this cell re-ran instantly — no need
    to manually execute anything.

    **Key differences from Jupyter:**

    1. **No hidden state** — The notebook state always matches what you see
    2. **Cells run in dependency order** — Not top-to-bottom, but based on
       which variables each cell uses
    3. **No cell numbers** — Order on the page doesn't determine execution order
    """
    )
    return


@app.cell
def _(mo, slider):
    result = slider.value**2
    mo.md(f"""
    ## Automatic updates

    The square of {slider.value} is **{result}**.

    This cell depends on `slider.value`, so it updates automatically when you
    interact with the slider. marimo tracks these dependencies for you.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Next steps

    - **Edit this notebook** — Your changes persist to storage
    - **Try more UI elements** — `mo.ui.dropdown()`, `mo.ui.text()`,
      `mo.ui.checkbox()`, and [more](https://docs.marimo.io/api/inputs/)
    - **Run as an app** — Use `kubectl marimo run` to serve as a read-only
      dashboard
    """)
    return


@app.cell
def _():
    import marimo as mo

    return (mo,)


if __name__ == "__main__":
    app.run()
