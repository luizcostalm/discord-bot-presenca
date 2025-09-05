from datetime import datetime, timezone
import discord
from discord.ext import commands
from bot.config import Config
from bot import db

class Presence(commands.Cog):
    # Dicionário para rastrear última atividade dos usuários
    last_activity = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        # Atualiza última atividade para o usuário
        self.last_activity[message.author.id] = datetime.now(timezone.utc)

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

        # Detecta idle manual: se mudou para idle e teve atividade recente (<1min)
        if status == "idle":
            last = self.last_activity.get(after.id)
            now = datetime.now(timezone.utc)
            manual = False
            if last and (now - last).total_seconds() < 60:
                manual = True
            # Salva info extra no banco (opcional: pode criar nova coluna ou logar em arquivo)
            try:
                db.log_presence(after.id, username, status + ("_manual" if manual else ""), now_iso, guild_id)
            except Exception as e:
                print(f"[presence_log] erro: {e}")
            return

        try:
            db.log_presence(after.id, username, status, now_iso, guild_id)
        except Exception as e:
            print(f"[presence_log] erro: {e}")

