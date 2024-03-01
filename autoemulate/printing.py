from autoemulate.utils import get_mean_scores
from autoemulate.utils import get_model_name
from autoemulate.utils import get_model_scores


def _print_cv_results(models, scores_df, model_name=None, sort_by="r2"):
    """Print cv results.

    Parameters
    ----------
    models : list
        A list of models.
    scores_df : pandas.DataFrame
        A dataframe with scores for each model, metric, and fold.
    model_name : str, optional
        The name of the model to print. If None, the best fold from each model will be printed.
        If a model name is provided, the scores for that model across all folds will be printed.
    sort_by : str, optional
        The metric to sort by. Default is "r2".

    """
    # check if model is in self.models
    if model_name is not None:
        model_names = [get_model_name(mod) for mod in models]
        if model_name not in model_names:
            raise ValueError(
                f"Model {model_name} not found. Available models are: {model_names}"
            )
    if model_name is None:
        means = get_mean_scores(scores_df, metric=sort_by)
        print("Average scores across all models:")
        print(means)
    else:
        scores = get_model_scores(scores_df, model_name)
        print(f"Scores for {model_name} across all folds:")
        print(scores)
