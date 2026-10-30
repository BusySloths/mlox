---
title: "From bare server to running stack"
eyebrow: "How it works"
description: "Three calm steps. No YAML archaeology, no click-ops."
steps:
  - title: "Add a server"
    description: "Connect a server over SSH, for example an Ubuntu VPS, then pick a backend: native, Docker or Kubernetes. MLOX sets it up, locks it down and remembers it in your encrypted project."
    image: "mlox_tui_overview"
    alt: "The MLOX overview listing bundles, servers and their running state."
  - title: "Deploy from the catalog"
    description: "Choose MLflow, Airflow, LiteLLM, Postgres or any other template. Ports, secrets and dependencies between services are wired for you, and every step is inspectable."
    image: "mlox_tui_catalog"
    alt: "The MLOX service catalog with a template selected and its requirements and ports."
  - title: "Operate with confidence"
    description: "Health checks, credentials, logs, telemetry and lifecycle actions for every service, in the TUI when you are exploring, from the CLI when you are automating."
    image: "mlox_tui_service"
    alt: "The MLOX service detail view for MLflow with capabilities, URLs and service actions."
---
