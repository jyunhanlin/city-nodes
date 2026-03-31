from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_service_account_key: str = ""
    github_token: str = ""
    github_repository: str = ""
    anthropic_api_key: str = ""
    google_places_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
