"""Core services: SecretStore (encrypted local secrets)."""
from .secrets import SecretStore, SecretStoreError, get_secret_store

__all__ = ["SecretStore", "SecretStoreError", "get_secret_store"]
