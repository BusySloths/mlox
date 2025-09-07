import os
import sys
import typer
import shutil
import subprocess
import logging

from importlib import resources

from mlox.session import MloxSession
from mlox.infra import Infrastructure
from mlox.config import load_config, get_stacks_path


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)

infra_app = typer.Typer(no_args_is_help=True)


def setup_demo_project(ip1: str, ip2: str, ip3: str):
    logger.info("[MLOX DEMO] Setting up demo project with provided IPs...")
    logger.info(f"Using IPs: {ip1}, {ip2}, {ip3}")
    infra = Infrastructure()
    config_native = load_config(
        get_stacks_path(), "/ubuntu", "mlox-server.ubuntu.native.yaml"
    )
    config_docker = load_config(
        get_stacks_path(), "/ubuntu", "mlox-server.ubuntu.docker.yaml"
    )
    config_k8s = load_config(
        get_stacks_path(), "/ubuntu", "mlox-server.ubuntu.k3s.yaml"
    )
    if not config_native or not config_docker or not config_k8s:
        logger.error("[MLOX DEMO] One or more configurations not found. Exiting setup.")
        return
    params = dict()
    params["${MLOX_IP}"] = ip1
    params["${MLOX_PORT}"] = "22"
    params["${MLOX_ROOT}"] = "root"
    params["${MLOX_ROOT_PW}"] = "pass"
    ms = MloxSession.new_infrastructure(
        infra=infra,  # This should be replaced with an actual Infrastructure instance
        config=config_native,  # This should be replaced with an actual ServerConfig instance
        params=params,  # This should be replaced with actual parameters for the server
        username="demo",
        password="demo",
    )
    if ms is None:
        logger.error("[MLOX DEMO] Failed to create MloxSession. Exiting setup.")
        return
    params["${MLOX_IP}"] = ip2
    ms.infra.add_server(config=config_docker, params=params)
    params["${MLOX_IP}"] = ip3
    params["${K3S_CONTROLLER_URL}"] = ""
    params["${K3S_CONTROLLER_TOKEN}"] = ""
    params["${K3S_CONTROLLER_UUID}"] = ""
    ms.infra.add_server(config=config_k8s, params=params)
    ms.save_infrastructure()


@app.command()
def demo():
    """Spin up a demo MLOX testbed (3 VMs), show IPs, credentials, and launch the UI."""
    import time

    # 1. Start the multipass testbed
    try:
        with resources.as_file(
            resources.files("mlox.assets").joinpath("start-multipass-testbed.sh")
        ) as script_path:
            logger.info(f"[MLOX DEMO] Executing multipass testbed script: {script_path}")
            os.chmod(script_path, 0o755)
            subprocess.run([str(script_path)], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        logger.error(f"[MLOX DEMO] Error starting multipass testbed: {e}")
        sys.exit(1)

    # 2. Wait a moment for VMs to boot
    logger.info("[MLOX DEMO] Waiting for VMs to boot...")
    time.sleep(5)

    # 3. Print multipass list (show IPs) and extract demo instance IPs
    ip_map = {}
    try:
        logger.info("[MLOX DEMO] Listing multipass VMs:")
        result = subprocess.run(
            ["multipass", "list"], check=True, capture_output=True, text=True
        )
        logger.info(result.stdout)
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] in {
                "mlox-demo-1",
                "mlox-demo-2",
                "mlox-demo-3",
            }:
                # The IPv4 is always the 3rd column
                ip_map[parts[0]] = parts[2]
    except Exception as e:
        logger.error(f"[MLOX DEMO] Could not list multipass VMs: {e}")

    # 4. Print default user/pw (hardcoded or documented)
    logger.info("[MLOX DEMO] Default credentials for testbed VMs:")
    logger.info("  username: root")
    logger.info("  password: pass")

    # 5. Start the UI
    logger.info("[MLOX DEMO] Setup project DEMO...")

    # Use the extracted IPs for setup_demo_project
    ip1 = ip_map.get("mlox-demo-1", "")
    ip2 = ip_map.get("mlox-demo-2", "")
    ip3 = ip_map.get("mlox-demo-3", "")
    setup_demo_project(ip1, ip2, ip3)
    logger.info("[MLOX DEMO] Launching MLOX UI...")
    start_ui({"MLOX_PROJECT": "demo", "MLOX_PASSWORD": "demo"})
    logger.info("End of demo setup.")


def start_multipass():
    """
    Finds and executes the start-multipass.sh script included with the package.
    """
    try:
        # Modern way to access package data files
        with resources.as_file(
            resources.files("mlox.assets").joinpath("start-multipass.sh")
        ) as script_path:
            logger.info(f"Executing multipass startup script from: {script_path}")
            # Make sure the script is executable
            os.chmod(script_path, 0o755)
            # Run the script
            subprocess.run([str(script_path)], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        logger.error(f"Error starting multipass: {e}")
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
                logger.info(f"Copied theme config to {dest_config_path}")
        except Exception as e:
            logger.warning(
                f"Warning: Could not copy theme configuration. UI will use default theme. Error: {e}"
            )

        app_path = str(resources.files("mlox").joinpath("app.py"))
        logger.info(f"Launching MLOX UI from: {app_path}")
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
        logger.error(f"Error starting Streamlit UI: {e}")
        sys.exit(1)


def start_tui(env: dict | None = None):
    """Launch the Textual-based terminal UI."""
    try:
        try:
            import textual  # noqa: F401
        except Exception:
            logger.error(
                "Textual is not installed. Please install 'textual' to use the terminal UI."
            )
            sys.exit(1)

        app_path = str(resources.files("mlox").joinpath("tui.py"))
        logger.info(f"Launching MLOX TUI from: {app_path}")
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        subprocess.run([sys.executable, app_path], check=True, env=run_env)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        logger.error(f"Error starting Textual UI: {e}")
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


@app.command()
def tui(
    project: str = typer.Option(
        "", prompt_required=False, help="Project name (username for session)"
    ),
    password: str = typer.Option(
        "", prompt_required=False, hide_input=True, help="Password for the session"
    ),
):
    """Start the MLOX terminal UI (requires project and password)"""
    env: dict = {}
    if len(password) > 4 and len(project) >= 1:
        env["MLOX_PROJECT"] = project
        env["MLOX_PASSWORD"] = password
    start_tui(env)


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
