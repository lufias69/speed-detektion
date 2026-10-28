import json
import os
from base64 import urlsafe_b64encode, urlsafe_b64decode
from dataclasses import asdict

from cryptography.fernet import Fernet

from config import Config, load_config


SENSITIVE_KEYS = ("firebase_api_key",)


def _get_or_create_key():
    """Load or create an encryption key stored in a simple key file."""
    key_path = "config.key"
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass
    return key


def encrypt_config(config: Config) -> dict:
    """Encrypt sensitive fields before saving config.json."""
    fernet = Fernet(_get_or_create_key())
    data = config.__dict__.copy()
    for key in SENSITIVE_KEYS:
        value = data.get(key)
        if value:
            data[key] = urlsafe_b64encode(fernet.encrypt(value.encode())).decode()
    return data


def decrypt_config(path: str = "config.json") -> Config:
    """Load config.json and decrypt sensitive fields."""
    config = load_config(path)
    fernet = Fernet(_get_or_create_key())
    for key in SENSITIVE_KEYS:
        value = getattr(config, key)
        if value:
            try:
                raw = urlsafe_b64decode(value.encode())
                setattr(config, key, fernet.decrypt(raw).decode())
            except Exception:
                # Likely already plaintext; keep as-is.
                pass
    return config


def save_encrypted_config(config: Config, path: str = "config.json"):
    """Save config with sensitive fields encrypted."""
    data = encrypt_config(config)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
