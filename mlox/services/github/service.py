import re
import logging

from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, cast, Literal

from mlox.infra import Bundle, Repo
from mlox.service import AbstractService
from mlox.server import AbstractGitServer
from mlox.remote import (
    fs_delete_dir,
    fs_exists_dir,
    exec_command,
    fs_read_file,
    fs_create_dir,
    fs_list_files,
    fs_list_file_tree,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class GithubRepoService(AbstractService, Repo):
    link: str
    is_private: bool = field(default=False, init=True)
    repo_name: str = field(default="", init=False)
    user_or_org_name: str = field(default="", init=False)
    deploy_key: str = field(default="", init=False)
    cloned: bool = field(default=False, init=False)

    def __post_init__(self):
        splits = self.link.split("/")
        self.repo_name = splits[-1][:-4]
        self.user_or_org_name = splits[-2]
        self.state = "un-initialized"

    def get_url(self) -> str:
        return f"https://github.com/{self.user_or_org_name}/{self.repo_name}"

    def setup(self, conn) -> None:
        self.service_urls = {"Repository": self.get_url()}
        self.service_ports = dict()

        if self.is_private:
            logging.info(f"Generate deploy keys for {self.repo_name}.")
            self._generate_deploy_ssh_key(conn)
            self.state = "running"
        else:
            self.git_clone(conn)

    def teardown(self, conn):
        fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn):
        return None

    def check(self, conn) -> Dict:
        """
        Checks if the repository is cloned and the directory exists on the remote server.
        Returns a dict with 'cloned' (bool) and 'exists' (bool).
        """
        repo_path = self.target_path + "/" + self.repo_name
        exists = False
        repo_files = list()
        repo_tree = list()
        try:
            exists = fs_exists_dir(conn, repo_path)
            repo_files = fs_list_files(conn, repo_path)
            repo_tree = fs_list_file_tree(conn, repo_path)
        except Exception as e:
            logging.warning(f"Could not check repo directory existence: {e}")
        return {
            "cloned": self.cloned,
            "exists": exists,
            "private": self.is_private,
            "files": repo_files,
            "tree": repo_tree,
        }

    def _generate_deploy_ssh_key(
        self,
        conn,
        key_type: str = "rsa",
        key_bits: int = 4096,
    ) -> None:
        """
        Generates an SSH key pair for use as a GitHub deploy key on the remote server.
        """
        key_name = f"mlox_deploy_{self.repo_name}"
        ssh_dir = self.target_path + "/.ssh"
        fs_create_dir(conn, ssh_dir)
        private_key_path = f"{ssh_dir}/{key_name}"
        public_key_path = private_key_path + ".pub"
        # Generate key pair using ssh-keygen on remote
        exec_command(
            conn,
            f"yes | ssh-keygen -t {key_type} -b {key_bits} -N '' -f {private_key_path}",
            sudo=False,
        )
        self.deploy_key = fs_read_file(conn, public_key_path, format="string")

    def _repo_public(self, conn, clone_or_pull: Literal["clone", "pull"]) -> None:
        full_cmd = f"cd {self.target_path} && git clone {self.link}"
        if clone_or_pull == "pull":
            full_cmd = f"cd {self.target_path}/{self.repo_name} && git pull"
        exec_command(conn, f"bash -c '{full_cmd}'", sudo=False, pty=False)

    def _repo_with_deploy_key(
        self, conn, clone_or_pull: Literal["clone", "pull"]
    ) -> int:
        """
        1. Start ssh-agent and add the deploy key (assumes key is already generated and stored)
        2. Clone the repo using the key
        3. Kill the agent and reset previous state
        """
        key_name = f"mlox_deploy_{self.repo_name}"
        # agent_check = exec_command(
        #     conn, "pgrep ssh-agent || echo 'not_running'", sudo=False
        # )

        git_cmd = "pull"
        trg_path = self.target_path + "/" + self.repo_name
        private_key_path = f"../.ssh/{key_name}"
        if clone_or_pull == "clone":
            git_cmd = f"clone {self.link}"
            trg_path = self.target_path
            private_key_path = f".ssh/{key_name}"
        full_cmd = (
            f"cd {trg_path} && "
            'eval "$(ssh-agent -s)" && '
            f"ssh-add {private_key_path} && "
            f"git {git_cmd}"
        )
        res = exec_command(conn, f"bash -c '{full_cmd}'", sudo=False, pty=False)
        err_code = 1
        if res:
            # Try to find the agent pid from the output
            pid_match = re.search(r"Agent pid (\d+)", str(res))
            if pid_match:
                pid = pid_match.group(1)
                exec_command(conn, f"kill -9 {pid}", sudo=False)
                err_code = 0
            else:
                logging.error(
                    "Could not find ssh-agent PID to kill after cloning repo."
                )
                err_code = 2
        if err_code == 0:
            self.cloned = True
            self.state = "running"
        else:
            self.state = "unknown"
        return err_code

    def git_clone(self, conn) -> None:
        if self.is_private:
            self._repo_with_deploy_key(conn, "clone")
        else:
            self._repo_public(conn, "clone")
        if fs_exists_dir(conn, self.target_path + "/" + self.repo_name):
            self.modified_timestamp = datetime.now().isoformat()
            self.created_timestamp = datetime.now().isoformat()
            self.cloned = True
            self.state = "running"
        else:
            self.state = "unknown"

    def git_pull(self, conn) -> None:
        if self.is_private:
            self._repo_with_deploy_key(conn, "pull")
        else:
            self._repo_public(conn, "pull")
        self.modified_timestamp = datetime.now().isoformat()

    # def pull_repo(self, bundle: Bundle) -> None:
    #     self.modified_timestamp = datetime.now().isoformat()
    #     if hasattr(bundle.server, "git_pull"):
    #         try:
    #             server = cast(AbstractGitServer, bundle.server)
    #             server.git_pull(self.target_path + "/" + self.repo_name)
    #         except Exception as e:
    #             logging.warning(f"Could not clone repo: {e}")
    #             self.state = "unknown"
    #             return
    #         self.state = "running"
    #     else:
    #         logging.warning("Server is not a git server.")
    #         self.state = "unknown"

    # def remove_repo(self, ip: str, repo: Repo) -> None:
    #     bundle = next(
    #         (bundle for bundle in self.bundles if bundle.server.ip == ip), None
    #     )
    #     if not bundle:
    #         return
    #     if not bundle.server.mlox_user:
    #         return
    #     bundle.server.git_remove(repo.path)
    #     bundle.repos.remove(repo)
