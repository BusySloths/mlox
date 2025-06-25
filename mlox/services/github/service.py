import logging

from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, cast

from mlox.infra import Bundle
from mlox.service import AbstractService
from mlox.server import AbstractGitServer
from mlox.remote import fs_delete_dir

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@dataclass
class GithubRepoService(AbstractService):
    link: str
    repo_name: str = field(default="", init=False)
    created_timestamp: str = field(default_factory=datetime.now().isoformat, init=False)
    modified_timestamp: str = field(
        default_factory=datetime.now().isoformat, init=False
    )

    def __post_init__(self):
        self.repo_name = self.link.split("/")[-1][:-4]

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
        return dict()

    def pull_repo(self, bundle: Bundle) -> None:
        self.modified_timestamp = datetime.now().isoformat()
        if isinstance(bundle.server, AbstractGitServer):
            server = cast(AbstractGitServer, bundle.server)
            server.git_pull(self.target_path + "/" + self.repo_name)
        else:
            logging.warning("Server is not a git server.")

    def create_and_add_repo(self, bundle: Bundle) -> None:
        if isinstance(bundle.server, AbstractGitServer):
            server = cast(AbstractGitServer, bundle.server)
            server.git_clone(self.link, self.target_path)
        else:
            logging.warning("Server is not a git server.")

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
