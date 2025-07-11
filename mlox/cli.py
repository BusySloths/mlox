import os
import sys
import subprocess
from importlib import resources


def start_multipass():
    """
    Finds and executes the start-multipass.sh script included with the package.
    This function is registered as a console script in pyproject.toml.
    """
    try:
        # Use importlib.resources to access package data reliably.
        # This works correctly whether the package is installed from a wheel,
        # an sdist, or in editable mode. Since requires-python is >=3.11,
        # we can use the modern .files() API directly.
        script_ref = resources.files("mlox.assets").joinpath("start-multipass.sh")
        ctx_manager = resources.as_file(script_ref)

        with ctx_manager as script_path:
            os.chmod(script_path, 0o755)  # Ensure the script is executable
            # Execute the script, allowing it to interact with the user's terminal
            result = subprocess.run([str(script_path)], check=False)
            sys.exit(result.returncode)
    except FileNotFoundError:
        print(
            "Error: The 'start-multipass.sh' script could not be found within the package.",
            file=sys.stderr,
        )
        sys.exit(1)
