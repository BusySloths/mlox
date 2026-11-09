"""Legacy imports and persisted module/class references remain resolvable."""
import importlib

import pytest

import mlox.contracts.services as service_contracts
import mlox.contracts.servers as server_contracts
import mlox.service as legacy_service
import mlox.server as legacy_server


@pytest.mark.parametrize("name", service_contracts.__all__)
def test_service_contracts_are_identical_through_legacy_facade(name):
    legacy = getattr(importlib.import_module("mlox.service"), name)
    assert legacy is getattr(service_contracts, name)
    assert getattr(legacy_service, name) is legacy


@pytest.mark.parametrize("name", server_contracts.__all__)
def test_server_contracts_are_identical_through_legacy_facade(name):
    legacy = getattr(importlib.import_module("mlox.server"), name)
    assert legacy is getattr(server_contracts, name)
    assert getattr(legacy_server, name) is legacy
