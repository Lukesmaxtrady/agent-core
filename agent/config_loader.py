# agent/config_loader.py

import os
import yaml
import logging
from pathlib import Path

class ConfigLoader:
    _config = None

    @classmethod
    def load_config(cls, config_path: str = None):
        if cls._config is not None:
            return cls._config

        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"

        if not Path(config_path).exists():
            logging.error(f"Config file not found: {config_path}")
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Override with environment variables if present (env vars take priority)
        env_overrides = {
            "openai_api_key": os.getenv("OPENAI_API_KEY"),
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        }
        for key, val in env_overrides.items():
            if val:
                config[key] = val

        # Fail-fast checks for critical keys
        missing = []
        if not config.get("openai_api_key"):
            missing.append("OPENAI_API_KEY")
        # Add any more required env vars here if needed

        if missing:
            error_msg = f"Missing required configuration or environment variables: {', '.join(missing)}"
            logging.error(error_msg)
            raise EnvironmentError(error_msg)

        cls._config = config
        logging.info("Configuration loaded successfully.")
        return cls._config

    @classmethod
    def get(cls, key: str, default=None):
        if cls._config is None:
            cls.load_config()
        return cls._config.get(key, default)

    @classmethod
    def get_path(cls, *path_parts, default=None):
        """
        Returns a resolved absolute Path from config base_dir plus path_parts.
        Example: get_path('logs_dir', 'agent_backups')
        """
        config = cls.load_config()
        base_dir = Path(config.get("paths", {}).get("base_dir", ".")).resolve()
        parts = []
        for part in path_parts:
            if isinstance(part, str):
                # If the part is a config key for a path, get its value
                val = config.get("paths", {}).get(part, None)
                if val:
                    parts.append(val)
                else:
                    parts.append(part)
            else:
                parts.append(str(part))
        full_path = base_dir.joinpath(*parts).resolve()
        return full_path

