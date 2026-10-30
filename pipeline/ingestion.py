from sklearn.datasets import load_breast_cancer


def load_data():
    data = load_breast_cancer(as_frame=True)

    df = data.frame.copy()

    x = df.drop(columns=["target"])
    y = df["target"]

    return x, y