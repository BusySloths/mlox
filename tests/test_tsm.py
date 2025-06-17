import pytest
import json
from pathlib import Path
from mlox.secret_manager import TinySecretManager


@pytest.fixture
def manager():
    """Provides a fresh TinySecretManager instance for each test."""
    return TinySecretManager()


def test_initialization(manager: TinySecretManager):
    """Test that the manager initializes with no secrets."""
    assert manager.get_secret("ANY_KEY") is None


def test_set_and_get_secret(manager: TinySecretManager):
    """Test setting and getting a secret."""
    manager.set_secret("API_KEY", "12345")
    assert manager.get_secret("API_KEY") == "12345"


def test_get_secret_not_found(manager: TinySecretManager):
    """Test getting a non-existent secret returns None."""
    assert manager.get_secret("NON_EXISTENT_KEY") is None


def test_get_secret_not_found_with_default(manager: TinySecretManager):
    """Test getting a non-existent secret returns the default value."""
    assert manager.get_secret("NON_EXISTENT_KEY", "default_value") == "default_value"


def test_load_from_env(manager: TinySecretManager, monkeypatch: pytest.MonkeyPatch):
    """Test loading secrets from environment variables."""
    monkeypatch.setenv("APP_SECRET_USER", "testuser")
    monkeypatch.setenv("APP_SECRET_PASSWORD", "secure")
    monkeypatch.setenv("OTHER_VAR", "othervalue")  # Should not be loaded

    manager.load_from_env(prefix="APP_SECRET_")

    assert manager.get_secret("USER") == "testuser"
    assert manager.get_secret("PASSWORD") == "secure"
    assert manager.get_secret("OTHER_VAR") is None
    assert manager.get_secret("APP_SECRET_USER") is None  # Prefix should be stripped


def test_load_from_env_empty_prefix(
    manager: TinySecretManager, monkeypatch: pytest.MonkeyPatch
):
    """Test loading secrets from environment variables with an empty prefix."""
    monkeypatch.setenv("TOKEN", "token_value")
    manager.load_from_env(prefix="")  # Load all env vars
    assert manager.get_secret("TOKEN") == "token_value"


def test_load_from_json_file(manager: TinySecretManager, tmp_path: Path):
    """Test loading secrets from a JSON file."""
    secrets_data = {"DB_HOST": "localhost", "DB_PORT": "5432"}
    secret_file = tmp_path / "secrets.json"
    secret_file.write_text(json.dumps(secrets_data))

    manager.load_from_json_file(str(secret_file))

    assert manager.get_secret("DB_HOST") == "localhost"
    assert manager.get_secret("DB_PORT") == "5432"


def test_load_from_json_file_not_found(manager: TinySecretManager, capsys):
    """Test loading from a non-existent JSON file prints a warning."""
    manager.load_from_json_file("non_existent.json")
    captured = capsys.readouterr()
    assert "Warning: Secret file non_existent.json not found." in captured.out
    assert manager.get_secret("ANY_KEY") is None


def test_load_from_json_file_malformed(
    manager: TinySecretManager, tmp_path: Path, capsys
):
    """Test loading from a malformed JSON file prints a warning."""
    secret_file = tmp_path / "malformed.json"
    secret_file.write_text("{'DB_HOST': 'localhost',")  # Malformed JSON

    manager.load_from_json_file(str(secret_file))
    captured = capsys.readouterr()
    assert "Warning: Could not decode JSON from" in captured.out
    assert manager.get_secret("DB_HOST") is None


def test_load_from_json_file_not_dict(
    manager: TinySecretManager, tmp_path: Path, capsys
):
    """Test loading from a JSON file that is not a dictionary."""
    secret_file = tmp_path / "not_dict.json"
    secret_file.write_text(json.dumps(["item1", "item2"]))  # JSON array, not object

    manager.load_from_json_file(str(secret_file))
    captured = capsys.readouterr()
    assert "Warning: JSON file" in captured.out
    assert "does not contain a dictionary root" in captured.out
    assert manager.get_secret("ANY_KEY") is None


def test_load_from_dotenv_file(manager: TinySecretManager, tmp_path: Path):
    """Test loading secrets from a .env style file."""
    dotenv_content = (
        "SERVICE_URL=http://example.com\n"
        "SERVICE_TOKEN=abcdef\n"
        "# This is a comment\n"
        "EMPTY_VAL=\n"
        "  SPACED_KEY  =  spaced_value  \n"
    )
    secret_file = tmp_path / ".env"
    secret_file.write_text(dotenv_content)

    manager.load_from_dotenv_file(str(secret_file))

    assert manager.get_secret("SERVICE_URL") == "http://example.com"
    assert manager.get_secret("SERVICE_TOKEN") == "abcdef"
    assert manager.get_secret("EMPTY_VAL") == ""
    assert manager.get_secret("SPACED_KEY") == "spaced_value"
    assert manager.get_secret("# This is a comment") is None


def test_load_from_dotenv_file_not_found(manager: TinySecretManager, capsys):
    """Test loading from a non-existent .env file prints a warning."""
    manager.load_from_dotenv_file("non_existent.env")
    captured = capsys.readouterr()
    assert "Warning: Secret file non_existent.env not found." in captured.out
    assert manager.get_secret("ANY_KEY") is None


def test_secret_override_order(
    manager: TinySecretManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test the order of precedence for loading/setting secrets."""
    # 1. Initial set
    manager.set_secret("MY_KEY", "initial_value")
    assert manager.get_secret("MY_KEY") == "initial_value"

    # 2. Load from .env file
    dotenv_content = "MY_KEY=dotenv_value\nOTHER_KEY=dotenv_other"
    env_file = tmp_path / ".env"
    env_file.write_text(dotenv_content)
    manager.load_from_dotenv_file(str(env_file))
    assert manager.get_secret("MY_KEY") == "dotenv_value"  # .env overrides initial set
    assert manager.get_secret("OTHER_KEY") == "dotenv_other"

    # 3. Load from JSON file
    json_data = {"MY_KEY": "json_value", "JSON_ONLY_KEY": "json_only"}
    json_file = tmp_path / "secrets.json"
    json_file.write_text(json.dumps(json_data))
    manager.load_from_json_file(str(json_file))
    assert manager.get_secret("MY_KEY") == "json_value"  # JSON overrides .env
    assert manager.get_secret("JSON_ONLY_KEY") == "json_only"

    # 4. Load from environment variables
    monkeypatch.setenv("APP_SECRET_MY_KEY", "env_value")
    manager.load_from_env(prefix="APP_SECRET_")
    assert manager.get_secret("MY_KEY") == "env_value"  # Env overrides JSON

    # 5. Final set_secret
    manager.set_secret("MY_KEY", "final_set_value")
    assert manager.get_secret("MY_KEY") == "final_set_value"  # set_secret overrides all
