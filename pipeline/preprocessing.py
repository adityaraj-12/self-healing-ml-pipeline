from sklearn.model_selection import train_test_split


def split_data(x, y, test_size=0.2, random_state=42):
    print("Data splited.")
    return train_test_split(
        x,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y
    )