from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_model: str = "qwen2.5:3b"
    ollama_base_url: str = "http://localhost:11434"
    # 180 s, bo PIERWSZE zadanie po starcie trwa ~60 s: Ollama cache'uje
    # prefiks promptu, wiec pierwsze przetwarza caly prompt systemowy
    # (~830 tokenow) z predkoscia ~20 tok/s. Kolejne ~12 s.
    llm_timeout_seconds: int = Field(default=180, gt=0)

    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    mail_from: str = "mail-sorter@example.com"

    classify_head_chars: int = Field(default=2000, ge=1)
    agent_max_steps: int = Field(default=3, ge=1)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
