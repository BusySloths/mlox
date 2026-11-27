---
slug: first-models
title: "Track, register and serve your first model"
type: tutorial
status: draft
# Planned shot list; capture names are fixed when the chapters are recorded.
shots: []
# Outputs are listed in content/registry.yaml.
---

# Track, register and serve your first model

The first service-specific recipe, planned in the same format as
`first-steps`, and continuing where it ends: one project, one Docker server
that is already set up. Recorded as terminal captures; see
`content/first-steps/script.md` for the recording setup.

Status: outline only. Before recording, settle the open points, run the steps
once by hand, and replace each chapter's notes with exact actions, shots and
captures.

## Chapter: before

The `first-steps` project with its server running, or a new one. Python with
`busysloths-mlox` in the notebook or script environment.

## Chapter: mlflow

Add MLflow from the catalog to the existing server and set it up. Show the
service in the tree, open its web UI.

## Chapter: track

Train a small model (scikit-learn) and log the run to MLflow with the MLOX
MLflow helpers (`mlox/services/mlflow/`), so the tracking URL and credentials
come from the project, not copied by hand.

## Chapter: register

Register the model and mark a version as champion. Show the model in the TUI.

## Chapter: serve

Serve the champion (MLflow MLServer on the same server), send a prediction
request and show the answer.

## Chapter: time

The measured steps from the recorded run, as in `first-steps`.

## Open points

- Model serving service: MLServer on Docker or MLflow Gateway.
- Client path: the MLOX MLflow helpers or the CLI for the credentials.
- Whether the models tab or the service panel carries the registry shot.
