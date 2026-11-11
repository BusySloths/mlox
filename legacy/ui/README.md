# Legacy Streamlit web UI (archived)

The former Streamlit web UI (`mlox/app.py` and `mlox/view/`), moved out of the
package as the first step of its removal (ADR "Streamlit web UI extraction" in
`docs/DOCTRINE.md`). It is not installed with MLOX, not linted or tested in CI,
and gets no changes. Use `mlox ui` instead: it serves the TUI in the browser.

To run it anyway, from the repository root:

```sh
uv run --with streamlit --with streamlit-vis-timeline streamlit run legacy/ui/app.py
uv run --with streamlit --with streamlit-vis-timeline pytest legacy/ui/tests
```

`app.py` puts the repository root on `sys.path` and registers the Streamlit
handlers itself; the core registry no longer loads them.
