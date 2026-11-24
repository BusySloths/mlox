from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from mlox.application.firewall_client import firewall_client_id


def test_identity_is_stable_private_and_shared_by_concurrent_processes(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        identities = list(pool.map(lambda _: firewall_client_id(state_dir=tmp_path), range(20)))
    assert len(set(identities)) == 1
    assert UUID(identities[0]).hex == identities[0]
    path = tmp_path / "mlox" / "firewall-client-id"
    assert path.stat().st_mode & 0o777 == 0o600
