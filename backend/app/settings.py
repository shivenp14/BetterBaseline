"""Runtime settings and configuration for the Better Baseline service."""

import os
from typing import List
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "Better Baseline API"
    app_version: str = "0.1.0"
    model_version: str = "binary-v1"
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() in ("1", "true", "yes"))
    allowed_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )


settings = Settings()
