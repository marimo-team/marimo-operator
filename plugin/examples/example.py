import marimo

__generated_with = "0.16.4"
app = marimo.App(width="medium")


@app.cell
def _():
    print("righto!")
    return


if __name__ == "__main__":
    app.run()
