from datetime import datetime, timezone
import discord
from discord.ext import commands
from bot.config import Config
from bot import db

class Presence(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config):
        self.bot = bot
        self.config = config

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        # Ignorar bots para reduzir ruído
        if after.bot:
            return

        # Loga somente quando o status muda
        if before.status == after.status:
            return

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        status = str(after.status)  # online / idle / dnd / offline
        username = f"{after.name}#{after.discriminator}" if after.discriminator != "0" else after.name
        guild_id = after.guild.id if after.guild else 0

        try:
            db.log_presence(after.id, username, status, now_iso, guild_id)
        except Exception as e:
            print(f"[presence_log] erro: {e}")
