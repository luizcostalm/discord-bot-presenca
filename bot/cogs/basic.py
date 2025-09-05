# bot/cogs/basic.py
import os
import discord
import sys, os
from discord.ext import commands


def _about_color() -> int:
    """
    Lê ABOUT_COLOR do .env.
    Aceita "0x5865F2" (hex com 0x) ou inteiro decimal.
    """
    s = os.getenv("ABOUT_COLOR", "0x5865F2")
    try:
        return int(s, 16) if s.lower().startswith("0x") else int(s)
    except Exception:
        return 0x5865F2


class Basic(commands.Cog):
    @commands.command(name="relatorio_ponto")
    @commands.has_permissions(administrator=True)
    async def relatorio_ponto(self, ctx):
        """
        Gera um relatório privado mostrando quem ficou online no Discord nos horários de entrada/retorno definidos pelos cargos.
        """
        import pytz
        from datetime import datetime, timedelta
        tz_br = pytz.timezone('America/Sao_Paulo')
        agora_br = datetime.now(tz_br)
        horarios_cargos = {
            'Entrada-07:30': '07:30',
            'Entrada-08:00': '08:00',
            'Entrada-08:30': '08:30',
            'Retorno-13:30': '13:30',
            'Retorno-14:00': '14:00',
        }
        relatorio = []
        for cargo_nome, hora_str in horarios_cargos.items():
            cargo = discord.utils.get(ctx.guild.roles, name=cargo_nome)
            if not cargo:
                relatorio.append(f"Cargo `{cargo_nome}` não encontrado.")
                continue
            membros = [m for m in ctx.guild.members if cargo in m.roles and not m.bot]
            if not membros:
                relatorio.append(f"Nenhum membro com o cargo `{cargo_nome}`.")
                continue
            hora_br = agora_br.replace(hour=int(hora_str.split(":")[0]), minute=int(hora_str.split(":")[1]), second=0, microsecond=0)
            janela_ini = hora_br
            janela_fim = hora_br  # sem tolerância: só conta se ficou online exatamente no horário
            from bot import db
            presentes = []
            ausentes = []
            for membro in membros:
                row = db.fetch_one(
                    "SELECT status, timestamp FROM presence_log WHERE user_id=? AND status='online' AND timestamp = ? ORDER BY timestamp LIMIT 1",
                    (membro.id, janela_ini.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S"),)
                )
                if row:
                    presentes.append(membro.display_name)
                else:
                    ausentes.append(membro.display_name)
            relatorio.append(f"\n**{cargo_nome} ({hora_str})**")
            relatorio.append(f"Presentes: {', '.join(presentes) if presentes else 'Nenhum'}")
            relatorio.append(f"Ausentes: {', '.join(ausentes) if ausentes else 'Nenhum'}")
        try:
            await ctx.author.send("\n".join(relatorio))
            await ctx.reply("Relatório enviado por DM!")
        except Exception:
            await ctx.reply("Não consegui enviar o relatório por DM. Verifique suas configurações de privacidade.")
    """
    Comandos básicos / utilitários:
      - !ping
      - !about (com assinatura/empresa/versão e logo)
      - !intents_check
    """

    def __init__(self, bot: commands.Bot, config):
        self.bot = bot
        self.config = config

    # -----------------------
    # Comandos públicos
    # -----------------------

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Mostra a latência do bot."""
        await ctx.reply(f"Pong! Latência: {round(self.bot.latency * 1000)} ms")

    @commands.command(name="about", aliases=["sobre"])
    async def about(self, ctx: commands.Context):
        """
        Mostra informações do bot com assinatura/branding.
        Suporta:
          - ABOUT_ENTERPRISE (ex.: 'Leis')
          - ABOUT_VERSION (ex.: '1.0')
          - ABOUT_SIGNATURE (texto)
          - ABOUT_SIGNATURE_LINK (url)
          - ABOUT_ICON_URL (https PNG/JPG/WEBP/GIF)
          - ABOUT_ICON_PATH (arquivo local PNG/JPG/WEBP/GIF)
          - ABOUT_COLOR (ex.: 0x5865F2)
        Se ABOUT_ICON_PATH existir, ele tem prioridade e o arquivo é enviado como anexo.
        """
        env = os.getenv
        intents = self.bot.intents

        enterprise = (env("ABOUT_ENTERPRISE", "") or "").strip()
        version = (env("ABOUT_VERSION", "") or "").strip()
        sig_text = (env("ABOUT_SIGNATURE", "") or "").strip()
        sig_link = (env("ABOUT_SIGNATURE_LINK", "") or "").strip()

        icon_url = (env("ABOUT_ICON_URL", "") or "").strip()
        icon_path = (env("ABOUT_ICON_PATH", "") or "").strip()  # caminho local opcional
        sample_every = env("SAMPLE_EVERY_SECONDS", "60")

        embed = discord.Embed(
            title="BotStatus",
            description="Monitoramento de presença no Discord",
            color=_about_color(),
            timestamp=discord.utils.utcnow(),
        )

        # Cabeçalho: Empresa • versão
        author_name = " • ".join(
            x for x in [enterprise or None, f"v{version}" if version else None] if x
        )
        author_kwargs = {"url": sig_link} if sig_link else {}

        # Definir ícone (URL pública OU arquivo local anexado)
        file_to_send: discord.File | None = None

        def _ext_ok(u: str) -> bool:
            u = u.lower()
            return any(u.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"))

        if icon_path and os.path.isfile(icon_path):
            # anexa arquivo local
            file_to_send = discord.File(icon_path, filename="about_icon.png")
            embed.set_author(
                name=(author_name or " "),
                icon_url="attachment://about_icon.png",
                **author_kwargs,
            )
            embed.set_thumbnail(url="attachment://about_icon.png")
        elif icon_url and _ext_ok(icon_url):
            # usa URL pública
            embed.set_author(
                name=(author_name or " "),
                icon_url=icon_url,
                **author_kwargs,
            )
            embed.set_thumbnail(url=icon_url)
        elif author_name:
            # sem ícone, apenas o texto
            embed.set_author(name=author_name, **author_kwargs)

        # Campos principais
        embed.add_field(name="Prefixo", value=f"`{self.config.prefix}`", inline=True)
        embed.add_field(name="DB", value=f"`{self.config.database_file}`", inline=True)
        embed.add_field(name="Servidores", value=str(len(self.bot.guilds)), inline=True)

        embed.add_field(name="Sampler", value=f"cada **{sample_every}s**", inline=True)
        embed.add_field(
            name="Intents",
            value=(
                f"message_content={intents.message_content} • "
                f"members={intents.members} • presences={intents.presences}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Comandos",
            value=(
                "`!status_servidor`, `!ausente`, `!trabalhou`, "
                "`!time_status`, `!janela_tempo`, `!report`, `!export_csv`"
            ),
            inline=False,
        )

        # Assinatura (um único lugar, para não duplicar em rodapé)
        if sig_text and sig_link:
            embed.add_field(name="Assinatura", value=f"[{sig_text}]({sig_link})", inline=False)
        elif sig_text:
            embed.add_field(name="Assinatura", value=sig_text, inline=False)

        # Rodapé minimal (sem repetir a assinatura)
        if author_name:
            embed.set_footer(text=author_name)

        if file_to_send:
            await ctx.reply(embed=embed, file=file_to_send)
        else:
            await ctx.reply(embed=embed)

    @commands.command(name="intents_check")
    async def intents_check(self, ctx: commands.Context):
        """Mostra o status das intents do bot (útil para debug)."""
        i = self.bot.intents
        await ctx.reply(
            f"message_content={i.message_content}, members={i.members}, presences={i.presences}"
        )
