import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv()  # carrega .env da pasta atual

from bot.config import Config
from bot import db

# importe NORMAL dos cogs (nada de await aqui)
from bot.cogs.sampler import Sampler        # <- sampler (com L), import absoluto
from bot.cogs.workcheck import WorkCheck    # <- nome da classe com C maiúsculo
from bot.cogs.duration import Duration
from bot.cogs.reports import Reports
from bot.cogs.basic import Basic
from bot.cogs.presence import Presence
from bot.cogs.stats import Stats


def build_bot(config: Config) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.presences = True

    # 💡 cache de membros/presenças + chunk no startup
    member_cache_flags = discord.MemberCacheFlags.all()
    bot = commands.Bot(
        command_prefix=config.prefix,
        intents=intents,
        member_cache_flags=member_cache_flags,
        chunk_guilds_at_startup=True,
    )

    @bot.event
    async def on_ready():
        print(f"✅ Logado como {bot.user} (id: {bot.user.id})")
        print(f"Prefixo: {config.prefix} | DB: {config.database_file}")

        # Garanta que todos os guilds foram chunkados ao subir
        for g in bot.guilds:
            try:
                await g.chunk(cache=True)
            except Exception as e:
                print(f"[on_ready] chunk {g.id} falhou: {e}")

        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching,
                                      name="presenças no servidor"),
            status=discord.Status.online
        )
    return bot


async def amain():
    config = Config.from_env()
    db.init_db(config.database_file)

    bot = build_bot(config)

    # add_cog é SÍNCRONO no discord.py — não use await aqui
    await bot.add_cog(Basic(bot, config))
    await bot.add_cog(Presence(bot, config))
    await bot.add_cog(Stats(bot, config))
    await bot.add_cog(Reports(bot, config))
    await bot.add_cog(Duration(bot, config))
    await bot.add_cog(WorkCheck(bot, config))
    await bot.add_cog(Sampler(bot, config))

    await bot.start(config.token)


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        print("\nEncerrando...")
