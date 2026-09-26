"""Environment-only settings. Startup fails closed outside explicit local DEV_MODE."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    bot_token: str = ''
    webhook_secret: str = ''
    public_base_url: str = ''
    database_url: str = ''
    dev_mode: bool = False
    port: int = 8000
    log_level: str = 'INFO'

    def validate_production(self) -> None:
        if self.dev_mode:
            return
        if not self.bot_token or not self.webhook_secret or not self.public_base_url.startswith('https://'):
            raise RuntimeError('Production requires BOT_TOKEN, WEBHOOK_SECRET and HTTPS PUBLIC_BASE_URL')
        if not self.database_url.startswith(('postgresql://', 'postgresql+psycopg://')):
            raise RuntimeError('Production requires PostgreSQL DATABASE_URL')
        if len(self.webhook_secret) < 16 or not self.webhook_secret.replace('_', '').replace('-', '').isalnum():
            raise RuntimeError('WEBHOOK_SECRET must be >=16 chars, ASCII letters/digits/_/-')


@lru_cache
def get_settings() -> Settings:
    return Settings()
