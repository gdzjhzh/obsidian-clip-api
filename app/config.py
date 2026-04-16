import os
from typing import Any, Dict

import yaml


class Config:
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self):
        config_path = os.getenv("CONFIG_PATH", "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """Get nested config values using dot-separated keys."""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

    @property
    def couchdb_url(self) -> str:
        return self.get("couchdb.url")

    @property
    def couchdb_db_name(self) -> str:
        return self.get("couchdb.db_name")

    @property
    def work_wechat_enabled(self) -> bool:
        return self.get("work_wechat.enabled", False)

    @property
    def work_wechat_webhook_url(self) -> str:
        return self.get("work_wechat.webhook_url", "")

    @property
    def work_wechat_at_all(self) -> bool:
        return self.get("work_wechat.at_all", False)

    @property
    def picgo_server(self) -> str:
        return self.get("picgo.server")

    @property
    def picgo_upload_path(self) -> str:
        return self.get("picgo.upload_path")

    @property
    def picgo_local_path_prefix(self) -> str:
        return self.get("picgo.local_path_prefix", "")

    @property
    def picgo_local_use_wikilink(self) -> bool:
        return self.get("picgo.local_use_wikilink", False)

    @property
    def debug(self) -> bool:
        return self.get("debug", False)

    @property
    def storage_method(self) -> str:
        return self.get("storage.method", "rest_api")

    @property
    def obsidian_api_url(self) -> str:
        return self.get("obsidian_api.url", "http://127.0.0.1:27123")

    @property
    def obsidian_api_key(self) -> str:
        return self.get("obsidian_api.api_key")

    @property
    def obsidian_api_timeout(self) -> int:
        return self.get("obsidian_api.timeout", 30)

    @property
    def obsidian_api_retry_count(self) -> int:
        return self.get("obsidian_api.retry_count", 3)

    @property
    def obsidian_api_retry_delay(self) -> int:
        return self.get("obsidian_api.retry_delay", 1)

    @property
    def obsidian_api_verify_ssl(self) -> bool:
        return self.get("obsidian_api.verify_ssl", True)

    @property
    def obsidian_clippings_path(self) -> str:
        return self.get("obsidian.clippings_path", "Clippings")

    @property
    def obsidian_date_folder(self) -> bool:
        return self.get("obsidian.date_folder", True)

    @property
    def llm_enabled(self) -> bool:
        return self.get("llm.enabled", True)

    @property
    def llm_url(self) -> str:
        return self.get("llm.url", "")

    @property
    def llm_api_key(self) -> str:
        return self.get("llm.api_key", "")

    @property
    def llm_timeout(self) -> int:
        return self.get("llm.timeout", 300)

    @property
    def llm_retry_count(self) -> int:
        return self.get("llm.retry_count", 2)

    @property
    def llm_retry_delay(self) -> int:
        return self.get("llm.retry_delay", 2)

    @property
    def llm_language(self) -> str:
        return self.get("llm.language", "auto")

    @property
    def content_fetcher_method(self) -> str:
        return self.get("content_fetcher.method", "builtin")

    @property
    def content_fetcher_fallback(self) -> bool:
        return self.get("content_fetcher.fallback", True)

    @property
    def content_fetcher_external_url(self) -> str:
        return self.get("content_fetcher.external.url", "")

    @property
    def log_level(self) -> str:
        return self.get("logging.level", "INFO")

    @property
    def log_colorize(self) -> bool:
        return self.get("logging.colorize", True)

    @property
    def log_rotation(self) -> str:
        return self.get("logging.rotation", "10 MB")

    @property
    def log_retention(self) -> str:
        return self.get("logging.retention", "30 days")

    @property
    def log_compression(self) -> str:
        return self.get("logging.compression", "zip")


config = Config()
