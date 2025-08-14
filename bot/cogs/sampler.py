from __future__ import annotations
from datetime import datetime, timezone
import os
import discord
from discord.ext import commands, tasks
from bot.config import Config
from bot import db

# Periodicidade (segundos) configurável pelo .env
SAMPLE_EVERY = int(os.getenv("SAMPLE_EVERY_SECONDS", "60"))  # 60s = 1 min

class Sampler(commands.Cog):
    """
    Amostra o status de TODOS os membros de TODOS os servidores onde o bot está,
    em intervalos regulares, gravando no presence_log.
    Isso garante dados mesmo sem 'mudanças de status'.
    """

    def __init__(self, bot: commands.Bot, config: Config):
        self.bot = bot
        self.config = config
        # começa a amostrar quando o bot estiver pronto
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    @tasks.loop(seconds=SAMPLE_EVERY)
    async def poll_loop(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        for guild in list(self.bot.guilds):
            try:
                # garante que o cache tem TODOS os membros e suas presenças
                try:
                    await guild.chunk(cache=True)
                except Exception as e:
                    print(f"[sampler] chunk {guild.id} falhou: {e}")

                for m in guild.members:
                    if m.bot:
                        continue
                    status = str(m.status)  # refletirá online/idle/dnd/offline de verdade
                    username = f"{m.name}#{m.discriminator}" if m.discriminator != "0" else m.name
                    try:
                        db.log_presence(m.id, username, status, now, guild.id)
                    except Exception as e:
                        print(f"[sampler] erro ao gravar {guild.id}/{m.id}: {e}")
            except Exception as e:
                print(f"[sampler] erro no guild {guild.id}: {e}")

    @poll_loop.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()
        print(f"[sampler] loop iniciado (cada {SAMPLE_EVERY}s)")
