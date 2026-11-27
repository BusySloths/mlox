from concurrent.futures import ThreadPoolExecutor
import sys
from types import SimpleNamespace
from uuid import UUID

from mlox.application import firewall_client
from mlox.application.firewall_client import firewall_client_id


def test_identity_is_stable_private_and_shared_by_concurrent_processes(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        identities = list(pool.map(lambda _: firewall_client_id(state_dir=tmp_path), range(20)))
    assert len(set(identities)) == 1
    assert UUID(identities[0]).hex == identities[0]
    path = tmp_path / "mlox" / "firewall-client-id"
    assert path.stat().st_mode & 0o777 == 0o600


def test_windows_lock_uses_msvcrt_byte_range_lock(tmp_path, monkeypatch):
    calls = []
    msvcrt = SimpleNamespace(
        LK_LOCK=1,
        LK_UNLCK=2,
        locking=lambda descriptor, mode, length: calls.append((mode, length)),
    )
    monkeypatch.setitem(sys.modules, "msvcrt", msvcrt)
    lock_path = tmp_path / "firewall-client.lock"

    with lock_path.open("a+b") as handle:
        with firewall_client._exclusive_lock(handle, windows=True):
            assert handle.read() == b"\0"

    assert calls == [(msvcrt.LK_LOCK, 1), (msvcrt.LK_UNLCK, 1)]
