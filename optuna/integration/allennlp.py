import json
import os
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union
import warnings

import optuna
from optuna._experimental import experimental
from optuna._imports import try_import

with try_import() as _imports:
    import allennlp.commands
    import allennlp.common.util

if _imports.is_successful():
    import _jsonnet


def dump_best_config(input_config_file: str, output_config_file: str, study: optuna.Study) -> None:
    """Save JSON config file after updating with parameters from the best trial in the study.

    Args:
        input_config_file:
            Input Jsonnet config file used with
            :class:`~optuna.integration.AllenNLPExecutor`.
        output_config_file:
            Output JSON config file.
        study:
            Instance of :class:`~optuna.study.Study`.
            Note that :func:`~optuna.study.Study.optimize` must have been called.

    """
    _imports.check()

    best_params = study.best_params
    for key, value in best_params.items():
        best_params[key] = str(value)
    best_config = json.loads(_jsonnet.evaluate_file(input_config_file, ext_vars=best_params))
    best_config = allennlp.common.params.infer_and_cast(best_config)

    with open(output_config_file, "w") as f:
        json.dump(best_config, f, indent=4)


@experimental("1.4.0")
class AllenNLPExecutor(object):
    """AllenNLP extension to use optuna with Jsonnet config file.

    This feature is experimental since AllenNLP major release will come soon.
    The interface may change without prior notice to correspond to the update.

    See the examples of `objective function <https://github.com/optuna/optuna/blob/
    master/examples/allennlp/allennlp_jsonnet.py>`_ and
    `config file <https://github.com/optuna/optuna/blob/master/
    examples/allennlp/classifier.jsonnet>`_.

    Args:
        trial:
            A :class:`~optuna.trial.Trial` corresponding to the current evaluation
            of the objective function.
        config_file:
            Config file for AllenNLP.
            Hyperparameters should be masked with ``std.extVar``.
            Please refer to `the config example <https://github.com/allenai/allentune/blob/
            master/examples/classifier.jsonnet>`_.
        serialization_dir:
            A path which model weights and logs are saved.
        metrics:
            An evaluation metric for the result of ``objective``.
        include_package:
            Additional packages to include.
            For more information, please see
            `AllenNLP documentation <https://docs.allennlp.org/master/api/commands/train/>`_.

    """

    def __init__(
        self,
        trial: optuna.Trial,
        config_file: str,
        serialization_dir: str,
        metrics: str = "best_validation_accuracy",
        *,
        include_package: Optional[Union[str, List[str]]] = None
    ):
        _imports.check()

        self._params = trial.params
        self._config_file = config_file
        self._serialization_dir = serialization_dir
        self._metrics = metrics
        if include_package is None:
            include_package = []
        if isinstance(include_package, str):
            self._include_package = [include_package]
        else:
            self._include_package = include_package

    def _build_params(self) -> Dict[str, Any]:
        """Create a dict of params for AllenNLP."""
        # _build_params is based on allentune's train_func.
        # https://github.com/allenai/allentune/blob/master/allentune/modules/allennlp_runner.py#L34-L65
        for key, value in self._params.items():
            self._params[key] = str(value)
        ext_vars = {**allennlp.common.params._environment_variables(), **self._params}
        _params = json.loads(_jsonnet.evaluate_file(self._config_file, ext_vars=ext_vars))

        # _params contains a list of string or string as value values.
        # Some params couldn't be casted correctly and
        # infer_and_cast converts them into desired values.
        return allennlp.common.params.infer_and_cast(_params)

    def run(self) -> float:
        """Train a model using AllenNLP."""
        try:
            import_func = allennlp.common.util.import_submodules
        except AttributeError:
            import_func = allennlp.common.util.import_module_and_submodules
            warnings.warn("AllenNLP>0.9 has not been supported officially yet.")

        for package_name in self._include_package:
            import_func(package_name)

        params = allennlp.common.params.Params(self._build_params())
        allennlp.commands.train.train_model(params, self._serialization_dir)

        metrics = json.load(open(os.path.join(self._serialization_dir, "metrics.json")))
        return metrics[self._metrics]
