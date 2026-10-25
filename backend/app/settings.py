"""Runtime settings and configuration for the Better Baseline service."""

import json
import os
from typing import Any, List
from pydantic import BaseModel, Field, field_validator


def parse_allowed_origins(value: Any = None) -> List[str]:
    """Parse allowed CORS origins from an env string, list, or fallback to defaults."""
    if value is None:
        raw = os.getenv("ALLOWED_ORIGINS")
    elif isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    elif isinstance(value, str):
        raw = value
    else:
        return [str(value).strip()]

    if not raw:
        return [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass

    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class Settings(BaseModel):
    app_name: str = "Better Baseline API"
    app_version: str = "0.1.0"
    model_version: str = "binary-v1"
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() in ("1", "true", "yes"))
    allowed_origins: List[str] = Field(default_factory=parse_allowed_origins)

    # Compute controls and resource ceilings
    max_mc_reps: int = Field(default_factory=lambda: int(os.getenv("MAX_MC_REPS", "100000")))
    max_grid_cells: int = Field(default_factory=lambda: int(os.getenv("MAX_GRID_CELLS", "5000")))
    max_enrolled_per_arm: int = Field(default_factory=lambda: int(os.getenv("MAX_ENROLLED_PER_ARM", "1000000")))
    max_concurrent_compute: int = Field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_COMPUTE", "4")))
    cache_size: int = Field(default_factory=lambda: int(os.getenv("CACHE_SIZE", "256")))
    max_body_bytes: int = Field(default_factory=lambda: int(os.getenv("MAX_BODY_BYTES", "1048576")))  # 1MB default

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def validate_allowed_origins(cls, v: Any) -> List[str]:
        return parse_allowed_origins(v)


settings = Settings()
