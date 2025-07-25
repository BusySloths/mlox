import os
import subprocess
import sys
from importlib import resources


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


def start_ui():
    """
    Finds the app.py file within the package and launches it with Streamlit.
    This replaces the need for a separate start-ui.sh script.
    """
    try:
        # This is a robust way to get the path to a module file
        app_path = str(resources.files("mlox").joinpath("app.py"))
        print(f"Launching MLOX UI from: {app_path}")
        # Use sys.executable to ensure we use the streamlit from the correct python env
        subprocess.run([sys.executable, "-m", "streamlit", "run", app_path], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Error starting Streamlit UI: {e}", file=sys.stderr)
        sys.exit(1)
