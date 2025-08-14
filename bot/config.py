import os
from dataclasses import dataclass

@dataclass
class Config:
    token: str
    prefix: str = "!"
    database_file: str = "presence_data.db"
    leaderboard_limit: int = 10

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN não definido no .env / ambiente.")
        prefix = os.getenv("BOT_PREFIX", "!")
        database_file = os.getenv("DATABASE_FILE", "presence_data.db")
        leaderboard_limit = int(os.getenv("LEADERBOARD_LIMIT", "10"))
        return cls(
            token=token,
            prefix=prefix,
            database_file=database_file,
            leaderboard_limit=leaderboard_limit,
        )
