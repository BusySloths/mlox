import os
import subprocess
import sys
from importlib import resources
import shutil

import typer


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
        # --- Copy theme config to ensure consistent UI ---
        # This ensures that the Streamlit app uses the theme defined in the package,
        # regardless of the user's local or global Streamlit config.
        try:
            # Get path to the source config.toml within the package
            source_config_path_obj = resources.files("mlox.resources").joinpath(
                "config.toml"
            )

            # Define the destination path in the user's current directory
            dest_dir = os.path.join(os.getcwd(), ".streamlit")
            dest_config_path = os.path.join(dest_dir, "config.toml")

            # Create the .streamlit directory if it doesn't exist
            os.makedirs(dest_dir, exist_ok=True)

            # Copy the file, overwriting if it exists.
            with resources.as_file(source_config_path_obj) as source_path:
                shutil.copy(source_path, dest_config_path)
                print(f"Copied theme config to {dest_config_path}")
        except Exception as e:
            # If copying fails, just print a warning and continue. The UI will still
            # launch, just maybe without the custom theme.
            print(
                f"Warning: Could not copy theme configuration. UI will use default theme. Error: {e}",
                file=sys.stderr,
            )

        # This is a robust way to get the path to a module file
        app_path = str(resources.files("mlox").joinpath("app.py"))
        print(f"Launching MLOX UI from: {app_path}")
        # Use sys.executable to ensure we use the streamlit from the correct python env
        subprocess.run([sys.executable, "-m", "streamlit", "run", app_path], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Error starting Streamlit UI: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # Typer CLI app
    app = typer.Typer()

    @app.command()
    def multipass():
        """Start multipass VM"""
        start_multipass()

    @app.command()
    def ui():
        """Start the MLOX UI with Streamlit"""
        start_ui()

    app()


if __name__ == "__main__":
    main()
