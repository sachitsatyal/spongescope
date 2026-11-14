"""Register an exported model in MLflow and move the `champion` alias to it.

  uv run python scripts\\register_model.py --model models\\spongescope-v1

The alias is what serving reads, so promoting a new version is this one command.
"""

import argparse
import json
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

ROOT = Path(__file__).resolve().parents[1]
NAME = "spongescope"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "models" / "spongescope-v1"))
    ap.add_argument("--tracking-uri", default="sqlite:///mlflow.db")
    ap.add_argument("--alias", default="champion")
    args = ap.parse_args()

    path = Path(args.model)
    config = json.loads((path / "config.json").read_text())
    mlflow.set_tracking_uri(args.tracking_uri)
    client = MlflowClient()
    if not any(m.name == NAME for m in client.search_registered_models(f"name='{NAME}'")):
        client.create_registered_model(NAME)

    with mlflow.start_run(run_name=f"export/{config['run_name']}") as run:
        mlflow.log_artifacts(str(path), artifact_path="model")
        flat = {f"{g}/{m}": v for g, d in config["metrics"].items() for m, v in d.items()}
        mlflow.log_metrics({**flat, "temperature": config["temperature"]})
        mlflow.log_params(
            {
                "run_name": config["run_name"],
                "n_parameters": config["n_parameters"],
                **{f"model.{k}": v for k, v in config["model"].items()},
            }
        )
        uri = f"runs:/{run.info.run_id}/model"

    mv = client.create_model_version(NAME, uri, run_id=run.info.run_id)
    client.set_registered_model_alias(NAME, args.alias, mv.version)
    print(f"{NAME} version {mv.version} registered from {config['run_name']}")
    print(f"alias '{args.alias}' -> version {mv.version}")
    print(f"load with: mlflow.artifacts.download_artifacts('models:/{NAME}@{args.alias}')")


if __name__ == "__main__":
    main()
