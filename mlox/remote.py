import os
import re
import yaml
import logging
import tempfile

from io import BytesIO
from typing import Dict, Tuple
from fabric import Connection, Config  # type: ignore

logger = logging.getLogger(__name__)


def open_connection(
    config: Dict,
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
    )

    logger.info("SSH connection open.")

    # optionally return tmpdir to keep it alive
    return conn, tmpdir


def close_connection(conn, tmp_dir=None):
    conn.close()
    if tmp_dir is not None:
        tmp_dir.cleanup()
        logger.info(f"Temporary directory {tmp_dir.name} deleted.")
    logger.info("SSH connection closed and tmp dir deleted.")


def exec_command(conn, cmd, sudo=False, pty=False):
    print(f"Execute CMD: {cmd}")
    res = None
    if sudo:
        try:
            res = conn.sudo(cmd, hide="stderr", pty=pty).stdout.strip()
        except Exception as e:
            print(e)
    else:
        res = conn.run(cmd, hide=True).stdout.strip()
    print(res)
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
    return ret


def docker_list_container(conn):
    res = exec_command(conn, "docker container ls", sudo=True)
    dl = str(res).split("\n")
    dlist = [re.sub("\ {2,}", "    ", dl[i]).split("   ") for i in range(len(dl))]
    return dlist


def docker_down(conn, config_yaml):
    return exec_command(
        conn, f'docker compose -f "{config_yaml}" down --remove-orphans', sudo=True
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


def fs_read_file(conn, file_path, encoding="utf-8", format="yaml"):
    io_obj = BytesIO()
    conn.get(file_path, io_obj)
    if format == "yaml":
        return yaml.safe_load(io_obj.getvalue())
    return io_obj.getvalue().decode(encoding)
