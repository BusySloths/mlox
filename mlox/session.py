from dataclasses import dataclass, field

from mlox.infra import Infrastructure
from mlox.secret_manager import TinySecretManager
from mlox.utils import dataclass_to_dict, dict_to_dataclass
from mlox.server import AbstractServer
from mlox.service import AbstractService


@dataclass
class MloxSession:
    username: str
    password: str

    infra: Infrastructure = field(init=False)
    secrets: TinySecretManager = field(init=False)

    def __post_init__(self):
        self.secrets = TinySecretManager(
            f"/{self.username}.key", ".secrets", self.password
        )
        self.load_infrastructure()

    def save_infrastructure(self) -> None:
        infra_dict = dataclass_to_dict(self.infra)
        self.secrets.save_secret("MLOX_CONFIG_INFRASTRUCTURE", infra_dict)

    def load_infrastructure(self) -> None:
        infra_dict = self.secrets.load_secret("MLOX_CONFIG_INFRASTRUCTURE")
        if infra_dict and isinstance(infra_dict, dict):
            self.infra = dict_to_dataclass(
                infra_dict, hooks=[AbstractServer, AbstractService]
            )
        else:
            self.infra = Infrastructure()
