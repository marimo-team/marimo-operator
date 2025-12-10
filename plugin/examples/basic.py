import marimo

__generated_with = "0.16.4"
app = marimo.App()


@app.cell
def hello():
    return


@app.cell
def _():
    print("In notebook.py")
    return


if __name__ == "__main__":
    app.run()
