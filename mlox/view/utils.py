import streamlit as st

from typing import Dict, List


from mlox.config import ServiceConfig


def st_hack_align(container):
    container.write('<div style="height: 28px;"></div>', unsafe_allow_html=True)


def _plot_config_nicely_helper(d: Dict, prefix: str = "") -> List[str]:
    res: List[str] = list()
    for k, v in d.items():
        text = prefix + k
        if v:
            if isinstance(v, str):
                text += ":" + v
                res.append(text)
            elif isinstance(v, Dict):
                res.extend(_plot_config_nicely_helper(v, prefix=k + ":"))
        else:
            res.append(text)
    return res


def plot_config_nicely(
    config: ServiceConfig,
    additional_badges: Dict | None = None,
    prefix_name: str = "",
    icon: str = ":material/star:",
) -> None:
    st.markdown(f"#### {prefix_name}{config.name}")
    badges = ""
    colors = ["blue", "green", "orange", "red", "gray", "violet"]
    badge_list = _plot_config_nicely_helper(config.groups)
    for text in badge_list:
        badges += f":{colors[hash(text) % len(colors)]}-badge[{icon} {text}] "
    st.markdown(badges)

    if additional_badges:
        badges = ""
        badge_list = _plot_config_nicely_helper(additional_badges)
        for text in badge_list:
            badges += (
                f":{colors[hash(text) % len(colors)]}-badge[:material/cloud: {text}] "
            )
        st.markdown(badges)
    st.markdown(config.description)
    st.markdown(
        f"Find out more: [{config.links.get('project', None)}]({config.links.get('project', None)})"
    )
