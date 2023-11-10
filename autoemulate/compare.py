from autoemulate.metrics import METRIC_REGISTRY
from autoemulate.emulators import MODEL_REGISTRY
from autoemulate.cv import CV_REGISTRY
from autoemulate.logging_config import configure_logging
from autoemulate.plotting import plot_results

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sklearn.utils.validation import check_X_y
from sklearn.model_selection import cross_validate
from sklearn.metrics import make_scorer
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler
from skopt import BayesSearchCV


class AutoEmulate:
    def __init__(self):
        """Initializes an AutoEmulate object."""
        self.X = None
        self.y = None
        self.is_set_up = False
        self.scaler = None

    def setup(
        self,
        X,
        y,
        hyperparameter_search=False,
        normalise=True,
        fold_strategy="kfold",
        folds=5,
        n_jobs=None,
        log_to_file=False,
    ):
        """Sets up the automatic emulation.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Simulation input.
        y : array-like, shape (n_samples, n_outputs)
            Simulation output.
        hyperparameter_search : bool
            Whether to perform hyperparameter search over predifined parameter grids.
        normalise : bool, default=False
            Whether to normalise the data before fitting the models. Currently only
            z-transformation using StandardScaler.
        fold_strategy : str
            Cross-validation strategy, currently either "kfold" or "stratified_kfold".
        folds : int
            Number of folds.
        n_jobs : int
            Number of jobs to run in parallel. `None` means 1, `-1` means using all processors.
        log_to_file : bool
            Whether to log to file.
        """
        self.X, self.y = check_X_y(
            X, y, multi_output=True, y_numeric=True, dtype="float32"
        )
        self.y = self.y.astype("float32")  # needed for pytorch models

        if normalise:
            self.scaler = StandardScaler()
            self.X = self.scaler.fit_transform(self.X)

        self.models = [model() for model in MODEL_REGISTRY.values()]
        self.metrics = [metric for metric in METRIC_REGISTRY.keys()]
        self.cv = CV_REGISTRY[fold_strategy](folds=folds, shuffle=True)
        self.hyperparameter_search = hyperparameter_search
        self.normalise = normalise
        self.n_jobs = n_jobs
        self.logger = configure_logging(log_to_file=log_to_file)
        self.is_set_up = True
        self.cv_results = {}

    def compare(self):
        """Compares the emulator models on the data. self.setup() must be run first.

        Returns
        -------
        scores_df : pandas.DataFrame
            Dataframe containing the scores for each model, metric and fold.
        """
        if not self.is_set_up:
            raise RuntimeError("Must run setup() before compare()")

        # Freshly initialise scores dataframe when running compare()
        self.scores_df = pd.DataFrame(
            columns=["model", "metric", "fold", "score"]
        ).astype(
            {"model": "object", "metric": "object", "fold": "int64", "score": "float64"}
        )

        for model in self.models:
            # search for best hyperparameters
            if self.hyperparameter_search:
                self.hyperparam_search(model)
            # run cv
            self.cross_validate(model)

    def cross_validate(self, model):
        """Perform cross-validation on a given model using the specified metrics.

        Parameters
        ----------
            model: A scikit-learn estimator object.

        Class attributes used
        ---------------------
            self.X : array-like, shape (n_samples, n_features)
                Simulation input.
            self.y : array-like, shape (n_samples, n_outputs)
                Simulation output.
            self.cv : scikit-learn cross-validation object
                Cross-validation strategy.
            self.metrics : list of str
                List of metrics to use for cross-validation.
            self.n_jobs : int
                Number of jobs to run in parallel. `None` means 1, `-1` means using all processors.

        Returns
        -------
            scores_df : pandas.DataFrame
                Dataframe containing the scores for each model, metric and fold.

        """

        # Get model name
        model_name = type(model).__name__

        # The metrics we want to use for cross-validation
        scorers = {name: make_scorer(METRIC_REGISTRY[name]) for name in self.metrics}

        self.logger.info(f"Cross-validating {model_name}...")
        self.logger.info(f"Parameters: {model.get_params()}")

        # Cross-validate
        cv_results = cross_validate(
            model,
            self.X,
            self.y,
            cv=self.cv,
            scoring=scorers,
            n_jobs=self.n_jobs,
            return_estimator=True,
            return_indices=True,
        )
        self._update_scores_df(model_name, cv_results)

    def _update_scores_df(self, model_name, cv_results):
        """Updates the scores dataframe with the results of the cross-validation.

        Parameters
        ----------
            model_name : str
                Name of the model.
            cv_results : dict
                Results of the cross-validation.

        Returns
        -------
            scores_df : pandas.DataFrame
                Dataframe containing the scores for each model, metric and fold.

        """
        # Gather scores from each metric
        # Initialise scores dataframe
        for key in cv_results.keys():
            if key.startswith("test_"):
                for fold, score in enumerate(cv_results[key]):
                    self.scores_df.loc[len(self.scores_df.index)] = {
                        "model": model_name,
                        "metric": key.split("test_", 1)[1],
                        "fold": fold,
                        "score": score,
                    }
        # save results for plotting etc.
        self.cv_results[model_name] = cv_results

    def hyperparam_search(self, model):
        """Performs hyperparameter search for a given model.

        Parameters
        ----------
        model : object
            Emulator model.

        Returns
        -------
        model : object
            Emulator model with updated parameters.
        """
        model_name = type(model).__name__
        self.logger.info(f"Performing grid search for {model_name}...")
        param_grid = model.get_grid_params()  # Grid search
        grid_search = GridSearchCV(model, param_grid, cv=self.cv, n_jobs=self.n_jobs)
        # grid_search = BayesSearchCV(model, param_grid, cv=self.cv, n_jobs=self.n_jobs)
        grid_search.fit(self.X, self.y)
        best_params = grid_search.best_params_
        self.logger.info(f"Best parameters for {model_name}: {best_params}")
        model.set_params(**best_params)  # Update the model with the best parameters

    def print_scores(self, model=None):
        # check if model is in self.models
        if model is not None:
            model_names = [type(model).__name__ for model in self.models]
            if model not in model_names:
                raise ValueError(
                    f"Model {model} not found. Available models are: {model_names}"
                )
        if model is None:
            means = (
                self.scores_df.groupby(["model", "metric"])["score"]
                .mean()
                .unstack()
                .reset_index()
            )
            print("Average scores across all models:")
            print(means)
        else:
            scores = self.scores_df[self.scores_df["model"] == model].pivot(
                index="fold", columns="metric", values="score"
            )
            print(f"Scores for {model} across all folds:")
            print(scores)

    def plot_results(self, model_name=None):
        """Plots the results of the cross-validation.

        Parameters
        ----------
        model_name : str
            Name of the model to plot. If None, plots best folds of each models.
            If a model name is specified, plots all folds of that model.
        """
        plot_results(self.cv_results, self.X, self.y, model_name=model_name)
