from datetime import datetime, timedelta, timezone
import io, csv
from typing import Optional, List
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

class Reports(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config):
        self.bot = bot
        self.config = config

    @commands.command(name="export_csv")
    async def export_csv(self, ctx: commands.Context, days: Optional[int] = 7):
        """Exporta CSV com contagem por status por usuário no período (padrão: 7 dias)."""
        try:
            days = int(days)
        except Exception:
            days = 7

        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        rows = db.fetch_all(
            "SELECT user_id, MAX(username) AS uname, "
            "SUM(CASE WHEN status='online'  THEN 1 ELSE 0 END) AS online, "
            "SUM(CASE WHEN status='idle'    THEN 1 ELSE 0 END) AS idle, "
            "SUM(CASE WHEN status='dnd'     THEN 1 ELSE 0 END) AS dnd, "
            "SUM(CASE WHEN status='offline' THEN 1 ELSE 0 END) AS offline, "
            "COUNT(*) AS total "
            "FROM presence_log WHERE guild_id = ? AND timestamp >= ? "
            "GROUP BY user_id ORDER BY total DESC",
            (ctx.guild.id, since)
        )

        if not rows:
            await ctx.reply(f"Sem dados nos últimos {days} dias.")
            return

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["user_id", "username", "ONLINE", "AUSENTE", "NÃO PERTURBE", "OFFLINE", "TOTAL"])
        for user_id, uname, online, idle, dnd, offline, total in rows:
            writer.writerow([user_id, uname, online, idle, dnd, offline, total])

        data = buf.getvalue().encode("utf-8-sig")  # BOM p/ Excel
        filename = f"presence_report_{days}d_g{ctx.guild.id}.csv"
        await ctx.reply(
            content=f"Export dos últimos **{days}** dias.",
            file=discord.File(io.BytesIO(data), filename=filename)
        )

    @commands.command(name="report")
    async def report(self, ctx: commands.Context, days: Optional[int] = 7):
        """Resumo em texto: Top usuários + totais por status (padrão: 7 dias)."""
        try:
            days = int(days)
        except Exception:
            days = 7
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        # totais do servidor por status
        totals = dict(db.fetch_all(
            "SELECT status, COUNT(*) FROM presence_log "
            "WHERE guild_id = ? AND timestamp >= ? GROUP BY status",
            (ctx.guild.id, since)
        ))
        def t(k): return totals.get(k, 0)
        header = (f"**Resumo — últimos {days} dias**\n"
                  f"- {LABEL_PT['online']}: {t('online')}\n"
                  f"- {LABEL_PT['idle']}: {t('idle')}\n"
                  f"- {LABEL_PT['dnd']}: {t('dnd')}\n"
                  f"- {LABEL_PT['offline']}: {t('offline')}\n")

        # top usuários
        top = db.fetch_all(
            "SELECT MAX(username) AS uname, COUNT(*) AS total "
            "FROM presence_log WHERE guild_id = ? AND timestamp >= ? "
            "GROUP BY user_id ORDER BY total DESC LIMIT 10",
            (ctx.guild.id, since)
        )
        if top:
            lines = [header, f"\n**Top {len(top)} usuários:**"]
            for i, (uname, total) in enumerate(top, start=1):
                lines.append(f"{i}. `{uname}` — {total} mudanças de status")
            await ctx.reply("\n".join(lines))
        else:
            await ctx.reply(header)

    @commands.command(name="snapshot")
    @commands.has_permissions(administrator=True)
    async def snapshot(self, ctx: commands.Context):
        """Grava o status ATUAL de todos os membros (admin). Útil para criar baseline."""
        members: List[discord.Member] = []
        try:
            async for m in ctx.guild.fetch_members(limit=None):
                members.append(m)
        except Exception:
            members = list(ctx.guild.members)  # fallback no cache

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0
        for m in members:
            if m.bot:
                continue
            status = str(m.status)
            username = f"{m.name}#{m.discriminator}" if m.discriminator != "0" else m.name
            try:
                db.log_presence(m.id, username, status, now, ctx.guild.id)
                inserted += 1
            except Exception as e:
                print(f"[snapshot] erro: {e}")

        await ctx.reply(f"Snapshot registrado: **{inserted}** membros.")
