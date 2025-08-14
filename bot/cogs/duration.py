from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
import os

import discord
from discord.ext import commands
from bot.config import Config
from bot import db

# ---- Config via .env (com defaults) -----------------------------------------
# Fuso padrão: America/Sao_Paulo. Em Windows, pode ser preciso `pip install tzdata`.
WORK_TZ = os.getenv("WORK_TZ", "America/Sao_Paulo")
WORK_DAYS = os.getenv("WORK_DAYS", "0,1,2,3,4")  # 0=segunda ... 6=domingo
WORK_START = os.getenv("WORK_START", "08:00")
WORK_END = os.getenv("WORK_END", "18:00")

# Mapas de rótulos
LABEL_PT = {
    "online":  "ONLINE",
    "idle":    "AUSENTE",
    "dnd":     "NÃO PERTURBE",
    "offline": "OFFLINE",
}
NORMALIZE_STATUS = {
    "online": "online", "on": "online",
    "idle": "idle", "ausente": "idle", "afk": "idle",
    "dnd": "dnd", "não perturbe": "dnd", "nao perturbe": "dnd", "np": "dnd",
    "offline": "offline", "off": "offline", "invis": "offline", "invisible": "offline",
}

def _fmt_hms(seconds: float) -> str:
    s = int(round(seconds))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

def _parse_utc(ts: str) -> datetime:
    # banco salva "YYYY-MM-DD HH:MM:SS" em UTC
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)

def _parse_hhmm(s: str) -> tuple[int, int]:
    s = s.strip()
    hh, mm = s.split(":")
    return int(hh), int(mm)

# Timezone
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(WORK_TZ)
except Exception:
    # fallback (Windows sem tzdata): usa offset simples, padrão -03
    try:
        off = int(os.getenv("WORK_TZ_OFFSET", "-3"))
        from datetime import timezone as _tz, timedelta as _td
        TZ = _tz(_td(hours=off))
    except Exception:
        TZ = timezone.utc

# Parâmetros de janela útil
_BIZ_DAYS = {int(x) for x in WORK_DAYS.split(",") if x != ""}
_SH, _SM = _parse_hhmm(WORK_START)
_EH, _EM = _parse_hhmm(WORK_END)

def _business_overlap_seconds(start_utc: datetime, end_utc: datetime) -> float:
    """
    Retorna quantos segundos entre [start_utc, end_utc] caem
    em dias/horários úteis definidos.
    """
    if end_utc <= start_utc:
        return 0.0

    start_local = start_utc.astimezone(TZ)
    end_local = end_utc.astimezone(TZ)

    total = 0.0
    cur = start_local

    # avança dia a dia calculando interseção com [SH:SM, EH:EM]
    while cur < end_local:
        # início e fim do dia corrente
        day_start = cur.replace(hour=_SH, minute=_SM, second=0, microsecond=0)
        day_end = cur.replace(hour=_EH, minute=_EM, second=0, microsecond=0)

        if cur.weekday() in _BIZ_DAYS:
            # interseção com a janela do dia
            seg_ini = max(cur, day_start)
            seg_fim = min(end_local, day_end)
            if seg_fim > seg_ini:
                total += (seg_fim - seg_ini).total_seconds()

        # avança para 00:00 do próximo dia
        nxt = (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        # evita loop infinito caso EH/SH causem retrocesso
        if nxt <= cur:
            nxt = cur + timedelta(hours=24)
        cur = nxt

    return total

class Duration(commands.Cog):
    """Cálculo de tempo por status usando presence_log, filtrando horário útil."""

    def __init__(self, bot: commands.Bot, config: Config):
        self.bot = bot
        self.config = config

    @commands.command(name="time_status")
    async def time_status(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
        days: Optional[int] = 7,
        status: Optional[str] = None,
    ):
        """
        Soma o tempo por status SOMENTE de seg-sex, 08:00-18:00 (ajustável via .env).
        Uso:
          !time_status
          !time_status @user 1
          !time_status @user 7 AUSENTE
        """
        member = member or ctx.author
        try:
            days = int(days) if days is not None else 7
        except Exception:
            days = 7

        status_filter = None
        if status:
            key = NORMALIZE_STATUS.get(status.strip().lower())
            if key is None:
                await ctx.reply("Status inválido. Use ONLINE / AUSENTE / NÃO PERTURBE / OFFLINE.")
                return
            status_filter = key

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)
        start = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        end = end_dt.strftime("%Y-%m-%d %H:%M:%S")

        # último status vigente antes do início
        last_before = db.fetch_one(
            "SELECT status, timestamp FROM presence_log "
            "WHERE guild_id = ? AND user_id = ? AND timestamp < ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (ctx.guild.id, member.id, start)
        )
        if last_before:
            current_status = last_before[0]
            prev_time_utc = start_dt
        else:
            current_status = "offline"
            prev_time_utc = start_dt

        # eventos no intervalo
        rows = db.fetch_all(
            "SELECT status, timestamp FROM presence_log "
            "WHERE guild_id = ? AND user_id = ? AND timestamp >= ? AND timestamp <= ? "
            "ORDER BY timestamp ASC",
            (ctx.guild.id, member.id, start, end)
        )

        durations: Dict[str, float] = {"online":0.0, "idle":0.0, "dnd":0.0, "offline":0.0}

        for st, ts in rows:
            t_utc = _parse_utc(ts)
            delta = _business_overlap_seconds(prev_time_utc, t_utc)
            if delta > 0:
                durations[current_status] += delta
            current_status = st
            prev_time_utc = t_utc

        # cauda até agora
        tail = _business_overlap_seconds(prev_time_utc, end_dt)
        if tail > 0:
            durations[current_status] += tail

        # resposta
        if status_filter:
            label = LABEL_PT.get(status_filter, status_filter.upper())
            await ctx.reply(
                f"**{member.display_name}** — últimos {days} dias (útil {WORK_START}-{WORK_END}, seg-sex)\n"
                f"- {label}: {_fmt_hms(durations.get(status_filter, 0))}"
            )
        else:
            order = ["online", "idle", "dnd", "offline"]
            lines = [f"**{member.display_name}** — últimos {days} dias (útil {WORK_START}-{WORK_END}, seg-sex)"]
            for k in order:
                lines.append(f"- {LABEL_PT[k]}: {_fmt_hms(durations[k])}")
            await ctx.reply("\n".join(lines))
