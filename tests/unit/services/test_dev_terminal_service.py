from mlox.execution import TaskGroup
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

    assert "@install_" not in script
    assert "MIN_NVIM_VERSION=0.11.2" in script
    assert "nvim_version_meets_min" in script
    assert "snapd" in script
    assert "snap install nvim --classic" in script
    assert "ln -sf /snap/bin/nvim /usr/local/bin/nvim" in script
    assert "Neovim $MIN_NVIM_VERSION or newer is required for LazyVim." in script
    assert "npm install -g @anthropic-ai/claude-code" in script
    assert "npm install -g @openai/codex" in script
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
    assert "command -v zsh git nvim mc yazi atuin claude codex pyenv tmux zellij" in commands[0]
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
    assert "append_once 'export COLORTERM=truecolor'" in script
    assert (
        'append_once \'export TERMINFO_DIRS="$HOME/.terminfo:/etc/terminfo:/lib/terminfo:/usr/share/terminfo"\''
        in script
    )
    assert "append_once 'export NCURSES_NO_UTF8_ACS=1'" in script
    assert "append_once 'export LESSCHARSET=utf-8'" in script
    assert "append_once 'unset LC_ALL'" in script


def test_install_script_installs_and_configures_tmux_for_lazyvim() -> None:
    script = _service()._install_script()

    assert " tmux " in script
    assert " screen " not in script
    assert "ncurses-bin ncurses-term" in script
    assert 'TMUX_CONF="$TARGET_HOME/.tmux.conf"' in script
    assert 'set -g default-terminal "tmux-256color"' in script
    assert 'set -ga terminal-overrides ",*:RGB"' in script
    assert 'set -g focus-events on' in script
    assert 'set -g escape-time 10' in script
    assert 'set -g mouse on' in script
    assert 'setw -g mode-keys vi' in script
    assert 'set -g set-clipboard on' in script
    assert 'set -g prefix C-a' in script
    assert 'bind | split-window -h -c "#{pane_current_path}"' in script
    assert 'bind - split-window -v -c "#{pane_current_path}"' in script
    assert 'bind h select-pane -L' in script
    assert 'bind-key -T copy-mode-vi v send -X begin-selection' in script
    assert 'bind ? display-popup -E -w 78 -h 24 "cat ~/.tmux-shortcuts"' in script


def test_install_script_writes_tmux_shortcut_reference() -> None:
    script = _service()._install_script()

    assert 'TMUX_SHORTCUTS="$TARGET_HOME/.tmux-shortcuts"' in script
    assert "tmux essentials for this host" in script
    assert "tmux new -As dev" in script
    assert "Ctrl-a |      split right" in script
    assert "Ctrl-a h/j/k/l move between panes" in script
    assert "Ctrl-a [      enter copy mode" in script
    assert 'alias mux="tmux new -As dev"' in script
    assert 'alias tmux-help="cat ~/.tmux-shortcuts"' in script


def test_install_script_installs_and_configures_zellij_for_lazyvim() -> None:
    script = _service()._install_script()

    assert "apt-get install -yq zellij || true" in script
    assert "https://github.com/zellij-org/zellij/releases/latest/download/zellij-${zellij_arch}.tar.gz" in script
    assert 'ZELLIJ_CONFIG="$ZELLIJ_CONFIG_DIR/config.kdl"' in script
    assert 'default_mode "normal"' in script
    assert "zellij-autolock.wasm" in script
    assert '"swaits/zellij-nav.nvim"' in script
    assert '"<cmd>ZellijNavigateLeftTab<cr>"' in script
    assert '"<cmd>ZellijNavigateRightTab<cr>"' in script
    assert 'command = "silent !zellij action switch-mode normal"' in script
    assert 'alias zj="zellij attach dev --create"' in script
    assert 'alias zellij-help="cat ~/.zellij-shortcuts"' in script


def test_install_script_adds_codex_to_lazyvim() -> None:
    script = _service()._install_script()

    assert "INSTALL_CODEX=true" in script
    assert '"<leader>ao"' in script
    assert 'vim.cmd("terminal codex")' in script
    assert 'desc = "Open Codex"' in script


def test_install_script_installs_oh_my_zsh_without_interactive_installer() -> None:
    script = _service()._install_script()

    assert "INSTALL_OH_MY_ZSH=true" in script
    assert "https://github.com/ohmyzsh/ohmyzsh.git" in script
    assert 'append_once \'export ZSH="$HOME/.oh-my-zsh"\'' in script
    assert "append_once 'plugins=(git direnv fzf pyenv)'" in script
    assert 'append_once \'[ -f "$ZSH/oh-my-zsh.sh" ] && source "$ZSH/oh-my-zsh.sh"\'' in script


def test_sensitive_cleanup_removes_claude_code_and_history_state() -> None:
    script = _service()._sensitive_cleanup_script()

    assert "TARGET_USER=\"${SUDO_USER:-$(id -un)}\"" in script
    assert "remove_home_path" in script
    assert 'rm -rf -- "$TARGET_HOME/$relative_path"' in script
    assert 'remove_home_path ".claude"' in script
    assert 'remove_home_path ".claude.json"' in script
    assert 'remove_home_path ".config/claude-code"' in script
    assert 'remove_home_path ".cache/claude-code"' in script
    assert 'remove_home_path ".local/share/claude-code"' in script
    assert 'remove_home_path ".local/state/claude-code"' in script
    assert 'remove_home_path ".atuin"' in script
    assert 'remove_home_path ".local/share/atuin"' in script
    assert 'remove_home_path ".tmux.conf"' in script
    assert 'remove_home_path ".tmux-shortcuts"' in script
    assert 'remove_home_path ".config/zellij/config.kdl"' in script
    assert 'remove_home_path ".zellij-shortcuts"' in script
    assert 'remove_home_path ".codex"' in script


def test_teardown_runs_sensitive_cleanup_before_removing_target_path() -> None:
    service = _service()
    calls: list[tuple[str, str, dict]] = []

    class Exec:
        def fs_write_file(self, _conn, path, content):
            calls.append(("fs_write_file", path, {"content": content}))

        def execute(self, _conn, command, **kwargs):
            calls.append(("execute", command, kwargs))

        def fs_delete_dir(self, _conn, path):
            calls.append(("fs_delete_dir", path, {}))

    service.exec = Exec()  # type: ignore[assignment]

    service.teardown(object())

    assert calls[0][0] == "fs_write_file"
    assert calls[0][1] == "/tmp/dev-terminal/cleanup-sensitive-state.sh"
    assert 'remove_home_path ".claude"' in calls[0][2]["content"]
    assert calls[1] == (
        "execute",
        "chmod +x /tmp/dev-terminal/cleanup-sensitive-state.sh",
        {"group": TaskGroup.FILESYSTEM},
    )
    assert calls[2] == (
        "execute",
        "/tmp/dev-terminal/cleanup-sensitive-state.sh",
        {"group": TaskGroup.SECURITY_ASSETS, "sudo": True},
    )
    assert calls[3] == ("fs_delete_dir", "/tmp/dev-terminal", {})
    assert service.state == "un-initialized"
