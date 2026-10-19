import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def _():
    print("In notebook.py")


if __name__ == "__main__":
    app.run()
