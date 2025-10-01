import pandas as pd
import streamlit as st


def _state_badge(state: str) -> str:
    colors = {
        "running": "#16a34a",
        "stopped": "#ef4444",
        "un-initialized": "#64748b",
        "unknown": "#f59e0b",
    }
    color = colors.get(state, "#64748b")
    return f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;background:{color};color:white;font-size:12px'>{state}</span>"


def help():
    # Page chrome
    st.markdown("## Service Documentation 📚")
    st.caption(
        "Quick access to reference docs and project pages for your installed services."
    )
    st.markdown(
        "For more about MLOX, visit the "
        "[Project site](https://mlox.org) or the "
        "[GitHub repo](https://github.com/busysloths/mlox)."
    )

    # Styling
    st.markdown(
        """
        <style>
        .doc-card h4 {margin:0}
        .doc-chip {display:inline-block;padding:2px 8px;border-radius:999px;background:#111827;color:#e5e7eb;margin-right:6px;margin-bottom:4px;font-size:12px;border:1px solid #374151}
        .doc-btn {display:inline-block;padding:6px 10px;background:#2E8B57;color:#fff;border-radius:6px;text-decoration:none;margin-right:6px;margin-bottom:6px}
        .doc-btn.secondary {background:#334155}
        .doc-btn:hover {filter:brightness(1.05)}
        </style>
        """,
        unsafe_allow_html=True,
    )

    ms = st.session_state.get("mlox")
    if not ms:
        st.info("Open a project to see installed service documentation.")
        return

    infra = ms.infra

    # Build installed services list
    entries = []
    for b in infra.bundles:
        for s in b.services:
            cfg = infra.get_service_config(s)
            if not cfg:
                continue
            entries.append(
                {
                    "name": cfg.name,
                    "version": getattr(cfg, "version", ""),
                    "description": getattr(cfg, "description_short", ""),
                    "links": cfg.links or {},
                    "state": getattr(s, "state", "unknown"),
                    "service": s,
                }
            )

    if not entries:
        st.info("No services installed yet. Add services in the Templates tab.")
        return

    # Filters
    c1, c2 = st.columns([2, 1])
    q = c1.text_input("Search", value="", placeholder="Search by name…")
    state_sel = c2.selectbox(
        "State",
        ["all", "running", "stopped", "un-initialized", "unknown"],
        index=0,
    )

    filt = entries
    if q:
        ql = q.lower()
        filt = [e for e in filt if ql in e["name"].lower()]
    if state_sel != "all":
        filt = [e for e in filt if e["state"] == state_sel]

    # Card grid
    cols = st.columns(3)
    for i, e in enumerate(filt):
        col = cols[i % 3]
        with col.container(border=True):
            st.markdown(
                f"<h4>{e['name']}</h4> v{e['version']} {_state_badge(e['state'])}",
                unsafe_allow_html=True,
            )
            if e["description"]:
                st.caption(e["description"])

            # Buttons: Docs, Project, Primary UI if available
            links = e["links"]
            primary_url = None
            # heuristics for a UI link on the running service instance
            if getattr(e["service"], "service_urls", None):
                prefs = ["UI", "Dashboard", "Service", "Open"]
                for p in prefs:
                    if p in e["service"].service_urls:
                        primary_url = e["service"].service_urls[p]
                        break

            btn_cols = st.columns([3, 2, 1])
            with btn_cols[0]:
                url = links.get("documentation") or links.get("docs") or ""
                if url:
                    st.link_button("Documentation", url, use_container_width=True)
            with btn_cols[1]:
                url = links.get("project") or links.get("homepage") or ""
                if url:
                    st.link_button("Project", url, use_container_width=True)
            with btn_cols[2]:
                if primary_url:
                    st.link_button("Open", primary_url, use_container_width=True)


help()
