from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    llm_base_url: str = "https://apim-rakathon-q7146n.azure-api.net/openai/v1/"
    llm_api_key: str = ""
    llm_model: str = "gpt-6-luna-dz-eu"  # ~2x faster than gpt-6-1-sol-dz-eu with the same results on synthetic data
    llm_mode: str = "mock"  # mock | live
    llm_reasoning_effort: str = "low"  # low | medium | high | "" (model default); low keeps extraction fast
    # Embeddings run locally (no embedding deployment on the gateway; clinical text stays on the machine).
    embedding_backend: str = "local"  # local | gateway
    local_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_model: str = ""  # gateway deployment name, only for embedding_backend=gateway
    embedding_dim: int = 384  # must match the model and the VECTOR columns in IRIS

    fhir_base_url: str = "http://localhost:52773/fhir/r4/"
    iris_host: str = "localhost"
    iris_port: int = 1972
    iris_namespace: str = "FHIRSERVER"
    iris_user: str = "SuperUser"
    iris_password: str = "SYS"

    mkn10_csv: str = ""
    reporting_facility: str = "00843989000000 - Fakultní nemocnice Ostrava"  # NOR "Zařízení (pracoviště)"
    reporting_department: str = ""  # NOR "Oddělení" (číselník NOR), e.g. "20 - Chirurgie"
    auto_accept_threshold: int = 85  # fields at/above this score without conflict skip review
    data_dir: Path = REPO_ROOT / "backend" / "var"


@lru_cache
def get_settings() -> Settings:
    return Settings()
