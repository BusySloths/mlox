# Servers

This package contains compute targets and backend implementations.

## Structure

- `local/`: operations on the current machine.
- `ubuntu/`: native, Docker, K3s, and Multipass-backed servers.
- `connector/`: virtual targets for externally hosted services.
- `mlox-server*.yaml`: server templates and capabilities.

## Workflow

A server config instantiates an `AbstractServer`. The server becomes the compute
side of an infrastructure bundle and supplies connections and executors to its
services.

## System Role

Servers model where and how work runs. Service deployment should use server
capabilities and executors instead of embedding transport-specific commands.

