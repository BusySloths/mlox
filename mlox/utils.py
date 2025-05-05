import importlib
import json
import logging
import os

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from dacite import from_dict
from dataclasses import asdict, is_dataclass
from typing import List, Any

from mlox.remote import exec_command


# --- Encryption Helpers ---
def _get_encryption_key() -> bytes:
    """Derives the encryption key from an environment variable."""
    password = os.environ.get("MLOX_CONFIG_PASSWORD")
    if not password:
        raise ValueError(
            "MLOX_CONFIG_PASSWORD environment variable not set for encryption/decryption."
        )

    # Use a fixed salt or store/derive it securely if needed. For simplicity, using a fixed one here.
    # WARNING: Using a fixed salt is less secure than a unique one per encryption.
    # Consider storing a unique salt alongside the encrypted data if enhancing security later.
    salt = (
        b"mlox_fixed_salt_#s0m3th1ng_"  # Replace with something unique to your project
    )
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # Fernet keys must be 32 url-safe base64-encoded bytes
        salt=salt,
        iterations=480000,  # NIST recommendation for PBKDF2-HMAC-SHA256
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key


def encrypt_existing_json_file(path: str) -> None:
    """Reads a plain-text JSON file, encrypts its content, and overwrites the file."""
    logging.info(f"Encrypting existing file: {path}")
    try:
        # Read the plain text content
        with open(path, "r", encoding="utf-8") as f:
            plain_text = f.read()

        # Encrypt the content
        key = _get_encryption_key()
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(plain_text.encode("utf-8"))

        # Overwrite the file with encrypted data
        with open(path, "wb") as f:
            f.write(encrypted_data)
        logging.info(f"Successfully encrypted and overwrote {path}")
    except FileNotFoundError:
        logging.error(f"Error: File not found at {path}")
    except Exception as e:
        logging.error(f"An error occurred during encryption of {path}: {e}")
        raise  # Re-raise the exception after logging


def execute_command(conn, cmd: List | str):
    if isinstance(cmd, str):
        # Type 1: single CMD executed as sudo
        exec_command(conn, cmd, sudo=True)
    if isinstance(cmd, list):
        if isinstance(cmd[0], bool):
            # Type 2: [Sudo True/False, CMD, Descr]
            exec_command(conn, cmd[1], sudo=cmd[0])
        else:
            # Type 3: Function call with arguments
            func_name = cmd[0]
            module_name = "mlox.remote"
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
            args = cmd[1:]
            print(f"Execute CMD: {func_name} with args: {args}")
            if args:
                func(conn, *args)
            else:
                func(conn)


def save_dataclass_to_json(obj: Any, path: str) -> None:
    """Saves a dataclass instance to a JSON file, including its class information."""
    """Encrypts the JSON content before saving."""
    if not is_dataclass(obj):
        raise TypeError("Object must be a dataclass instance")

    data = asdict(obj)
    # Add class metadata
    data["_module_name_"] = obj.__class__.__module__
    data["_class_name_"] = obj.__class__.__name__

    json_string = json.dumps(data, indent=2)

    # Encrypt the JSON string
    key = _get_encryption_key()
    fernet = Fernet(key)
    encrypted_data = fernet.encrypt(json_string.encode("utf-8"))

    with open(path, "w") as f:
        f.write(encrypted_data)


def load_dataclass_from_json(path: str) -> Any:
    """
    Loads a dataclass instance from a JSON file.
    Uses metadata (_module_name_, _class_name_) stored in the JSON
    to determine the concrete class to instantiate, ensuring it's a subclass
    of the provided base_cls.
    """
    """Decrypts the file content before parsing JSON."""

    print(os.getcwd() + path)
    with open(os.getcwd() + path, "rb") as f:
        encrypted_data = f.read()

    # Decrypt the data
    key = _get_encryption_key()
    fernet = Fernet(key)
    json_string = fernet.decrypt(encrypted_data).decode("utf-8")
    data = json.loads(json_string)

    module_name = data.pop("_module_name_", None)
    class_name = data.pop("_class_name_", None)

    try:
        module = importlib.import_module(module_name)
        concrete_cls = getattr(module, class_name)

        # Use dacite with the dynamically determined concrete class
        # Pass the remaining data (without the metadata keys)
        return from_dict(
            data_class=concrete_cls, data=data
        )  # Add config=Config(...) if needed

    except (ImportError, AttributeError, TypeError) as e:
        logging.error(f"Error loading concrete class {module_name}.{class_name}: {e}")
        # Fallback or re-raise depending on desired behavior
        raise ValueError(
            f"Could not load dataclass from {path} due to class resolution error."
        ) from e


if __name__ == "__main__":
    # Make sure your environment variable is set!
    if not os.environ.get("MLOX_CONFIG_PASSWORD"):
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    else:
        server_config_path = "./test_server.json"  # Or wherever your file is
        try:
            encrypt_existing_json_file(server_config_path)
            print(f"File '{server_config_path}' has been encrypted.")
        except Exception as e:
            print(f"Failed to encrypt file: {e}")
