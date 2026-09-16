"""Project selection dialog shared by runtime project switching."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from mlox.application.use_cases.project import ProjectOption


class ProjectSwitchDialog(ModalScreen[tuple[str, str] | None]):
    """Prompt for a discovered project and its password."""

    def __init__(self, projects: list[ProjectOption]) -> None:
        super().__init__()
        self.projects = projects
        self._projects_by_path = {project.path: project for project in projects}

    def compose(self) -> ComposeResult:
        with Container(id="project-switch-dialog"):
            yield Label("Switch Project", id="project-switch-title")
            if self.projects:
                yield Select(
                    [(project.name, project.path) for project in self.projects],
                    allow_blank=False,
                    id="project-switch-select",
                )
                yield Input(
                    value=self.projects[0].password,
                    placeholder="Password",
                    password=True,
                    id="project-switch-password",
                )
                yield Static("", id="project-switch-error")
            else:
                yield Static(
                    "No .mlox projects were found in the current directory.",
                    id="project-switch-empty",
                )
            with Horizontal(id="project-switch-actions"):
                yield Button("Cancel", id="cancel-project-switch")
                yield Button(
                    "Switch",
                    id="confirm-project-switch",
                    variant="success",
                    disabled=not bool(self.projects),
                )

    @on(Select.Changed, "#project-switch-select")
    def handle_project_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return
        project = self._projects_by_path.get(str(event.value))
        if project is not None:
            self.query_one("#project-switch-password", Input).value = project.password

    @on(Button.Pressed, "#cancel-project-switch")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-project-switch")
    def handle_confirm(self, _: Button.Pressed) -> None:
        if not self.projects:
            self.dismiss(None)
            return
        select = self.query_one("#project-switch-select", Select)
        password = self.query_one("#project-switch-password", Input).value
        if select.value is Select.BLANK or not password:
            self.query_one("#project-switch-error", Static).update(
                "Project and password are required"
            )
            return
        self.dismiss((str(select.value), password))
