from datetime import datetime, timedelta, timezone
from typing import Optional
import discord
from discord.ext import commands
from bot.config import Config
from bot import db

LABEL_PT = {
    "online":  "ONLINE",
    "idle":    "AUSENTE",
    "dnd":     "NÃO PERTURBE",
    "offline": "OFFLINE",
}

class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config):
        self.bot = bot
        self.config = config

    @commands.command(name="status_servidor", aliases=["online_agora","contagem_agora"])
    async def status_servidor(self, ctx: commands.Context):
        """Mostra contagem AO VIVO de status no servidor (ignora bots)."""
        # Garante cache atualizado de membros E presenças
        try:
            await ctx.guild.chunk(cache=True)
        except Exception as e:
            print(f"[status_servidor] chunk falhou: {e}")

        counts = {"online": 0, "idle": 0, "dnd": 0, "offline": 0}
        for m in ctx.guild.members:  # usa o CACHE do gateway
            if m.bot:
                continue
            key = str(m.status)  # agora reflete a presença real
            if key in counts:
                counts[key] += 1

        label = {"online": "ONLINE", "idle": "AUSENTE", "dnd": "NÃO PERTURBE", "offline": "OFFLINE"}
        msg = [
            f"**Status agora — {ctx.guild.name}**",
            f"- {label['online']}: {counts['online']}",
            f"- {label['idle']}: {counts['idle']}",
            f"- {label['dnd']}: {counts['dnd']}",
            f"- {label['offline']}: {counts['offline']}",
            "_Obs.: OFFLINE inclui quem está Invisível._"
        ]
        await ctx.reply("\n".join(msg))


    @commands.command(name="status_now")
    async def status_now(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        member = member or ctx.author
        key = str(member.status)
        label = LABEL_PT.get(key, key.upper())
        await ctx.reply(f"Status atual de **{member.display_name}**: **{label}**")

    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx: commands.Context, days: Optional[int] = 7):
        try:
            days = int(days)
        except Exception:
            days = 7
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        limit = self.config.leaderboard_limit
        rows = db.fetch_all(
            "SELECT user_id, MAX(username) AS uname, COUNT(*) AS c "
            "FROM presence_log WHERE guild_id = ? AND timestamp >= ? "
            "GROUP BY user_id ORDER BY c DESC LIMIT ?",
            (ctx.guild.id, since, limit)
        )
        if not rows:
            await ctx.reply("Sem dados suficientes nesse período.")
            return
        linhas = [f"**Top {len(rows)} (últimos {days} dias):**"]
        for i, (uid, uname, c) in enumerate(rows, start=1):
            linhas.append(f"{i}. `{uname}` — {c} mudanças de status")
        await ctx.reply("\n".join(linhas))

    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context, member: Optional[discord.Member] = None, days: Optional[int] = 7):
        member = member or ctx.author
        try:
            days = int(days)
        except Exception:
            days = 7
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        rows = db.fetch_all(
            "SELECT status, COUNT(*) FROM presence_log "
            "WHERE guild_id = ? AND user_id = ? AND timestamp >= ? "
            "GROUP BY status",
            (ctx.guild.id, member.id, since)
        )
        if not rows:
            await ctx.reply(f"Sem dados para {member.display_name} nos últimos {days} dias.")
            return
        counts = {k.lower(): v for k, v in rows}
        order = ["online","idle","dnd","offline"]
        linhas = [f"**{member.display_name} — últimos {days} dias**"]
        for k in order:
            linhas.append(f"- {LABEL_PT[k]}: {counts.get(k, 0)}")
        await ctx.reply("\n".join(linhas))
