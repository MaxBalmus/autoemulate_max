from copy import deepcopy

import gpytorch
import numpy as np
import torch
from scipy.stats import loguniform
from scipy.stats import randint
from sklearn.base import BaseEstimator
from sklearn.base import RegressorMixin
from sklearn.exceptions import DataConversionWarning
from sklearn.preprocessing._data import _handle_zeros_in_scale
from sklearn.utils import check_array
from sklearn.utils import check_X_y
from sklearn.utils.validation import check_is_fitted
from skorch.callbacks import EarlyStopping
from skorch.callbacks import LRScheduler
from skorch.callbacks import ProgressBar
from skorch.probabilistic import ExactGPRegressor

from autoemulate.emulators.neural_networks.gp_module import CorrGPModule
from autoemulate.utils import set_random_seed


class GaussianProcessTorch(RegressorMixin, BaseEstimator):
    """Exact Gaussian Process emulator build with GPyTorch.

    Parameters
    ----------
    mean_module : GP mean, defaults to gpytorch.means.ConstantMean() when None
    covar_module : GP covariance, defaults to gpytorch.kernels.RBFKernel() when None
    multitask : whether to use multitask GP, which models correlations between outputs. If False,
    each output is modeled independently, default=True
    lr : learning rate, default=1e-1
    optimizer : optimizer, default=torch.optim.AdamW
    max_epochs : maximum number of epochs, default=30
    normalize_y : whether to normalize the target values, default=True
    device : device to use, defaults to "cuda" if available, otherwise "cpu"
    random_state : random seed, default=None
    """

    def __init__(
        self,
        # architecture
        mean_module=None,
        covar_module=None,
        # training
        lr=2e-1,
        optimizer=torch.optim.AdamW,
        max_epochs=50,
        normalize_y=True,
        # misc
        device=None,
        random_state=None,
    ):
        self.mean_module = mean_module
        self.covar_module = covar_module
        self.lr = lr
        self.optimizer = optimizer
        self.max_epochs = max_epochs
        self.normalize_y = normalize_y
        self.device = device
        self.random_state = random_state

    def _get_module(self, module, default_class):
        """
        Get mean and kernel modules.

        We can't default the modules in the constructor because 'fit' modifies them which
        fails scikit-learn estimator tests. Therefore, we deepcopy if module is given or return the default class
        if not.
        """
        if module is None:
            return default_class
        return deepcopy(module)

    def fit(self, X, y):
        """Fit the emulator to the data.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            The input data.
        y : array-like of shape (n_samples, )
            The output data.
        Returns
        -------
        self : object
            Returns self.
        """
        if self.random_state is not None:
            set_random_seed(self.random_state)

        X, y = check_X_y(
            X,
            y,
            y_numeric=True,
            multi_output=True,
            dtype=np.float32,
            copy=True,
            ensure_2d=True,
        )
        self.y_dim_ = y.ndim
        self.n_features_in_ = X.shape[1]
        self.n_outputs_ = y.shape[1] if y.ndim > 1 else 1
        y = y.astype(np.float32)

        # Normalize target value
        # the zero handler is from sklearn
        if self.normalize_y:
            self._y_train_mean = np.mean(y, axis=0)
            self._y_train_std = _handle_zeros_in_scale(np.std(y, axis=0), copy=False)
            y = (y - self._y_train_mean) / self._y_train_std

        self.model_ = ExactGPRegressor(
            CorrGPModule,
            module__mean=self._get_module(
                self.mean_module, gpytorch.means.ConstantMean()
            ),
            module__covar=self._get_module(
                self.covar_module,
                gpytorch.kernels.RBFKernel().initialize(lengthscale=1.0)
                + gpytorch.kernels.ConstantKernel(),
            ),
            likelihood=gpytorch.likelihoods.MultitaskGaussianLikelihood(
                num_tasks=self.n_outputs_
            ),
            max_epochs=self.max_epochs,
            lr=self.lr,
            optimizer=self.optimizer,
            # callbacks=[EarlyStopping(patience=5)],
            callbacks=[
                (
                    "lr_scheduler",
                    LRScheduler(policy="ReduceLROnPlateau", patience=5, factor=0.5),
                ),
                (
                    "early_stopping",
                    EarlyStopping(monitor="train_loss", patience=10, threshold=1e-3),
                ),
            ],
            verbose=0,
            device=self.device
            if self.device is not None
            else "cuda"
            if torch.cuda.is_available()
            else "cpu",
        )
        self.model_.fit(X, y)
        self.is_fitted_ = True
        return self

    def predict(self, X, return_std=False):
        """Predict the output of the emulator.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            The input data.
        return_std : bool, default=False
            Whether to return the standard deviation.

        Returns
        -------
        y : array-like of shape (n_samples, )
            The predicted output.
        """

        # checks
        check_is_fitted(self)
        X = check_array(X, dtype=np.float32)

        # predict
        mean, std = self.model_.predict(X, return_std=True)

        # sklearn: regression models should return float64
        mean = mean.astype(np.float64)
        std = std.astype(np.float64)

        # output shape should be same as input shape
        # when input dim is 1D, make sure output is 1D
        if mean.ndim == 2 and self.y_dim_ == 1:
            mean = mean.squeeze()
            std = std.squeeze()

        # undo normalization
        if self.normalize_y:
            mean = mean * self._y_train_std + self._y_train_mean
            std = std * self._y_train_std

        if return_std:
            return mean, std
        return mean

    def get_grid_params(self, search_type="random"):
        """Returns the grid parameters for the emulator."""
        param_space = {
            "covar_module": [
                # TODO: initialize lengthscale for other kernels?
                gpytorch.kernels.RBFKernel().initialize(lengthscale=1.0),
                gpytorch.kernels.MaternKernel(nu=2.5),
                gpytorch.kernels.MaternKernel(nu=1.5),
                gpytorch.kernels.PeriodicKernel(),
                gpytorch.kernels.RQKernel(),
            ],
            "mean_module": [gpytorch.means.ConstantMean(), gpytorch.means.ZeroMean()],
            "optimizer": [torch.optim.AdamW, torch.optim.Adam, torch.optim.SGD],
            "lr": [5e-1, 1e-1, 5e-2, 1e-2],
            "max_epochs": [50, 100, 200],
            "normalize_y": [True, False],
        }
        return param_space

    @property
    def model_name(self):
        return self.__class__.__name__

    def _more_tags(self):
        # TODO: is it really non-deterministic?
        return {"multioutput": True, "non_deterministic": True}
