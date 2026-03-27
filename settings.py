from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_service_account_key: str
    github_token: str = ""
    github_repository: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
