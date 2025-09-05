import os
import asyncio
import discord
from discord.ext import commands
from discord.ext.commands import when_mentioned_or
from dotenv import load_dotenv

load_dotenv()

from bot.config import Config
from bot import db

# cogs
from bot.cogs.sampler import Sampler
from bot.cogs.workcheck import WorkCheck
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

    member_cache_flags = discord.MemberCacheFlags.all()

    bot = commands.Bot(
        command_prefix=when_mentioned_or(config.prefix),  # aceita "!" e @BotStatus
        intents=intents,
        member_cache_flags=member_cache_flags,
        chunk_guilds_at_startup=True,
    )


    @bot.event
    async def on_ready():
        print(f"✅ Logado como {bot.user} (id: {bot.user.id})")
        print(f"Prefixo: {config.prefix} | DB: {config.database_file}")

        # garante membros no cache (bom para presença)
        for g in bot.guilds:
            try:
                await g.chunk(cache=True)
            except Exception as e:
                print(f"[on_ready] chunk {g.id} falhou: {e}")

        # status do bot
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="presenças no servidor",
            ),
            status=discord.Status.online,
        )

        # mostra canais liberados encontrados
        allowed = {
            int(x) for x in os.getenv("ALLOWED_CHANNELS", "").split(",")
            if x.strip().isdigit()
        }
        print("ALLOWED_CHANNELS ->", allowed)
        for g in bot.guilds:
            hit  = [cid for cid in allowed if g.get_channel(cid)]
            miss = [cid for cid in allowed if not g.get_channel(cid)]
            print(f"- {g.name} ({g.id}) | canais OK: {hit} | NÃO ENCONTRADOS: {miss}")

    # DEBUG: loga tudo que o bot enxerga e erros de comando
    @bot.event
    async def on_message(message: discord.Message):
        where = f"{message.guild.name if message.guild else 'DM'} | #{getattr(message.channel,'name','?')} ({message.channel.id})"
        print(f"[msg] {where} :: {message.author} -> {message.content!r}")
        await bot.process_commands(message)

    @bot.event
    async def on_command_error(ctx, error):
        print("[cmd-err]", type(error).__name__, error)
        try:
            await ctx.reply(f"❌ {type(error).__name__}: {error}")
        except Exception:
            pass

    return bot


async def amain():
    config = Config.from_env()
    db.init_db(config.database_file)

    bot = build_bot(config)

    # add_cog: na sua versão do discord.py provavelmente é **async** → use await
    await bot.add_cog(Basic(bot, config))
    await bot.add_cog(Presence(bot, config))
    await bot.add_cog(Stats(bot, config))
    await bot.add_cog(Duration(bot, config))
    await bot.add_cog(Reports(bot, config))
    await bot.add_cog(WorkCheck(bot, config))
    await bot.add_cog(Sampler(bot, config))

    await bot.start(config.token)


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        print("\nEncerrando...")
