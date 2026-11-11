from legacy.ui.view.services.repo_deploy import _env_vars_to_text, _parse_env_text


def test_env_text_helpers_parse_dotenv_style_content():
    text = "\n".join(
        [
            "# ignored",
            "A=1",
            "export B=two",
            "C=value=with=equals",
            "NO_EQUALS",
            "",
        ]
    )

    parsed = _parse_env_text(text)

    assert parsed == {"A": "1", "B": "two", "C": "value=with=equals"}
    assert _env_vars_to_text({"B": "2", "A": "1"}) == "A=1\nB=2"
