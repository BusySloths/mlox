import os
import json
import dacite
import base64
import string
import logging
import secrets
import importlib


from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from dataclasses import is_dataclass, fields  # Added fields import
from typing import List, Any, Dict


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


def dataclass_to_dict(obj: Any) -> Dict:
    if not is_dataclass(obj):
        raise TypeError("Object must be a dataclass instance")
    return _custom_asdict_recursive(obj)


def encrypt_dict(my_data: Dict, password: str) -> str:
    """Saves a dictionary to an encrypted JSON file."""
    json_string = json.dumps(my_data, indent=2)
    key = _get_encryption_key(password=password)
    fernet = Fernet(key)
    return fernet.encrypt(json_string.encode("utf-8")).decode("utf-8")


def decrypt_dict(data: str, password: str) -> Dict:
    # Decrypt the data
    key = _get_encryption_key(password=password)
    fernet = Fernet(key)
    json_string = fernet.decrypt(data).decode("utf-8")
    return json.loads(json_string)


def save_to_json(my_data: Dict, path: str, password: str, encrypt: bool = True) -> None:
    """Saves a dictionary to an encrypted JSON file."""
    json_string = json.dumps(my_data, indent=2)

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
    # print(f"====>> Loading data: {data_item}")
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
                config=dacite.Config(type_hooks={object: _load_hook}),
            )
        except (ImportError, AttributeError, TypeError) as e:
            logging.error(
                f"Hook Error resolving/instantiating {module_name}.{class_name}: {e}"
            )
            raise ValueError(
                f"Hook: Could not load nested dataclass {module_name}.{class_name}"
            ) from e
    logging.info(data_item)
    return data_item  # Let dacite handle if not a dict with metadata


def load_from_json(path: str, password: str, encrypted: bool = True) -> Any:
    # print(os.getcwd() + path)
    with open(os.getcwd() + path, "rb") as f:
        encrypted_data = f.read()
    if encrypted:
        # Decrypt the data
        key = _get_encryption_key(password=password)
        fernet = Fernet(key)
        json_string = fernet.decrypt(encrypted_data).decode("utf-8")
        data = json.loads(json_string)
    else:
        data = json.loads(encrypted_data)
    return data


def dict_to_dataclass(data: Dict, hooks: List[Any] | None = None) -> Any:
    module_name = data.pop("_module_name_", None)
    class_name = data.pop("_class_name_", None)
    if not module_name or not class_name:
        raise ValueError(
            "Data does not contain module and class names for deserialization."
        )

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
        raise ValueError("Could not load top-level dataclass") from e
    except Exception as e:  # Catch potential errors from the hook or dacite
        logging.error(f"Error during dacite processing: {e}")
        raise ValueError("Error during deserialization") from e


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
        password = password.replace(" ", "")  # Remove spaces if any
        password = password.replace("\\", "=")  # Remove escape characters if any
        password = password.replace('"', "+")  # Remove escape characters if any
        password = password.replace("'", "-")  # Remove escape characters if any
        password = password.replace("`", "]")  # Remove escape characters if any
        password = password.replace("^", "[")  # Remove escape characters if any
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and sum(c.isdigit() for c in password) >= 3
        ):
            break
    return password


def generate_username(user_prefix: str = "mlox") -> str:
    return f"{user_prefix}_{generate_password(5, with_punctuation=False)}"


def generate_pw(len: int = 20) -> str:
    return generate_password(length=len, with_punctuation=True)


def auto_map_ports(
    used_ports: List[int],
    requested_ports: Dict[str, int],
    ub: int = 65535,
    lb: int = 1024,
) -> Dict[str, int]:
    """
    Automatically assign ports to services in the bundle based on the provided port mapping.
    If a service's port is already set, it will not be changed.
    """
    assigned_ports = dict()
    for port_name, port in requested_ports.items():
        if port not in used_ports:
            assigned_ports[port_name] = port
            used_ports.append(port)
        else:
            searching = True
            probe = port
            while searching:
                if probe > ub:
                    logging.warning(
                        f"Port {port_name} ({port}) is already in use and no free port could be found."
                    )
                    searching = False
                    break
                if probe not in used_ports:
                    assigned_ports[port_name] = probe
                    used_ports.append(probe)
                    searching = False
                probe += 1
    if not len(assigned_ports) == len(requested_ports):
        logging.warning(
            "Not all requested ports could be assigned. Some ports are already in use."
        )
    return assigned_ports


if __name__ == "__main__":
    # Make sure your environment variable is set!
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    else:
        server_config_path = "./test_server copy.json"  # Or wherever your file is
        try:
            encrypt_existing_json_file(server_config_path, password=password)
            print(f"File '{server_config_path}' has been encrypted.")
        except Exception as e:
            print(f"Failed to encrypt file: {e}")
