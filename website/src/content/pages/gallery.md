---
title: "Explore the TUI"
eyebrow: "Real project · 5 bundles · 23 services"
description: "Every screen below is a real MLOX project running on real servers, captured by our automated content pipeline. Addresses and private names are blurred, everything else is live. Use the tabs, or your ← → keys, just like in the terminal."
shots:
  - id: overview
    label: "Overview"
    title: "Your whole infrastructure on one screen"
    description: "Bundles, servers and every deployed service in a single tree, with live state per server and capacity totals. The first thing you see after unlocking a project."
    image: "mlox_tui_overview"
    alt: "MLOX TUI overview: a tree of five bundles and their services, metric tiles for bundles, services, CPU cores and RAM, and a table of running servers."
  - id: monitor
    label: "Monitor"
    title: "Telemetry from every server"
    description: "OpenTelemetry collectors on each server stream host metrics into the project: CPU, memory, disk and network, refreshed every 30 seconds, without a single extra dashboard."
    image: "mlox_tui_monitor"
    alt: "MLOX Monitor tab: a per-server table of CPU, RAM, disk and network usage, plus CPU, memory, disk and network trend panels."
  - id: models
    label: "Models"
    title: "Registries, gateways and every model version"
    description: "See what your MLflow registry holds and what the model gateway can serve right now, then copy a ready-made curl call to test it."
    image: "mlox_tui_models"
    alt: "MLOX Models tab: registries, running gateway endpoints and a long list of model versions marked READY."
  - id: workflow
    label: "Workflow"
    title: "Pipelines you can actually see"
    description: "Airflow orchestrators, DAGs, schedules and last runs, failures included, next to the services those pipelines depend on."
    image: "mlox_tui_workflow"
    alt: "MLOX Workflow tab: an Airflow orchestrator and its DAGs with schedule, last run and last state."
  - id: catalog
    label: "Catalog"
    title: "Twenty-plus services, one keystroke away"
    description: "MLflow, Airflow, LiteLLM, Ollama, Milvus, Kafka, Postgres, Redis, MinIO, OpenBao and more, each with requirements, ports and capabilities shown before you deploy."
    image: "mlox_tui_catalog"
    alt: "MLOX service catalog: a table of service templates with versions and maintainers, and the details of the selected template."
  - id: service
    label: "Service"
    title: "Every service, fully explained"
    description: "Capabilities, ports, URLs and the template it came from, plus credentials on demand, health checks and lifecycle actions, all for each service."
    image: "mlox_tui_service"
    alt: "MLOX service detail for MLflow: bundle, state, capabilities, target path, template, ports and URLs, plus service action buttons."
  - id: repositories
    label: "Repositories"
    title: "Your code, next to your infrastructure"
    description: "Private GitHub repositories cloned onto your servers, with deploy keys managed for you and a file browser built in."
    image: "mlox_tui_repositories"
    alt: "MLOX Repositories tab: cloned private repositories with their bundles and a file tree of a Python project."
  - id: databases
    label: "Databases"
    title: "Data stores at a glance"
    description: "Redis, Postgres and InfluxDB with engine, port and endpoints in one table, wired into the services that use them."
    image: "mlox_tui_databases"
    alt: "MLOX Databases tab: Redis, InfluxDB and Postgres with engine, state, port and endpoints."
  - id: firewall
    label: "Firewall"
    title: "Ports that follow your services"
    description: "MLOX recommends the open ports for each server from the services running on it, and shows the firewall state in the same place."
    image: "mlox_tui_firewall"
    alt: "MLOX Firewall tab: firewall status per server and a table of recommended ports with the services that need them."
  - id: knowledge
    label: "Knowledge"
    title: "Runbooks that live with the project"
    description: "Notes, postmortems and a kanban board, stored inside the same encrypted project file as your infrastructure."
    image: "mlox_tui_knowledge"
    alt: "MLOX Knowledge tab: a list of notes, boards and postmortems, and a kanban board with open, doing, blocked and done columns."
  - id: cli
    label: "CLI"
    title: "Same project, scriptable"
    description: "Everything the TUI does is a command away: human-friendly tables for you, --output json for scripts, CI and agents."
    image: "mlox_tui_cli"
    alt: "The MLOX command line: mlox --help listing commands, and mlox server list showing a table of servers."
---
