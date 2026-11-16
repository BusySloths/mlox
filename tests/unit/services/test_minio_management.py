from contextlib import contextmanager
from types import SimpleNamespace

from cryptography import x509

from mlox.application.use_cases import minio
from mlox.application.use_cases.databases import describe_databases
from mlox.service import ServiceCapability


class Executor:
    def __init__(self):
        self.commands = []
        self.restarts = 0
        self.uploads = {}

    def _run_task(self, conn, **kwargs):
        self.commands.append(kwargs["command"])
        return "MLOX_TLS_OK"

    def fs_copy(self, conn, source, destination):
        with open(source, "rb") as file:
            self.uploads[destination.rsplit("/", 1)[-1]] = file.read()

    def docker_restart(self, conn, *args, **kwargs):
        self.restarts += 1
        assert kwargs["force_recreate"]
        return "started"


@contextmanager
def connection():
    yield object()


class Storage:
    def __init__(self, fails=False):
        self.fails = fails

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def list_buckets(self):
        if self.fails:
            raise RuntimeError("unreachable")
        return ["data"]

    def list_keys(self, bucket):
        return ["one.txt"]


def make_service(fails=False):
    executor = Executor()
    service = SimpleNamespace(service_url="https://minio.example:9000", target_path="/tmp/a space",
                              target_docker_script="compose.yaml", target_docker_env=".env",
                              certificate="old", exec=executor,
                              get_storage=lambda infra: Storage(fails))
    bundle = SimpleNamespace(server=SimpleNamespace(get_server_connection=connection))
    return service, bundle, executor


def test_renew_certificate_validates_new_endpoint_and_creates_dns_certificate():
    service, bundle, executor = make_service()
    result = minio.renew_certificate(None, bundle, service)
    assert result.success
    cert = x509.load_pem_x509_certificate(service.certificate.encode())
    assert cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == ["minio.example"]
    assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days == 3650
    assert executor.restarts == 1
    assert executor.uploads["cert.pem"] == service.certificate.encode()
    assert "Collect service secrets" in result.message


def test_renew_certificate_restores_previous_certificate_when_verification_fails(monkeypatch):
    service, bundle, executor = make_service(fails=True)
    monkeypatch.setattr(minio.time, "sleep", lambda _: None)
    result = minio.renew_certificate(None, bundle, service)
    assert not result.success
    assert service.certificate == "old"
    assert executor.restarts == 2
    assert any("old-cert.pem cert.pem" in command for command in executor.commands)


def test_storage_services_appear_in_data_overview():
    services = [SimpleNamespace(name=name, capabilities={ServiceCapability.OBJECT_STORAGE}) for name in ("minio", "gcp")]
    bundle = SimpleNamespace(name="prod", server=None, services=services)
    result = describe_databases(SimpleNamespace(bundles=[bundle]))
    assert [row["service"] for row in result.data["rows"]] == ["minio", "gcp"]


def test_panel_browses_buckets_and_allows_renewal_when_loading_fails():
    import asyncio
    from textual.app import App, ComposeResult
    from textual.widgets import Button, DataTable, Static
    from mlox.tui.services.minio import MinioSettingsPanel

    async def exercise(fails):
        service, bundle, _ = make_service(fails=fails)
        panel = MinioSettingsPanel(None, bundle, service)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield panel

        async with TestApp().run_test() as pilot:
            await pilot.pause(0.3)
            assert not panel.query_one("#minio-renew-certificate", Button).disabled
            if fails:
                assert "Could not load buckets" in str(panel.query_one("#minio-message", Static).render())
            else:
                assert panel.query_one("#minio-buckets", DataTable).row_count == 1
                panel.query_one("#minio-buckets", DataTable).focus()
                await pilot.press("enter")
                await pilot.pause(0.3)
                assert panel.query_one("#minio-objects", DataTable).row_count == 1

    asyncio.run(exercise(False))
    asyncio.run(exercise(True))
