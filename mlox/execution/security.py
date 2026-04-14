"""TLS and SSH-key helpers for Ubuntu executors."""

from __future__ import annotations

from importlib import resources

from fabric import Connection  # type: ignore

from mlox.execution.base import (
    FilesystemTaskRunnerABC,
    TaskGroup,
    _quote_command,
)


class SecurityMixin(FilesystemTaskRunnerABC):
    def _get_stacks_path(self):
        """Return the packaged TLS configuration resource for services."""

        return resources.files("mlox.services.shared").joinpath("openssl-san.cnf")

    def tls_setup_no_config(self, connection: Connection, ip: str, path: str) -> None:
        """Create TLS assets on the remote host without using a custom config."""

        self.fs_create_dir(connection, path)

        subject = f"/CN={ip}"

        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"cd {path}; openssl genrsa -out key.pem 2048",
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=(
                f"cd {path}; openssl req -new -key key.pem -out server.csr -subj '{subject}'"
            ),
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=(
                f"cd {path}; "
                "openssl x509 -req -in server.csr -signkey key.pem -out cert.pem "
                "-days 365"
            ),
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"chmod u=rw,g=rw,o=rw {path}/key.pem",
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"chmod u=rw,g=rw,o=rw {path}/cert.pem",
        )

    def tls_setup(self, connection: Connection, ip: str, path: str) -> None:
        """Create TLS assets on the remote host using an OpenSSL config."""

        self.fs_create_dir(connection, path)

        with resources.as_file(self._get_stacks_path()) as tls_config:
            self.fs_copy(connection, str(tls_config), f"{path}/openssl-san.cnf")
        self.fs_find_and_replace(
            connection, f"{path}/openssl-san.cnf", "<MY_IP>", f"{ip}"
        )

        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"cd {path}; openssl genrsa -out key.pem 2048",
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=(
                f"cd {path}; openssl req -new -key key.pem -out server.csr -config openssl-san.cnf"
            ),
        )
        cmd = (
            f"cd {path}; "
            "openssl x509 -req -in server.csr -signkey key.pem "
            "-out cert.pem -days 365 -extensions req_ext -extfile openssl-san.cnf"
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=cmd,
        )
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=f"chmod u=rw,g=rw,o=rw {path}/key.pem",
        )

    def security_generate_ssh_key(
        self,
        connection: Connection,
        *,
        key_path: str,
        key_type: str = "rsa",
        bits: int = 4096,
        comment: str | None = None,
        sudo: bool = False,
        overwrite: bool = True,
    ) -> None:
        if overwrite:
            cleanup_cmd = _quote_command(
                [
                    "rm",
                    "-f",
                    key_path,
                    f"{key_path}.pub",
                ]
            )
            self._run_task(
                connection,
                group=TaskGroup.SECURITY_ASSETS,
                command=cleanup_cmd,
                sudo=sudo,
            )
        parts: list[str] = [
            "ssh-keygen",
            "-q",
            "-t",
            key_type,
            "-b",
            str(bits),
            "-N",
            "",
            "-f",
            key_path,
        ]
        if comment:
            parts.extend(["-C", comment])
        command = _quote_command(parts)
        self._run_task(
            connection,
            group=TaskGroup.SECURITY_ASSETS,
            command=command,
            sudo=sudo,
        )
