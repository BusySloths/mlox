import logging

from dataclasses import dataclass, field
from typing import Any, Dict

from mlox.service import AbstractService
from mlox.executors import TaskGroup

logger = logging.getLogger(__name__)


@dataclass
class OpenClawNativeService(AbstractService):
    port: int | Any
    install_channel: str = "latest"
    service_url: str = field(init=False, default="")
    pid_file: str = field(init=False, default="")
    log_file: str = field(init=False, default="")

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.pid_file = f"{self.target_path}/openclaw.pid"
        self.log_file = f"{self.target_path}/openclaw.log"

        self._ensure_node(conn)
        self._install_openclaw(conn)

        self.service_ports["OpenClaw Gateway"] = int(self.port)
        self.service_urls["OpenClaw Gateway"] = f"http://{conn.host}:{self.port}"
        self.service_url = f"http://{conn.host}:{self.port}"

    def teardown(self, conn) -> None:
        # self.spin_down(conn)
        self.exec.fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        cmd = (
            "bash -lc "
            '"nohup openclaw gateway --port {port} --verbose '
            '>> {log} 2>&1 & echo $! > {pid}"'
        ).format(port=self.port, log=self.log_file, pid=self.pid_file)
        self.exec.execute(
            conn,
            command=cmd,
            group=TaskGroup.SERVICE_CONTROL,
            description="Start OpenClaw gateway",
        )
        self.state = "running"
        return True

    def spin_down(self, conn) -> bool:
        # cmd = (
        #     "bash -lc "
        #     '"if [ -f {pid} ]; then '
        #     "kill $(cat {pid}) >/dev/null 2>&1 || true; "
        #     "rm -f {pid}; "
        #     'fi"'
        # ).format(pid=self.pid_file)
        # self.exec.execute(
        #     conn,
        #     command=cmd,
        #     group=TaskGroup.SERVICE_CONTROL,
        #     description="Stop OpenClaw gateway",
        # )
        # self.state = "stopped"
        return True

    def check(self, conn) -> Dict:
        cmd = (
            "bash -lc "
            '"if [ -f {pid} ] && ps -p $(cat {pid}) >/dev/null 2>&1; '
            'then echo running; else echo stopped; fi"'
        ).format(pid=self.pid_file)
        result = self.exec.execute(
            conn,
            command=cmd,
            group=TaskGroup.SERVICE_CONTROL,
            description="Check OpenClaw gateway status",
        )
        state = (result or "").strip()
        if state == "running":
            self.state = "running"
            return {"status": "running"}
        self.state = "stopped"
        return {"status": "stopped"}

    def get_secrets(self) -> Dict[str, Dict]:
        return {
            "openclaw_gateway": {
                "service_url": self.service_url,
                "port": str(self.port),
            }
        }

    def _ensure_node(self, conn) -> None:
        nvm_prefix = (
            'export NVM_DIR="$HOME/.nvm"; '
            '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; '
        )
        version = self.exec.execute(
            conn,
            command=f"bash -lc '{nvm_prefix} node -v 2>/dev/null || true'",
            group=TaskGroup.SYSTEM_PACKAGES,
            description="Check Node.js version via nvm",
        )
        if version and version.strip().startswith("v"):
            try:
                major = int(version.strip().lstrip("v").split(".")[0])
            except ValueError:
                major = 0
            if major >= 22:
                return

        self.exec.execute(
            conn,
            command="apt-get update",
            group=TaskGroup.SYSTEM_PACKAGES,
            sudo=True,
            description="Update apt cache",
        )
        self.exec.execute(
            conn,
            command="apt-get install -y curl",
            group=TaskGroup.SYSTEM_PACKAGES,
            sudo=True,
            description="Ensure curl is installed",
        )
        self.exec.execute(
            conn,
            command="bash -lc 'curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash'",
            group=TaskGroup.SYSTEM_PACKAGES,
            description="Install nvm",
        )
        self.exec.execute(
            conn,
            command=(
                "bash -lc '"
                'export NVM_DIR="$HOME/.nvm"; '
                '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; '
                "nvm install v22.6.0; "
                "nvm alias default v22.6.0; "
                "nvm use v22.6.0'"
            ),
            group=TaskGroup.SYSTEM_PACKAGES,
            description="Install Node.js via nvm",
        )
        version = self.exec.execute(
            conn,
            command=(
                "bash -lc '"
                f"{nvm_prefix}"
                "node -v'"
            ),
            group=TaskGroup.SYSTEM_PACKAGES,
            description="Verify Node.js version",
        )
        if not version or not version.strip().startswith("v"):
            raise RuntimeError("Node.js install failed; node binary not found.")
        try:
            major = int(version.strip().lstrip("v").split(".")[0])
        except ValueError as exc:
            raise RuntimeError("Unable to parse Node.js version.") from exc
        if major < 22:
            raise RuntimeError(
                f"Node.js 22+ required, but found {version.strip()} after install."
            )

    def _install_openclaw(self, conn) -> None:
        install_cmd = (
            "bash -lc '"
            'export NVM_DIR="$HOME/.nvm"; '
            '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; '
            "nvm use v22.6.0; "
            f"npm install -g openclaw@{self.install_channel}'"
        )
        self.exec.execute(
            conn,
            command=install_cmd,
            group=TaskGroup.SYSTEM_PACKAGES,
            description="Install OpenClaw CLI",
        )
