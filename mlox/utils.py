import importlib
import json
import logging
import os
import string
import secrets

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import dacite  # Changed import style
from abc import ABC
from dataclasses import is_dataclass, fields  # Added fields import
from typing import List, Any, Dict, TypeVar

from mlox.remote import exec_command


def _get_encryption_key(password: str) -> bytes:
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


def encrypt_existing_json_file(path: str, password: str) -> None:
    """Reads a plain-text JSON file, encrypts its content, and overwrites the file."""
    logging.info(f"Encrypting existing file: {path}")
    try:
        # Read the plain text content
        with open(path, "r", encoding="utf-8") as f:
            plain_text = f.read()

        # Encrypt the content
        key = _get_encryption_key(password)
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


def _custom_asdict_recursive(obj: Any) -> Any:
    """Recursively converts dataclass instances to dicts, adding class metadata."""
    if is_dataclass(obj):
        result = {}
        for f in fields(obj):
            value = _custom_asdict_recursive(getattr(obj, f.name))
            result[f.name] = value
        # Add metadata AFTER processing fields
        result["_module_name_"] = obj.__class__.__module__
        result["_class_name_"] = obj.__class__.__name__
        return result
    elif isinstance(obj, list):
        return [_custom_asdict_recursive(item) for item in obj]
    elif isinstance(obj, dict):
        # Assuming dict keys are simple types (str)
        return {k: _custom_asdict_recursive(v) for k, v in obj.items()}
    else:
        # Base types (int, str, bool, float, None, etc.)
        return obj


def save_dataclass_to_json(
    obj: Any, path: str, password: str, encrypt: bool = True
) -> None:
    """Saves a dataclass instance to an encrypted JSON file, including recursive class metadata."""
    if not is_dataclass(obj):
        raise TypeError("Object must be a dataclass instance")

    data = _custom_asdict_recursive(obj)
    json_string = json.dumps(data, indent=2)

    if encrypt:
        # Encrypt the JSON string
        key = _get_encryption_key(password=password)
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(json_string.encode("utf-8"))

        with open(path, "wb") as f:
            f.write(encrypted_data)
    else:
        # Save as plain text JSON
        with open(path, "w", encoding="utf-8") as f:
            f.write(json_string)


def _load_hook(data_item: Any) -> Any:
    """Dacite type hook to handle nested dataclasses with metadata."""
    print(f"====>> Loading data: {data_item}")
    if (
        isinstance(data_item, dict)
        and "_module_name_" in data_item
        and "_class_name_" in data_item
    ):
        module_name = data_item["_module_name_"]
        class_name = data_item["_class_name_"]
        try:
            module = importlib.import_module(module_name)
            nested_concrete_cls = getattr(module, class_name)
            # Create a copy without metadata for dacite processing
            data_copy = {
                k: v
                for k, v in data_item.items()
                if k not in ("_module_name_", "_class_name_")
            }
            # Recursively call from_dict for the nested object, passing the hook down
            return dacite.from_dict(
                data_class=nested_concrete_cls,
                data=data_copy,
                config=dacite.Config(
                    type_hooks={object: _load_hook}
                ),  # Pass hook recursively
            )
        except (ImportError, AttributeError, TypeError) as e:
            logging.error(
                f"Hook Error resolving/instantiating {module_name}.{class_name}: {e}"
            )
            raise ValueError(
                f"Hook: Could not load nested dataclass {module_name}.{class_name}"
            ) from e
    return data_item  # Let dacite handle if not a dict with metadata


def load_dataclass_from_json(
    path: str, password: str, encrypted: bool = True, hooks: List[Any] | None = None
) -> Any:
    """
    Loads a dataclass instance from an encrypted JSON file.
    Uses metadata (_module_name_, _class_name_) stored recursively in the JSON
    to determine the concrete classes to instantiate.
    """

    print(os.getcwd() + path)
    with open(os.getcwd() + path, "rb") as f:
        encrypted_data = f.read()

    if encrypted:
        # Decrypt the data
        key = _get_encryption_key(password=password)
        fernet = Fernet(key)
        json_string = fernet.decrypt(encrypted_data).decode("utf-8")
        print(f"Decrypted data: {json_string}")
        data = json.loads(json_string)
    else:
        data = json.loads(encrypted_data)

    module_name = data.pop("_module_name_", None)
    class_name = data.pop("_class_name_", None)
    if not module_name or not class_name:
        raise ValueError(f"Missing class metadata in top level of {path}")

    try:
        module = importlib.import_module(module_name)
        concrete_cls = getattr(module, class_name)

        # Use dacite with the dynamically determined top-level class and the hook for nested ones
        config = None
        if hooks:
            config = dacite.Config(type_hooks={h: _load_hook for h in hooks})

        return dacite.from_dict(data_class=concrete_cls, data=data, config=config)

    except (ImportError, AttributeError, TypeError) as e:
        logging.error(f"Error loading top-level class {module_name}.{class_name}: {e}")
        raise ValueError(
            f"Could not load dataclass from {path} due to class resolution error."
        ) from e
    except Exception as e:  # Catch potential errors from the hook or dacite
        logging.error(f"Error during dacite processing with hooks for {path}: {e}")
        raise


def generate_password(length: int = 10, with_punctuation: bool = False) -> str:
    """
    Generate a random password with at least 3 digits, 1 uppercase letter, and 1 lowercase letter.
    :param length: Length of the password
    :param with_punctuation: Include punctuation characters in the password
    :return: Generated password
    """
    if length < 5:
        raise ValueError("Password length must be at least 5 characters.")
    alphabet = string.ascii_letters + string.digits
    if with_punctuation:
        alphabet = alphabet + string.punctuation
    while True:
        password = "".join(secrets.choice(alphabet) for i in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and sum(c.isdigit() for c in password) >= 3
        ):
            break
    return password


if __name__ == "__main__":
    # Make sure your environment variable is set!
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    else:
        server_config_path = "./test_server.json"  # Or wherever your file is
        try:
            encrypt_existing_json_file(server_config_path, password=password)
            print(f"File '{server_config_path}' has been encrypted.")
        except Exception as e:
            print(f"Failed to encrypt file: {e}")
