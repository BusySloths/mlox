import crypt

import pytest

from mlox.services.registry.docker import RegistryDockerService


def test_generate_htpasswd_entry_valid():
    entry = RegistryDockerService._generate_htpasswd_entry("alice", "secret")
    assert entry.startswith("alice:")

    username, hashed = entry.strip().split(":", 1)
    assert username == "alice"
    assert crypt.crypt("secret", hashed) == hashed


@pytest.mark.parametrize(
    "username,password",
    [("", "secret"), ("alice", ""), ("", "")],
)
def test_generate_htpasswd_entry_requires_credentials(username, password):
    with pytest.raises(ValueError):
        RegistryDockerService._generate_htpasswd_entry(username, password)
