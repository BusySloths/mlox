import logging
import sys  # For sys.stdout.flush()

import streamlit as st

from fabric import Connection, Result  # type: ignore
from invoke.exceptions import UnexpectedExit  # For catching command execution errors

from mlox.executors import TaskGroup, UbuntuTaskExecutor

logger = logging.getLogger(__name__)


def emulate_basic_terminal(conn: Connection):
    """
    Emulates a basic interactive terminal over a Fabric connection.

    Args:
        conn: An active Fabric Connection object.
    """
    if not conn.is_connected:
        logger.error("Connection is not active. Cannot start terminal emulation.")
        print("Error: Connection is not active.", file=sys.stderr)
        return

    st.write(f"Connected to {conn.host}. Type 'exit' to quit.")

    executor = UbuntuTaskExecutor()

    try:
        initial_dir_result = conn.run("pwd", hide=True, warn=True, pty=False)
        current_dir = (
            initial_dir_result.stdout.strip() if initial_dir_result.ok else "~"
        )
    except Exception as e:
        logger.warning(f"Could not determine initial working directory: {e}")
        current_dir = "~"

    try:
        prompt = f"{conn.user}@{conn.host}:{current_dir}$ "
        command_str = st.text_input("Input", value="", placeholder=prompt)

        if command_str.strip().startswith("cd "):
            new_dir_path = command_str.strip()[3:].strip()
            if not new_dir_path:  # 'cd' with no arguments, go to home
                new_dir_path = "~"

            # To correctly resolve paths like 'cd ..' or 'cd /some/path'
            # we execute 'cd <path> && pwd' to get the new absolute path.
            # pty=False is generally better for non-interactive commands like this.
            # Ensure the path is quoted if it might contain spaces or special characters.
            # shlex.quote could be used here if available and robust quoting is needed.
            # For simplicity, basic quoting:
            if " " in new_dir_path and not (
                new_dir_path.startswith("'") or new_dir_path.startswith('"')
            ):
                new_dir_path = f"'{new_dir_path}'"

            cd_command_full = f"cd {new_dir_path} && pwd"
            res: Result = conn.run(cd_command_full, hide=True, warn=True, pty=False)

            if res.ok:
                current_dir = res.stdout.strip()
            else:
                if res.stderr:
                    print(res.stderr.strip(), file=sys.stderr)

        # For other commands, execute them
        # Using pty=True for more interactive-like behavior for most commands
        result = executor.execute(
            conn,
            command_str,
            group=TaskGroup.AD_HOC,
            pty=False,
        )

        st.write(f"Command {command_str}: ")
        st.write(result)

        sys.stdout.flush()

    except UnexpectedExit as e:
        print(f"Command error: {e}", file=sys.stderr)
    except EOFError:  # Ctrl+D
        print("\nExiting terminal (EOF).")
    except KeyboardInterrupt:  # Ctrl+C
        print("\nExiting terminal (Interrupt).")
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        logger.exception("Unexpected error in terminal emulation loop")
        # Depending on the severity, you might want to break or continue
        # break


# Example of how to use it (you'd need to establish a 'conn' first)
# if __name__ == "__main__":
#     # This is a placeholder for how you would get a connection.
#     # In a real scenario, you'd use your existing mlox.server.ServerConnection
#     # or directly instantiate fabric.Connection with credentials.
#     # from mlox.server import ServerConnection
#     # my_credentials = {"host": "your_ip", "user": "your_user", "pw": "your_password", "port": 22}
#     # server_conn_manager = ServerConnection(credentials=my_credentials)
#     # try:
#     #     with server_conn_manager as conn_obj:
#     #         emulate_basic_terminal(conn_obj)
#     # except Exception as e:
#     #     print(f"Failed to connect or run terminal: {e}")
