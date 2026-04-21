import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # External API keys
    NASA_API_KEY: str = "DEMO_KEY"
    COPERNICUS_CLIENT_ID: str = ""
    COPERNICUS_CLIENT_SECRET: str = ""
    N2YO_API_KEY: str = ""
    
    # API settings
    API_TITLE: str = "AstroGeo API"
    API_VERSION: str = "1.0.0"
    
    # External API URLs
    ISS_API_BASE: str = "http://api.open-notify.org"
    NASA_API_BASE: str = "https://api.nasa.gov"
    WEATHER_API_BASE: str = "https://api.open-meteo.com/v1"

    # Database settings (Defaults mapped to Supabase for seamless remote deployment)
    DB_HOST: str = "db.auyojdmjmgviztctbdsp.supabase.co"
    DB_PORT: str = "5432"
    DB_NAME: str = "postgres"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "*EPB8FSbV+Lr!2Z"
    DB_SCHEMA: str = "astronomy"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    model_config = {
        "env_file": os.path.join(os.path.dirname(__file__), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

settings = Settings()