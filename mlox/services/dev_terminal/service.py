"""Native developer terminal workstation bootstrap service."""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass, field
from typing import Dict

from mlox.execution import TaskGroup
from mlox.service import AbstractService, ServiceCapability

logger = logging.getLogger(__name__)


@dataclass
class DeveloperTerminalService(AbstractService):
    """Install an opinionated terminal developer environment on a backend host."""

    capabilities = {ServiceCapability.DEVELOPER_TOOLS}
    install_claude_code: bool = True
    install_codex: bool = True
    install_opencode: bool = True
    install_omp: bool = True
    install_herdr: bool = True
    install_atuin: bool = True
    install_lazyvim: bool = True
    install_yazi: bool = True
    install_spaceship: bool = True
    install_pyenv: bool = True
    install_oh_my_zsh: bool = True
    installed_tools: list[str] = field(default_factory=list, init=False)

    def _install_script(self) -> str:
        return self.render_template(
            "install-developer-terminal.sh.tmpl",
            {
                "install_claude_code": str(self.install_claude_code).lower(),
                "install_codex": str(self.install_codex).lower(),
                "install_opencode": str(self.install_opencode).lower(),
                "install_omp": str(self.install_omp).lower(),
                "install_herdr": str(self.install_herdr).lower(),
                "install_atuin": str(self.install_atuin).lower(),
                "install_lazyvim": str(self.install_lazyvim).lower(),
                "install_yazi": str(self.install_yazi).lower(),
                "install_spaceship": str(self.install_spaceship).lower(),
                "install_pyenv": str(self.install_pyenv).lower(),
                "install_oh_my_zsh": str(self.install_oh_my_zsh).lower(),
            },
        )

    def _sensitive_cleanup_script(self) -> str:
        return self.render_template("cleanup-sensitive-state.sh.tmpl", {})

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        script_path = f"{self.target_path}/install-developer-terminal.sh"
        self.exec.fs_write_file(conn, script_path, self._install_script())
        quoted_script_path = shlex.quote(script_path)
        self.exec.execute(
            conn, f"chmod +x {quoted_script_path}", group=TaskGroup.FILESYSTEM
        )
        result = self.exec.execute(
            conn, quoted_script_path, group=TaskGroup.SYSTEM_PACKAGES, sudo=True
        )
        if result is None:
            self.state = "unknown"
            raise RuntimeError("Developer terminal installation failed; see execution history for details.")
        self.state = "running"

    def teardown(self, conn) -> None:
        cleanup_path = f"{self.target_path}/cleanup-sensitive-state.sh"
        self.exec.fs_write_file(conn, cleanup_path, self._sensitive_cleanup_script())
        quoted_cleanup_path = shlex.quote(cleanup_path)
        self.exec.execute(
            conn, f"chmod +x {quoted_cleanup_path}", group=TaskGroup.FILESYSTEM
        )
        self.exec.execute(
            conn, quoted_cleanup_path, group=TaskGroup.SECURITY_ASSETS, sudo=True
        )
        self.exec.fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        self.state = "running"
        return True

    def spin_down(self, conn) -> bool:
        self.state = "stopped"
        return True

    def check(self, conn) -> Dict[str, str]:
        tools = ["zsh", "git", "nvim", "mc", "tmux", "zellij"]
        for enabled, tool in (
            (self.install_claude_code, "claude"),
            (self.install_codex, "codex"),
            (self.install_opencode, "opencode"),
            (self.install_omp, "omp"),
            (self.install_herdr, "herdr"),
            (self.install_yazi, "yazi"),
            (self.install_atuin, "atuin"),
            (self.install_pyenv, "pyenv"),
        ):
            if enabled:
                tools.append(tool)
        command = f"""for tool in {' '.join(tools)}; do
  command -v "$tool" >/dev/null || exit 1
done
nvim_version="$(nvim --version | sed -n '1s/^NVIM v//p' | cut -d- -f1)"
[ -n "$nvim_version" ] && dpkg --compare-versions "$nvim_version" ge 0.11.2"""
        if self.install_lazyvim:
            command += '\n[ -f "$HOME/.config/nvim/lua/config/lazy.lua" ]'
        try:
            self.exec.execute(conn, command, group=TaskGroup.AD_HOC)
            self.state = "running"
            return {"status": "running"}
        except Exception as exc:
            logger.warning("Developer terminal check failed: %s", exc)
            self.state = "unknown"
            return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        return {}
