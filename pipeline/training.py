from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


def build_model(C=1.0, max_iter=1000):
    print("Applying StandardScaler")
    return Pipeline([
        ("scaler", StandardScaler()),
        (
            "model",
            LogisticRegression(
                C=C,
                max_iter=max_iter
            )
        )
    ])


def train_model(x_train, y_train, C=1.0, max_iter=1000):
    print("Training Model...")
    model = build_model(C, max_iter)
    model.fit(x_train, y_train)

    return model