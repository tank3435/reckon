from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://reckon:reckon@localhost:5432/reckon"

    # External API keys
    fred_api_key: str = ""
    world_bank_api_key: str = ""
    gdelt_api_key: str = ""
    geocoding_api_key: str = ""
    # Free token at https://metaculus.com/aib — required for Metaculus ingestion
    metaculus_api_token: str = ""

    # Tier weights (must sum to 1.0)
    tier_weight_economic: float = 0.20
    tier_weight_political: float = 0.25
    tier_weight_military: float = 0.25
    tier_weight_existential: float = 0.30

    # Scoring: z-score clamp range before mapping to 0–100
    zscore_clamp: float = 3.0


settings = Settings()
