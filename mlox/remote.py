import os
import re
import yaml
import logging
import tempfile
import secrets

from io import BytesIO
from typing import Dict, Tuple
from fabric import Connection, Config  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def open_connection(
    config: Dict, timeout: int = 10
) -> Tuple[Connection, None | tempfile.TemporaryDirectory]:
    connect_kwargs = {"password": config["pw"]}

    tmpdir = None  # so we can return it if needed

    if "private_key" in config and "passphrase" in config:
        tmpdir = tempfile.TemporaryDirectory()
        tmpdirname = tmpdir.name
        logger.info(f"Created temporary directory at {tmpdirname}")

        private_key_path = os.path.join(tmpdirname, "id_rsa")
        with open(private_key_path, "w") as priv_file:
            priv_file.write(config["private_key"])
        os.chmod(private_key_path, 0o600)  # SSH requires strict perms

        connect_kwargs = {
            "key_filename": private_key_path,
            "passphrase": config["passphrase"],
        }

    conn = Connection(
        host=config["host"],
        user=config["user"],
        port=config["port"],
        connect_kwargs=connect_kwargs,
        config=Config(overrides={"sudo": {"password": config["pw"]}}),
        connect_timeout=timeout,
    )

    # optionally return tmpdir to keep it alive
    return conn, tmpdir


def close_connection(conn, tmp_dir=None):
    conn.close()
    if tmp_dir is not None:
        tmp_dir.cleanup()
        logger.info(f"Temporary directory {tmp_dir.name} deleted.")
    logger.info("SSH connection closed and tmp dir deleted.")


def exec_command(conn, cmd, sudo=False, pty=False):
    logger.debug(f"Executing command: {cmd}")
    res = None
    hide = "stderr" if sudo else True
    if sudo:
        try:
            res = conn.sudo(cmd, hide=hide, pty=pty).stdout.strip()
        except Exception as e:
            logger.error(f"Command failed: {e}")
    else:
        res = conn.run(cmd, hide=hide).stdout.strip()
    return res


def sys_disk_free(conn) -> int:
    uname = exec_command(conn, "uname -s")
    if "Linux" in uname:
        perc = exec_command(conn, "df -h / | tail -n1 | awk '{print $5}'")
        return int(perc[:-1])
    logging.error("No idea how to get disk space on {}!".format(uname))
    return 0


def sys_root_apt_install(conn, param, upgrade: bool = False):
    cmd = f"apt install {param}"
    if upgrade:
        cmd = "apt upgrade"
    exec_command(conn, "dpkg --configure -a")
    return exec_command(conn, cmd)


def sys_user_id(conn):
    return exec_command(conn, "id -u")


def sys_list_user(conn):
    return exec_command(conn, "ls -l /home | awk '{print $4}'")


def sys_add_user(
    conn, user_name, passwd, with_home_dir: bool = False, sudoer: bool = False
):
    p_home_dir = "-m " if with_home_dir else ""
    command = f"useradd -p `openssl passwd {passwd}` {p_home_dir}-d /home/{user_name} {user_name}"
    ret = exec_command(conn, command, sudo=True)
    if sudoer:
        exec_command(conn, f"usermod -aG sudo {user_name}", sudo=True)

        if os.environ.get("MLOX_DEBUG", False):
            logger.warning(
                "[DEBUG ENABLED] sudoer group member do not need to pw anymore."
            )
            # This is the key part:
            sudoer_file_content = f"{user_name} ALL=(ALL) NOPASSWD: ALL"
            sudoer_file_path = f"/etc/sudoers.d/90-mlox-{user_name}"
            exec_command(
                conn,
                f"echo '{sudoer_file_content}' | tee {sudoer_file_path}",
                sudo=True,
            )
            exec_command(conn, f"chmod 440 {sudoer_file_path}", sudo=True)
    return ret


def docker_list_container(conn):
    res = exec_command(conn, "docker container ls", sudo=True)
    dl = str(res).split("\n")
    dlist = [re.sub(r"\ {2,}", "    ", dl[i]).split("   ") for i in range(len(dl))]
    return dlist


def docker_down(conn, config_yaml, remove_volumes=False):
    volumes = "--volumes " if remove_volumes else ""
    return exec_command(
        conn,
        f'docker compose -f "{config_yaml}" down {volumes}--remove-orphans',
        sudo=True,
    )


def docker_up(conn, config_yaml, env_file=None):
    command = f'docker compose -f "{config_yaml}" up -d --build'
    if env_file is not None:
        command = (
            f'docker compose --env-file {env_file} -f "{config_yaml}" up -d --build'
        )
    return exec_command(conn, command, sudo=True)


def git_clone(conn, repo_url, install_path):
    exec_command(conn, f"mkdir -p {install_path}")
    exec_command(conn, f"cd {install_path}; git clone {repo_url}")


def fs_copy(conn, src_file, dst_path):
    conn.put(src_file, dst_path)


def fs_create_dir(conn, path):
    exec_command(conn, f"mkdir -p {path}")


def fs_delete_dir(conn, path):
    exec_command(conn, f"rm -rf {path}", sudo=True)


def fs_copy_dir(conn, src_path: str, dst_path: str, sudo: bool = False):
    """
    Copies a directory recursively on the remote server.

    Args:
        conn: Fabric connection object.
        src_path: The source directory path on the remote server.
        dst_path: The destination path on the remote server.
        sudo: If True, execute the command with sudo.
    """
    exec_command(conn, f"cp -r {src_path} {dst_path}", sudo=sudo)


def fs_exists_dir(conn, path: str) -> bool:
    """
    Checks if a directory exists on the remote server.
    Returns True if the directory exists, False otherwise.
    """
    try:
        # Use 'test -d' to check for directory existence
        res = exec_command(conn, f"test -d {path} && echo exists || echo missing")
        return str(res).strip() == "exists"
    except Exception as e:
        logger.warning(f"Error checking if directory exists: {e}")
        return False


def fs_create_symlink(conn, target_path, link_path, sudo=False):
    """
    Creates a symbolic link on the remote server.

    Args:
        conn: Fabric connection object.
        target_path: The path the link should point to.
        link_path: The path of the symbolic link to create.
        sudo: If True, execute the command with sudo.
    """
    exec_command(conn, f"ln -s {target_path} {link_path}", sudo=sudo)


def fs_remove_symlink(conn, link_path, sudo=False):
    """
    Removes a symbolic link on the remote server.
    """
    exec_command(conn, f"rm {link_path}", sudo=sudo)


def fs_touch(conn, fname):
    exec_command(conn, f"touch {fname}")


def fs_append_line(conn, fname, line):
    exec_command(conn, f"touch {fname}")
    exec_command(conn, f"echo '{line}' >> {fname}")


def fs_create_empty_file(conn, fname):
    exec_command(conn, f"echo -n >| {fname}")


def fs_find_and_replace(conn, fname, old, new, separator="!", sudo=False):
    exec_command(
        conn,
        f"sed -i 's{separator}{old}{separator}{new}{separator}g' {fname}",
        sudo=sudo,
    )


def fs_write_file(
    conn,
    file_path: str,
    content: str | bytes,
    sudo: bool = False,
    encoding: str = "utf-8",
):
    """
    Writes content to a file on the remote server.

    Args:
        conn: Fabric connection object.
        file_path: Absolute path to the remote file.
        content: String or bytes content to write to the file.
        sudo: If True, perform write operations with sudo.
        encoding: Encoding for the content if it's a string.
    """
    if isinstance(content, str):
        content_bytes = content.encode(encoding)
    elif isinstance(content, bytes):
        content_bytes = content
    else:
        raise TypeError("Content must be str or bytes")

    file_like_object = BytesIO(content_bytes)

    if not sudo:
        conn.put(file_like_object, remote=file_path)
        logger.info(f"Wrote content to {file_path} as user {conn.user}")
    else:
        # Put to a temporary location first, then sudo mv
        random_suffix = secrets.token_hex(8)
        remote_tmp_path = os.path.join("/tmp", f"mlox_tmp_{random_suffix}")

        try:
            conn.put(file_like_object, remote=remote_tmp_path)
            logger.info(f"Uploaded content to temporary remote path: {remote_tmp_path}")

            # Move the file to its final destination using sudo
            exec_command(conn, f"mv {remote_tmp_path} {file_path}", sudo=True)
            logger.info(
                f"Moved temporary file from {remote_tmp_path} to {file_path} using sudo."
            )
        except Exception as e:
            logger.error(f"Error writing file {file_path} with sudo: {e}")
            if conn.is_connected:  # Check if connection is still alive for cleanup
                exec_command(
                    conn, f"rm -f {remote_tmp_path}", sudo=True, pty=False
                )  # Attempt to clean up
            raise


def fs_read_file(conn, file_path, encoding="utf-8", format="yaml"):
    io_obj = BytesIO()
    conn.get(file_path, io_obj)
    if format == "yaml":
        return yaml.safe_load(io_obj.getvalue())
    return io_obj.getvalue().decode(encoding)


def fs_list_files(conn, path: str, sudo: bool = False) -> list[str]:
    """
    Lists files and directories in a given path on the remote server.

    Args:
        conn: Fabric connection object.
        path: Absolute path to the directory on the remote server.
        sudo: If True, execute the list command with sudo.

    Returns:
        A list of filenames and directory names.
    """
    command = f"ls -A1 {path}"  # -A for almost all, -1 for one per line
    output = exec_command(conn, command, sudo=sudo, pty=False)
    return output.splitlines() if output else []


def fs_list_file_tree(conn, path: str, sudo: bool = False) -> list[dict]:
    """
    Recursively lists the file tree for a given path on the remote server.
    Returns a list of dicts for each entry with keys:
      'name', 'path', 'is_file', 'is_dir', 'size', 'modification_datetime'
    """
    command = f"find {path} -printf '%p|%y|%s|%TY-%Tm-%Td %TH:%TM:%TS\n'"
    output = exec_command(conn, command, sudo=sudo, pty=False)
    entries = []
    if output:
        for line in output.splitlines():
            try:
                p, y, s, mdt = line.split("|", 3)
                entry = {
                    "name": os.path.basename(p),
                    "path": p,
                    "is_file": y == "f",
                    "is_dir": y == "d",
                    "size": int(s),
                    "modification_datetime": mdt.split(".")[0],
                }
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Error parsing file tree line: {line} ({e})")
    return entries
