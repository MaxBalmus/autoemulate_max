import numpy as np
import pandas as pd
import pytest

from autoemulate.emulators import GaussianProcessSk
from autoemulate.emulators import RandomForest
from autoemulate.printing import _print_cv_results

# prep inputs
models = {"GaussianProcesses": GaussianProcessSk, "RandomForest": RandomForest}

# make scores_df
metrics = ["rmse", "r2"]
model_names = models.keys()
data = []
for model in model_names:
    for metric in metrics:
        for fold in range(5):
            score = (
                np.random.uniform(-5000, 5000)
                if metric == "rmse"
                else np.random.uniform(-1, 1)
            )
            data.append(
                {"model": model, "metric": metric, "fold": fold, "score": score}
            )
scores_df = pd.DataFrame(data)


def test_print_results_all_models(capsys):
    _print_cv_results(models, scores_df)
    captured = capsys.readouterr()
    assert "Average scores across all models:" in captured.out
    assert "model" in captured.out


def test_print_results_single_model(capsys):
    _print_cv_results(models, scores_df, model="GaussianProcesses")
    captured = capsys.readouterr()
    assert "Scores for GaussianProcesses across all folds:" in captured.out
    assert "fold" in captured.out
    assert "metric" in captured.out


def test_print_results_invalid_model():
    with pytest.raises(ValueError):
        _print_cv_results(models, scores_df, model="InvalidModel")
