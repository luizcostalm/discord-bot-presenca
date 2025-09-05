from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
import os, re

import discord
from discord.ext import commands
from bot.config import Config
from bot import db

# --------- Padrões configuráveis via .env ----------
DEFAULT_TZ    = os.getenv("WORK_TZ", "America/Sao_Paulo")
DEFAULT_DAYS  = os.getenv("WORK_DAYS", "0,1,2,3,4")  # 0=seg ... 6=dom (padrão seg-sex)
DEFAULT_START = os.getenv("WORK_START", "08:00")
DEFAULT_END   = os.getenv("WORK_END",   "18:00")

LABEL_PT = {
    "online":  "ONLINE",
    "idle":    "AUSENTE",
    "dnd":     "NÃO PERTURBE",
    "offline": "OFFLINE",
}

# Timezone
try:
    from zoneinfo import ZoneInfo
    def get_tz(s: str): return ZoneInfo(s)
except Exception:
    from datetime import timezone as _tz, timedelta as _td
    def get_tz(s: str):  # fallback simples (AMT -03 se não houver tzdata)
        return _tz(_td(hours=int(os.getenv("WORK_TZ_OFFSET","-3"))))

def _tz_label(tz) -> str:
    return getattr(tz, "key", "local")

def _parse_hhmm(s: str) -> Tuple[int,int]:
    s = s.strip().strip('"').strip("'")
    hh, mm = s.split(":")
    return int(hh), int(mm)

def _fmt_hms(seconds: float) -> str:
    s = int(round(seconds))
    h, s = divmod(s, 3600); m, s = divmod(s, 60)
    out = []
    if h: out.append(f"{h}h")
    if m: out.append(f"{m}m")
    out.append(f"{s}s")
    return " ".join(out)

def _parse_utc(ts: str) -> datetime:
    # banco salva "YYYY-MM-DD HH:MM:SS" em UTC
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)

def _durations_in_window(guild_id: int, user_id: int, start_utc: datetime, end_utc: datetime) -> Dict[str,float]:
    """
    Devolve os segundos por status em [start_utc, end_utc].
    A janela já deve representar o período desejado (ex.: 08:00–18:00).
    """
    assert start_utc.tzinfo and end_utc.tzinfo
    if end_utc <= start_utc:
        return {"online":0.0, "idle":0.0, "dnd":0.0, "offline":0.0}

    start = start_utc.strftime("%Y-%m-%d %H:%M:%S")
    end   = end_utc.strftime("%Y-%m-%d %H:%M:%S")

    last_before = db.fetch_one(
        "SELECT status, timestamp FROM presence_log "
        "WHERE guild_id = ? AND user_id = ? AND timestamp < ? "
        "ORDER BY timestamp DESC LIMIT 1",
        (guild_id, user_id, start)
    )
    current_status = last_before[0] if last_before else "offline"
    prev_time = start_utc

    rows = db.fetch_all(
        "SELECT status, timestamp FROM presence_log "
        "WHERE guild_id = ? AND user_id = ? AND timestamp >= ? AND timestamp <= ? "
        "ORDER BY timestamp ASC",
        (guild_id, user_id, start, end)
    )

    durs = {"online":0.0, "idle":0.0, "dnd":0.0, "offline":0.0}
    for st, ts in rows:
        t = _parse_utc(ts)
        if t > prev_time:
            durs[current_status] += (t - prev_time).total_seconds()
        current_status = st
        prev_time = t

    if end_utc > prev_time:
        durs[current_status] += (end_utc - prev_time).total_seconds()
    return durs

def _parse_when(arg: Optional[str], tz, start_hm: Tuple[int,int], end_hm: Tuple[int,int]) -> List[Tuple[datetime, datetime]]:
    """
    Converte:
      - "hoje" / "today"
      - "ontem" / "yesterday"
      - "YYYY-MM-DD"
      - "YYYY-MM-DD..YYYY-MM-DD" (gerando uma janela por dia)
    em lista de janelas [início_utc, fim_utc], 1 por dia, usando as horas start_hm/end_hm.
    """
    now_local = datetime.now(tz)
    ymd = r"\d{4}-\d{2}-\d{2}"
    sh, sm = start_hm; eh, em = end_hm

    token = (arg or "hoje").strip().lower()
    if token in ("hoje", "today"):
        d = now_local.date()
        a = datetime(d.year,d.month,d.day, sh,sm, tzinfo=tz)
        b = datetime(d.year,d.month,d.day, eh,em, tzinfo=tz)
        return [(a.astimezone(timezone.utc), b.astimezone(timezone.utc))]
    if token in ("ontem", "yesterday"):
        d = (now_local - timedelta(days=1)).date()
        a = datetime(d.year,d.month,d.day, sh,sm, tzinfo=tz)
        b = datetime(d.year,d.month,d.day, eh,em, tzinfo=tz)
        return [(a.astimezone(timezone.utc), b.astimezone(timezone.utc))]
    if re.fullmatch(ymd, token):
        y,m,dd = map(int, token.split("-"))
        a = datetime(y,m,dd, sh,sm, tzinfo=tz)
        b = datetime(y,m,dd, eh,em, tzinfo=tz)
        return [(a.astimezone(timezone.utc), b.astimezone(timezone.utc))]
    if ".." in token:
        a_str, b_str = token.split("..",1)
        y1,m1,d1 = map(int, a_str.split("-"))
        y2,m2,d2 = map(int, b_str.split("-"))
        start_d = datetime(y1,m1,d1, tzinfo=tz).date()
        end_d   = datetime(y2,m2,d2, tzinfo=tz).date()
        if end_d < start_d: start_d, end_d = end_d, start_d
        out = []
        cur = start_d
        while cur <= end_d:
            a = datetime(cur.year,cur.month,cur.day, sh,sm, tzinfo=tz)
            b = datetime(cur.year,cur.month,cur.day, eh,em, tzinfo=tz)
            out.append((a.astimezone(timezone.utc), b.astimezone(timezone.utc)))
            cur += timedelta(days=1)
        return out

    # fallback: hoje
    d = now_local.date()
    a = datetime(d.year,d.month,d.day, sh,sm, tzinfo=tz)
    b = datetime(d.year,d.month,d.day, eh,em, tzinfo=tz)
    return [(a.astimezone(timezone.utc), b.astimezone(timezone.utc))]

class WorkCheck(commands.Cog):
    """Consultas personalizadas em PT-BR: 'trabalhou?', 'ausente', 'janela_tempo'."""
    def __init__(self, bot: commands.Bot, config: Config):
        self.bot = bot
        self.config = config

    # ----------------- TRABALHOU? -----------------
    @commands.command(name="trabalhou", aliases=["worked"])
    async def trabalhou(
        self,
        ctx: commands.Context,
        membro: Optional[discord.Member] = None,
        quando: Optional[str] = "hoje",
        min_minutos: Optional[int] = 30,
        modo: Optional[str] = "ativo",
        inicio: Optional[str] = None,
        fim: Optional[str] = None,
        dias: Optional[str] = None,
        fuso: Optional[str] = None,
    ):
        """
        Diz se 'trabalhou' (atingiu tempo mínimo) no(s) dia(s) especificado(s).
        Exemplos:
          !trabalhou                           -> você, HOJE, 30min, 08:00-18:00, seg-sex
          !trabalhou @luiz ontem 15            -> 15min ontem
          !trabalhou @luiz 2025-08-10          -> dia específico
          !trabalhou @luiz 2025-08-10..2025-08-14 30 ativo 09:00 17:00 0,1,2,3,4 America/Sao_Paulo
        """
        membro = membro or ctx.author
        try:
            min_minutos = int(min_minutos)
        except Exception:
            min_minutos = 30

        tz = get_tz(fuso or DEFAULT_TZ)
        sh, sm = _parse_hhmm(inicio or DEFAULT_START)
        eh, em = _parse_hhmm(fim    or DEFAULT_END)
        dias_validos = set(int(x) for x in (dias or DEFAULT_DAYS).split(",") if x!="")

        janelas = _parse_when(quando, tz, (sh,sm), (eh,em))

        modo = (str(modo or "ativo")).lower()
        status_ativos = {"online","idle","dnd"} if modo in ("ativo","active") else {"online"}

        linhas: List[str] = []
        total_ativo = 0.0

        for w_ini_utc, w_fim_utc in janelas:
            data_local = w_ini_utc.astimezone(tz).date()
            if data_local.weekday() not in dias_validos:
                linhas.append(f"- {data_local} (fora dos dias úteis) — ignorado")
                continue

            durs = _durations_in_window(ctx.guild.id, membro.id, w_ini_utc, w_fim_utc)
            ativo_seg = sum(durs[k] for k in status_ativos)
            total_ativo += ativo_seg

            ok = ativo_seg >= (min_minutos*60)
            status_word = "Sim ✅" if ok else "Não ❌"
            linhas.append(
                f"- {data_local}: {status_word} — ativo {_fmt_hms(ativo_seg)} "
                f"(ONLINE {_fmt_hms(durs['online'])}, AUSENTE {_fmt_hms(durs['idle'])}, DND {_fmt_hms(durs['dnd'])})"
            )

        janela_str = f"{inicio or DEFAULT_START}-{fim or DEFAULT_END}"
        if inicio and fim:
            janela_str = f"{inicio}-{fim}"
        cab = (f"**Trabalhou — {membro.display_name}**\n"
               f"Janela: {janela_str} | "
               f"Dias úteis: {','.join(map(str,sorted(dias_validos)))} | "
               f"Modo: {modo.upper()} | Mín: {min_minutos}min | TZ: {_tz_label(tz)}")
        linhas.insert(0, cab)
        if len(janelas) > 1:
            linhas.append(f"\n**Total ativo no período:** {_fmt_hms(total_ativo)}")

        await ctx.reply("\n".join(linhas))

    # ----------------- AUSENTE (idle) -----------------
    
    @commands.command(name="ausente", aliases=["tempo_ausente"])
    async def ausente(
        self,
        ctx: commands.Context,
        membro: Optional[discord.Member] = None,
        quando: Optional[str] = "hoje",
        periodo: Optional[str] = "manha",
        fuso: Optional[str] = None,
    ):
        """
        Mostra tempo AUSENTE (idle) no período desejado.
        Exemplos:
          !ausente @luiz hoje manha
          !ausente @luiz ontem tarde
          !ausente @luiz 2025-08-14 dia
          !ausente @luiz hoje 09:00-12:00
        """
        membro = membro or ctx.author
        tz = get_tz(fuso or DEFAULT_TZ)

        # períodos padrão em PT-BR
        mapa = {
            "manha": ("08:00", "12:00"),
            "tarde": ("13:00", "18:00"),
            "dia":   (DEFAULT_START, DEFAULT_END),  # 08–18 por padrão
        }
        if "-" in (periodo or "") and len(periodo.split("-")) == 2:
            ini, fim = periodo.split("-")
        else:
            ini, fim = mapa.get((periodo or "dia").lower(), mapa["dia"])

        sh, sm = _parse_hhmm(ini)
        eh, em = _parse_hhmm(fim)

        janelas = _parse_when(quando, tz, (sh,sm), (eh,em))
        dias_validos = set(int(x) for x in DEFAULT_DAYS.split(",") if x!="")

        total_idle = 0.0
        linhas = []


        for a_utc, b_utc in janelas:
            data_local = a_utc.astimezone(tz).date()
            if data_local.weekday() not in dias_validos:
                linhas.append(f"- {data_local} (fora dos dias úteis) — ignorado")
                continue

            durs = _durations_in_window(ctx.guild.id, membro.id, a_utc, b_utc)
            idle = durs["idle"]
            total_idle += idle

            # Buscar status personalizado do usuário (se houver)
            custom_status = None
            if hasattr(membro, "activities"):
                for act in membro.activities:
                    if isinstance(act, discord.CustomActivity) and act.name:
                        custom_status = act.name
                        break
            status_msg = f"- {data_local} {ini}-{fim}: AUSENTE {_fmt_hms(idle)}"
            if custom_status:
                status_msg += f" | Status personalizado: '{custom_status}'"
            linhas.append(status_msg)

        head = f"**Ausência — {membro.display_name} {ini}-{fim}** (TZ {_tz_label(tz)})"
        if len(janelas) > 1:
            linhas.append(f"\n**Total no período:** {_fmt_hms(total_idle)}")

        await ctx.reply("\n".join([head, *linhas]))

    
    # ----------------- AUSENTE AGORA  -----------------
    @commands.command(name="ausente_agora")
    async def ausente_agora(self, ctx, membro: discord.Member | None = None):
        """Diz se a pessoa está AUSENTE agora e, se possível, há quanto tempo."""
        membro = membro or ctx.author
        if str(membro.status) != "idle":
            await ctx.reply(f"{membro.display_name} **NÃO** está AUSENTE agora.")
            return

        row = db.fetch_one(
            "SELECT timestamp FROM presence_log WHERE guild_id=? AND user_id=? AND status='idle' "
            "ORDER BY timestamp DESC LIMIT 1",
            (ctx.guild.id, membro.id)
        )
        if not row:
            await ctx.reply(f"{membro.display_name} está **AUSENTE** agora (início desconhecido).")
            return

        t0 = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        dt = (datetime.now(timezone.utc) - t0).total_seconds()
        h, s = divmod(int(dt), 3600); m, s = divmod(s, 60)
        dur = (f"{h}h " if h else "") + (f"{m}m " if m else "") + f"{s}s"
        await ctx.reply(f"{membro.display_name} está **AUSENTE** há {dur}.")

    @commands.command(name="janela_tempo", aliases=["time_window"])
    async def janela_tempo(
        self,
        ctx: commands.Context,
        membro: Optional[discord.Member] = None,
        inicio_dt: Optional[str] = None,
        fim_dt: Optional[str] = None,
        modo: Optional[str] = "ativo",
        fuso: Optional[str] = None,
    ):
        """
        Soma por status em uma janela exata (datas/horas livres).
        Exemplos:
          !janela_tempo @luiz "2025-08-13 09:00" "2025-08-13 12:30"
          !janela_tempo @luiz 2025-08-13 09:00 2025-08-13 18:00 online America/Sao_Paulo
        """
        if not inicio_dt or not fim_dt:
            await ctx.reply("Use: !janela_tempo @user \"YYYY-MM-DD HH:MM\" \"YYYY-MM-DD HH:MM\" [modo] [fuso]")
            return

        membro = membro or ctx.author
        tz = get_tz(fuso or DEFAULT_TZ)
        modo = (str(modo or "ativo")).lower()
        status_ativos = {"online","idle","dnd"} if modo in ("ativo","active") else {"online"}

        def parse_local(s: str) -> datetime:
            s = s.strip().strip('"').strip("'")
            if " " in s:
                ymd, hm = s.split(" ",1)
            else:
                ymd, hm = s, "00:00"
            y,m,d = map(int, ymd.split("-"))
            hh,mm = map(int, hm.split(":"))
            return datetime(y,m,d, hh,mm, tzinfo=tz)

        a_local = parse_local(inicio_dt)
        b_local = parse_local(fim_dt)
        a_utc = a_local.astimezone(timezone.utc)
        b_utc = b_local.astimezone(timezone.utc)

        durs = _durations_in_window(ctx.guild.id, membro.id, a_utc, b_utc)
        ativo = sum(durs[k] for k in status_ativos)

        linhas = [
            f"**Janela de Tempo — {membro.display_name}**",
            f"{a_local.strftime('%Y-%m-%d %H:%M')} → {b_local.strftime('%Y-%m-%d %H:%M')} (TZ {_tz_label(tz)}) | modo {modo.upper()}",
            f"- ONLINE: {_fmt_hms(durs['online'])}",
            f"- AUSENTE: {_fmt_hms(durs['idle'])}",
            f"- NÃO PERTURBE: {_fmt_hms(durs['dnd'])}",
            f"- OFFLINE: {_fmt_hms(durs['offline'])}",
            f"**Ativo (critério {modo.upper()}): {_fmt_hms(ativo)}**",
        ]
        await ctx.reply("\n".join(linhas))
