from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
import logging

# from skopt import BayesSearchCV


class HyperparamSearch:
    """Performs hyperparameter search for a given model."""

    def __init__(self, X, y, cv, n_jobs, niter=20, logger=None):
        """Initializes a HyperparamSearch object.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The training input samples.
        y : array-like, shape (n_samples,) or (n_samples, n_outputs)
            The target values (class labels in classification, real numbers in
            regression).
        cv : int
            Number of folds in the cross-validation.
        n_jobs : int
            Number of jobs to run in parallel.
        niter : int, default=20
            Number of parameter settings that are sampled.
        logger : logging.Logger
            Logger object.
        """
        self.X = X
        self.y = y
        self.cv = cv
        self.n_jobs = n_jobs
        self.niter = niter
        self.logger = logger
        self.best_params = {}

    def search(self, model, param_grid=None):
        """Performs hyperparameter search for a given model.

        Parameters
        ----------
        model : sklearn.pipeline.Pipeline
            Model to be optimized.
        param_grid : dict, default=None
            Dictionary with parameters names (string) as keys and lists of
            parameter settings to try as values, or a list of such dictionaries,
            in which case the grids spanned by each dictionary in the list are
            explored. This enables searching over any sequence of parameter
            settings. Parameters names should be prefixed with "model__" to indicate that
            they are parameters of the model.

        Returns
        -------
        model : sklearn.pipeline.Pipeline
            Model pipeline with optimized parameters.
        """
        model_name = type(model.named_steps["model"]).__name__
        self.logger.info(f"Performing grid search for {model_name}...")

        try:
            # TODO: checks that parameters
            if param_grid is None:
                param_grid = model.named_steps["model"].get_grid_params()
            else:
                param_grid = self.check_param_grid(param_grid, model)

            grid_search = RandomizedSearchCV(
                model, param_grid, n_iter=self.niter, cv=self.cv, n_jobs=self.n_jobs
            )
            grid_search.fit(self.X, self.y)

            best_params = grid_search.best_params_
            self.logger.info(f"Best parameters for {model_name}: {best_params}")

            self.best_params = best_params
        except Exception as e:
            self.logger.error(f"Error during grid search for {model_name}: {e}")
            raise
        return model

    @staticmethod
    def check_param_grid(param_grid, model):
        """Checks that the parameter grid is valid.

        Parameters
        ----------
        param_grid : dict, default=None
            Dictionary with parameters names (string) as keys and lists of
            parameter settings to try as values, or a list of such dictionaries,
            in which case the grids spanned by each dictionary in the list are
            explored. This enables searching over any sequence of parameter
            settings. Parameters names should be prefixed with "model__" to indicate that
            they are parameters of the model.
        model : sklearn.pipeline.Pipeline
            Model to be optimized.

        Returns
        -------
        param_grid : dict
        """
        if type(param_grid) != dict:
            raise TypeError("param_grid must be a dictionary")
        for key, value in param_grid.items():
            if type(key) != str:
                raise TypeError("param_grid keys must be strings")
            if type(value) != list:
                raise TypeError("param_grid values must be lists")

        # check that the parameters start with "model__" prefix are
        # actually parameters of the model
        model_params = model.named_steps["model"].get_params()
        for key in param_grid.keys():
            if key.startswith("model__"):
                if key.split("__")[1] not in model_params.keys():
                    raise ValueError(
                        f"{key} is not a parameter of {type(model.named_steps['model']).__name__}"
                    )
        return param_grid
