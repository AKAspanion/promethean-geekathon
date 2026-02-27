from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_username: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "supply_chain"
    database_url: str | None = None

    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None

    weather_api_key: str | None = None
    weather_days_forecast: int = 3
    news_api_key: str | None = None

    # Trend insights agent
    trend_agent_enabled: bool = False
    trend_agent_interval_minutes: int = 60

    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    port: int = 8000
    env: str = "development"
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "extra": "ignore", "env_file_encoding": "utf-8"}

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
