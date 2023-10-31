from sklearn.utils.estimator_checks import parametrize_with_checks, _yield_all_checks
from autoemulate.emulators import (
    RandomForest,
    GaussianProcessSk,
    NeuralNetwork,
    GaussianProcess,
)
from functools import partial


@parametrize_with_checks(
    [  # GaussianProcess(),
        RandomForest(random_state=42),
        GaussianProcessSk(random_state=1337),
        NeuralNetwork(random_state=13),
    ]
)
def test_check_estimator(estimator, check):
    check(estimator)