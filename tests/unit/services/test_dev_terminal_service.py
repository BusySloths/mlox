from mlox.services.dev_terminal.service import DeveloperTerminalService


def _service() -> DeveloperTerminalService:
    return DeveloperTerminalService(
        name="dev-terminal:test",
        service_config_id="dev-terminal-0.1-beta",
        template="template.yaml",
        target_path="/tmp/dev-terminal",
    )


def test_install_script_installs_modern_neovim_with_snap_when_needed() -> None:
    script = _service()._install_script()

    assert "MIN_NVIM_VERSION=0.11.2" in script
    assert "nvim_version_meets_min" in script
    assert "snapd" in script
    assert "snap install nvim --classic" in script
    assert "ln -sf /snap/bin/nvim /usr/local/bin/nvim" in script
    assert "Neovim $MIN_NVIM_VERSION or newer is required for LazyVim." in script
    assert " mc neovim nodejs " not in script


def test_check_requires_lazyvim_compatible_neovim() -> None:
    service = _service()
    commands: list[str] = []

    class Exec:
        def execute(self, _conn, command, **_kwargs):
            commands.append(command)

    service.exec = Exec()  # type: ignore[assignment]

    assert service.check(object()) == {"status": "running"}
    assert commands
    assert "nvim --version" in commands[0]
    assert 'dpkg --compare-versions "$nvim_version" ge 0.11.2' in commands[0]


def test_install_script_installs_atuin_for_target_user() -> None:
    script = _service()._install_script()

    assert 'sudo -H -u "$TARGET_USER" env HOME="$TARGET_HOME" sh -c' in script
    assert "https://setup.atuin.sh" in script
    assert 'ln -sf "$TARGET_HOME/.atuin/bin/atuin" /usr/local/bin/atuin' in script
    assert '[[ -d "$HOME/.atuin/bin" ]] && export PATH="$HOME/.atuin/bin:$PATH"' in script
    assert (
        'if [ -x "$HOME/.atuin/bin/atuin" ]; then eval "$($HOME/.atuin/bin/atuin init zsh)"; '
        'elif command -v atuin >/dev/null 2>&1; then eval "$(atuin init zsh)"; fi'
        in script
    )


def test_install_script_repairs_and_exposes_pyenv_for_target_user() -> None:
    script = _service()._install_script()

    assert 'install -d -o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.pyenv"' in script
    assert 'git clone https://github.com/pyenv/pyenv.git "$TARGET_HOME/.pyenv"' in script
    assert 'git -C "$TARGET_HOME/.pyenv" init' in script
    assert 'git -C "$TARGET_HOME/.pyenv" fetch --depth 1 origin master' in script
    assert 'git -C "$TARGET_HOME/.pyenv" checkout -f FETCH_HEAD' in script
    assert 'ln -sf "$TARGET_HOME/.pyenv/bin/pyenv" /usr/local/bin/pyenv' in script
    assert '[[ -d "$PYENV_ROOT/bin" ]] && export PATH="$PYENV_ROOT/bin:$PATH"' in script
    assert (
        '[[ -d "$PYENV_ROOT/shims" ]] && export PATH="$PYENV_ROOT/shims:$PATH"'
        in script
    )
    assert 'command -v pyenv >/dev/null 2>&1 && eval "$(pyenv init -)"' in script


def test_install_script_configures_utf8_locale_for_zsh_and_pyenv() -> None:
    script = _service()._install_script()

    assert "locales" in script
    assert "locale-gen C.UTF-8" in script
    assert "update-locale LANG=C.UTF-8 LC_CTYPE=C.UTF-8" in script
    assert "append_once 'export LANG=C.UTF-8'" in script
    assert "append_once 'export LC_CTYPE=C.UTF-8'" in script
    assert "append_once 'unset LC_ALL'" in script
