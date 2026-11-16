"""MinIO bucket browser and certificate controls."""
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Static

from mlox.application.use_cases.minio import certificate_details, list_buckets, list_objects, renew_certificate


class MinioSettingsPanel(VerticalScroll):
    def __init__(self, infra, bundle, service) -> None:
        super().__init__()
        self.infra, self.bundle, self.service = infra, bundle, service
        self.buckets: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("MinIO Object Storage", classes="minio-title")
        yield Static(id="minio-certificate", markup=False)
        yield Static("Renewal restarts MinIO. Afterwards, collect service secrets and reconnect clients.", classes="minio-note", markup=False)
        with Horizontal(classes="minio-actions"):
            yield Button("Refresh Buckets", id="minio-refresh", variant="primary")
            yield Button("Renew Certificate", id="minio-renew-certificate", variant="warning")
        yield Static("Select a bucket to list its objects.", id="minio-message", markup=False)
        with Horizontal(id="minio-browser"):
            buckets = DataTable(id="minio-buckets")
            buckets.cursor_type = "row"
            buckets.add_columns("Buckets")
            yield buckets
            objects = DataTable(id="minio-objects")
            objects.cursor_type = "row"
            objects.add_columns("Object key")
            yield objects

    def on_mount(self) -> None:
        self._refresh()

    def _run(self, operation, callback, group: str) -> None:
        self._busy(True)
        app = self.app
        def finish(result):
            if self.is_attached:
                self._busy(False)
                callback(result)
        app.run_worker(lambda: app.call_from_thread(finish, operation()), thread=True, exclusive=True, group=group)

    def _busy(self, busy: bool) -> None:
        for button in self.query(Button):
            button.disabled = busy

    def _refresh(self) -> None:
        self.query_one("#minio-certificate", Static).update("Project certificate: " + certificate_details(self.service.certificate))
        self.query_one("#minio-message", Static).update("Loading buckets…")
        self._run(lambda: list_buckets(self.infra, self.service), self._show_buckets, "minio-buckets")

    @on(Button.Pressed, "#minio-refresh")
    def refresh_pressed(self) -> None:
        self._refresh()

    def _show_buckets(self, result) -> None:
        table = self.query_one("#minio-buckets", DataTable)
        table.clear()
        self.query_one("#minio-objects", DataTable).clear()
        self.buckets = (result.data or {}).get("buckets", []) if result.success else []
        for name in self.buckets:
            table.add_row(name)
        self.query_one("#minio-message", Static).update(result.message)

    @on(DataTable.RowSelected, "#minio-buckets")
    def bucket_selected(self, event: DataTable.RowSelected) -> None:
        index = event.cursor_row
        if 0 <= index < len(self.buckets):
            bucket = self.buckets[index]
            self.query_one("#minio-message", Static).update(f"Loading objects in {bucket}…")
            self._run(lambda: list_objects(self.infra, self.service, bucket), self._show_objects, "minio-objects")

    def _show_objects(self, result) -> None:
        table = self.query_one("#minio-objects", DataTable)
        table.clear()
        for name in (result.data or {}).get("objects", []):
            table.add_row(name)
        self.query_one("#minio-message", Static).update(result.message)

    @on(Button.Pressed, "#minio-renew-certificate")
    def renew_pressed(self) -> None:
        self.query_one("#minio-message", Static).update("Renewing certificate and verifying MinIO…")
        workspace = getattr(self.app, "workspace", None)
        self._run(lambda: renew_certificate(self.infra, self.bundle, self.service, workspace), self._show_renewal, "minio-renew")

    def _show_renewal(self, result) -> None:
        self.query_one("#minio-certificate", Static).update("Project certificate: " + certificate_details(self.service.certificate))
        self.query_one("#minio-message", Static).update(result.message)
        self.notify(result.message, severity="information" if result.success else "error", timeout=20)


def settings(infra, bundle, service):
    return MinioSettingsPanel(infra, bundle, service)
