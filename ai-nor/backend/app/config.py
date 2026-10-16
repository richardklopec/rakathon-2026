from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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

    # MKN-10 CSV from ÚZIS; relative paths are resolved against the ai-nor folder (data lives next to the repo)
    mkn10_csv: str = "../../Rakathon_DATA_NOR/Rakathon_DATA_NOR/mkn-10-strukturovane-podklady-20260101/mkn10_strukturovane_podklady_20260101/cp_utf8/01_MKN10_5E_2026_utf8.csv"
    # ÚZIS MKN-10 package (CSV in UTF-8 or Windows-1250) for the form's code lists; searched before the MKN10_CSV folder
    codelists_dir: str = "uploads"
    # MKN-10 Tabelární část (PDF, ÚZIS 2014): coding rules for the second LLM step (app/retrieval/rules.py)
    mkn10_rules_pdf: str = "../../Rakathon_DATA_NOR/Rakathon_DATA_NOR/mkn-tabelarni-cast_1-4-2014_2.pdf"
    reporting_facility: str = "00843989000000 - Fakultní nemocnice Ostrava"  # NOR "Zařízení (pracoviště)"
    reporting_department: str = ""  # NOR "Oddělení" (číselník NOR), e.g. "20 - Chirurgie"
    auto_accept_threshold: int = 85  # fields at/above this score without conflict skip review
    data_dir: Path = REPO_ROOT / "backend" / "var"
    llm_cache_dir: str = ""  # empty = data_dir/llm-cache; scripts.evaluate points it elsewhere for runs without cache
    # gold (reference) values for scripts.evaluate; FNO patients are never in the repo (AGENTS.md)
    eval_gold_dir: str = "../../Rakathon_DATA_NOR/gold"


    @field_validator("mkn10_csv", "codelists_dir", "mkn10_rules_pdf", "llm_cache_dir", "eval_gold_dir", "data_dir", mode="after")
    @classmethod
    def _relative_to_repo(cls, v):
        """Relative paths in .env work on any machine: resolve them against the ai-nor folder."""
        if not v:
            return v
        path = Path(v)
        resolved = path if path.is_absolute() else (REPO_ROOT / path).resolve()
        return str(resolved) if isinstance(v, str) else resolved


@lru_cache
def get_settings() -> Settings:
    return Settings()
