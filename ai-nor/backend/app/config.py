from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    llm_base_url: str = "https://apim-rakathon-q7146n.azure-api.net/openai/v1/"
    llm_api_key: str = ""
    llm_model: str = "gpt-6-1-sol-dz-eu"
    llm_mode: str = "mock"  # mock | live
    embedding_model: str = ""
    embedding_dim: int = 1536

    fhir_base_url: str = "http://localhost:52773/fhir/r4/"
    iris_host: str = "localhost"
    iris_port: int = 1972
    iris_namespace: str = "FHIRSERVER"
    iris_user: str = "SuperUser"
    iris_password: str = "SYS"

    mkn10_csv: str = ""
    data_dir: Path = REPO_ROOT / "backend" / "var"


@lru_cache
def get_settings() -> Settings:
    return Settings()
