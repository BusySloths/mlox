import os
import sys
import typer
import shutil
import subprocess

from importlib import resources

from mlox.session import MloxSession


app = typer.Typer(no_args_is_help=True)

infra_app = typer.Typer(no_args_is_help=True)


def start_multipass():
    """
    Finds and executes the start-multipass.sh script included with the package.
    """
    try:
        # Modern way to access package data files
        with resources.as_file(
            resources.files("mlox.assets").joinpath("start-multipass.sh")
        ) as script_path:
            print(f"Executing multipass startup script from: {script_path}")
            # Make sure the script is executable
            os.chmod(script_path, 0o755)
            # Run the script
            subprocess.run([str(script_path)], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Error starting multipass: {e}", file=sys.stderr)
        sys.exit(1)


def start_ui(env: dict | None = None):
    """
    Finds the app.py file within the package and launches it with Streamlit.
    This replaces the need for a separate start-ui.sh script.
    Optionally accepts an env dict to pass environment variables to the subprocess.
    """
    try:
        # --- Copy theme config to ensure consistent UI ---
        try:
            source_config_path_obj = resources.files("mlox.resources").joinpath(
                "config.toml"
            )
            dest_dir = os.path.join(os.getcwd(), ".streamlit")
            dest_config_path = os.path.join(dest_dir, "config.toml")
            os.makedirs(dest_dir, exist_ok=True)
            with resources.as_file(source_config_path_obj) as source_path:
                shutil.copy(source_path, dest_config_path)
                print(f"Copied theme config to {dest_config_path}")
        except Exception as e:
            print(
                f"Warning: Could not copy theme configuration. UI will use default theme. Error: {e}",
                file=sys.stderr,
            )

        app_path = str(resources.files("mlox").joinpath("app.py"))
        print(f"Launching MLOX UI from: {app_path}")
        # Prepare environment variables
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", app_path],
            check=True,
            env=run_env,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Error starting Streamlit UI: {e}", file=sys.stderr)
        sys.exit(1)


def get_session(project: str, password: str) -> MloxSession:
    try:
        session = MloxSession(project, password)
        if not session.secrets.is_working():
            typer.echo(
                "[ERROR] Could not initialize session (secrets not working)", err=True
            )
            raise typer.Exit(code=2)
        return session
    except Exception as e:
        typer.echo(f"[ERROR] Failed to load session: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def multipass():
    """Start multipass VM"""
    start_multipass()


@app.command()
def ui(
    project: str = typer.Option(
        "", prompt_required=False, help="Project name (username for session)"
    ),
    password: str = typer.Option(
        "", prompt_required=False, hide_input=True, help="Password for the session"
    ),
):
    """Start the MLOX UI with Streamlit (requires project and password)"""
    env: dict = {}
    if len(password) > 4 and len(project) >= 1:
        env["MLOX_PROJECT"] = project
        env["MLOX_PASSWORD"] = password
    # Optionally, you could pass session to the UI if needed
    start_ui(env)


@infra_app.command("list")
def list_bundles(
    project: str = typer.Option(..., help="Project name (username for session)"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
):
    """List bundle names of the loaded infrastructure for the given project and password."""
    session = get_session(project, password)
    if not session.infra.bundles:
        typer.echo("No bundles found.")
        raise typer.Exit(code=3)
    typer.echo("Loaded bundles:")
    for b in session.infra.bundles:
        typer.echo(f"{b.server.ip}: {b.name} with {len(b.services)} services")


# Register the infra sub-app
app.add_typer(infra_app, name="infra", help="Infrastructure related commands")


if __name__ == "__main__":
    app()
