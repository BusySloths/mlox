from dataclasses import dataclass, field

from mlox.infra import Infrastructure
from mlox.secret_manager import TinySecretManager


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
        infra_dict = self.infra.to_dict()
        self.secrets.save_secret("MLOX_CONFIG_INFRASTRUCTURE", infra_dict)

    def load_infrastructure(self) -> None:
        infra_dict = self.secrets.load_secret("MLOX_CONFIG_INFRASTRUCTURE")
        print(infra_dict)
        if not infra_dict:
            raise ValueError("No infrastructure data found in secrets.")
        if not isinstance(infra_dict, dict):
            raise ValueError("Infrastructure data is not in the expected format.")
        self.infra = Infrastructure.from_dict(infra_dict)
