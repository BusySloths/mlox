# Command-Line Interface

This package exposes MLOX through Typer commands.

## Structure

- `app.py`: root command and subcommand registration.
- `context.py`: project path, password, and workspace loading.
- `commands/`: project, server, service, and model commands.
- `rendering/`: terminal output helpers.

## Workflow

Each command loads one `ProjectWorkspace`, calls its public operation, renders
the returned `OperationResult`, and exits with an appropriate status.

## System Role

The CLI is an adapter. Keep business logic in `mlox.application` and
`mlox.project`; commands should focus on arguments, validation, and output.

