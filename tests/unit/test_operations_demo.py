import numpy as np

from examples.operations_demo.model import OperationsDemoModel, demonstration_batch


def test_demo_model_fault_is_isolated_to_pca_and_degrades_rmse(monkeypatch):
    monkeypatch.setattr("examples.operations_demo.model.mlflow.log_param", lambda *_: None)
    model = OperationsDemoModel()
    model.tracked_training()
    batch = demonstration_batch()

    healthy = model.live_predict(batch, {"corrupt": False})["prediction"]
    corrupt = model.live_predict(batch, {"corrupt": True})["prediction"]
    target = batch["target"]
    healthy_rmse = float(np.sqrt(np.mean((healthy - target) ** 2)))
    corrupt_rmse = float(np.sqrt(np.mean((corrupt - target) ** 2)))

    assert healthy_rmse < 1e-10
    assert corrupt_rmse > 1.0
    assert list(healthy.index) == list(batch.index)


def test_demonstration_batch_is_reproducible_and_labelled():
    first = demonstration_batch(8)
    second = demonstration_batch(8)

    assert first.equals(second)
    assert list(first.columns) == ["feature_1", "feature_2", "feature_3", "target"]
