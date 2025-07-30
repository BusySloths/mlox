import os
import logging

from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, cast

from mlox.infra import Bundle, Repo
from mlox.service import AbstractService
from mlox.server import AbstractGitServer
from mlox.remote import fs_delete_dir, fs_exists_dir, exec_command, fs_read_file

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class GithubRepoService(AbstractService, Repo):
    link: str
    private_repo: str
    deploy_key: str = field(default="", init=False)
    cloned: bool = field(default=False, init=False)

    def __post_init__(self):
        self.repo_name = self.link.split("/")[-1][:-4]
        self.state = "running"

    def setup(self, conn) -> None:
        self.service_urls = dict()
        self.service_ports = dict()
        self.state = "running"

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
        try:
            exists = fs_exists_dir(conn, repo_path)
        except Exception as e:
            logging.warning(f"Could not check repo directory existence: {e}")
        return {"cloned": self.cloned, "exists": exists}

    def generate_deploy_ssh_key(
        self,
        conn,
        key_type: str = "rsa",
        key_bits: int = 4096,
        key_name: str = "id_deploy",
    ) -> None:
        """
        Generates an SSH key pair for use as a GitHub deploy key on the remote server.
        Returns a dict with 'private_key' and 'public_key'.
        """

        ssh_dir = f"/tmp/mlox_ssh_{os.getpid()}"
        exec_command(conn, f"mkdir -p {ssh_dir}")
        private_key_path = f"{ssh_dir}/{key_name}"
        public_key_path = private_key_path + ".pub"
        # Generate key pair using ssh-keygen on remote
        exec_command(
            conn,
            f"yes | ssh-keygen -t {key_type} -b {key_bits} -N '' -f {private_key_path}",
            sudo=False,
        )
        # Add private key to remote ssh-agent
        # exec_command(conn, "eval `ssh-agent -s`")
        exec_command(conn, f"eval `ssh-agent -s` && ssh-add {private_key_path}")
        # Read keys from remote
        # private_key = fs_read_file(conn, private_key_path, format="string")
        public_key = fs_read_file(conn, public_key_path, format="string")
        # Optionally clean up
        # exec_command(conn, f"rm -rf {ssh_dir}")
        self.deploy_key = public_key

    def pull_repo(self, bundle: Bundle) -> None:
        self.modified_timestamp = datetime.now().isoformat()
        if hasattr(bundle.server, "git_pull"):
            try:
                server = cast(AbstractGitServer, bundle.server)
                server.git_pull(self.target_path + "/" + self.repo_name)
            except Exception as e:
                logging.warning(f"Could not clone repo: {e}")
                self.state = "unknown"
                return
            self.state = "running"
        else:
            logging.warning("Server is not a git server.")
            self.state = "unknown"

    def create_and_add_repo(self, bundle: Bundle) -> None:
        if hasattr(bundle.server, "git_clone"):
            try:
                server = cast(AbstractGitServer, bundle.server)
                server.git_clone(self.link, self.target_path)
                self.cloned = True
                self.state = "running"
            except Exception as e:
                logging.warning(f"Could not clone repo: {e}")
                self.state = "unknown"
        else:
            logging.warning("Server is not a git server.")
            self.state = "unknown"

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
