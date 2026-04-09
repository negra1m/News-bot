import asyncio
import discord
from discord.ext import commands
from datetime import datetime, timezone

from config import BLOG_SOURCES, NEWS_SOURCES
from db import count_total_seen, count_queue
from cogs.rss import RSSCog


class TextCommandsCog(commands.Cog):
    def __init__(self, bot, state, voice_session):
        self.bot           = bot
        self.state         = state
        self.voice_session = voice_session

    @commands.command(name="comandos", aliases=["ajuda", "help"])
    async def cmd_comandos(self, ctx):
        embed = discord.Embed(
            description=(
                "**📋 Comandos disponíveis**\n\n"
                "**Notícias**\n"
                "`!status` — situação atual do bot\n"
                "`!forcenow` — forçar ciclo de notícias agora\n"
                "`!pausar` / `!resumir` — pausar/retomar envio\n"
                "`!fontes` — listar fontes ativas\n\n"
                "**Oportunidades**\n"
                "`!oportunidades` — buscar oportunidades agora\n\n"
                "**Reuniões**\n"
                "`!reuniao` — entrar no canal de voz e gravar\n"
                "`!parar` — parar gravação e transcrever\n\n"
                "**Configuração**\n"
                "`!conf` — ver config atual\n"
                "`!conf opp add/del` — fontes de oportunidades\n"
                "`!conf kw add/del` — keywords de busca\n"
                "`!conf reddit add <sub> opp|news` — adicionar subreddit\n"
                "`!conf reddit del <sub> opp|news` — remover subreddit\n"
                "`!conf reddit list` — ver subreddits ativos\n"
                "`!conf reset` — voltar aos defaults"
            ),
            color=0x5865F2, timestamp=datetime.now(timezone.utc))
        await ctx.send(embed=embed)

    @commands.command(name="status")
    async def cmd_status(self, ctx):
        uptime  = datetime.now(timezone.utc) - self.state["start_time"]
        h, m    = divmod(int(uptime.total_seconds()), 3600)
        m       = m // 60
        pausado = "⏸ Pausado" if self.state["paused"] else "▶️ Rodando"
        lb = self.state["last_blog_cycle"].strftime("%H:%M:%S") if self.state["last_blog_cycle"] else "—"
        ln = self.state["last_news_cycle"].strftime("%H:%M:%S") if self.state["last_news_cycle"] else "—"
        vs = self.voice_session
        gravando = f"🎙️ Desde {vs['start_time'].strftime('%H:%M:%S')}" if vs.get("active") else "—"
        embed = discord.Embed(
            description=(
                f"**🤖 Status do Bot**\n"
                f"Estado: {pausado}\n"
                f"Uptime: {h}h {m}min\n"
                f"Notícias enviadas: {self.state['total_sent']}\n"
                f"No banco: {count_total_seen()} | Na fila: {count_queue()}\n"
                f"Último ciclo blogs: {lb}\n"
                f"Último ciclo jornais: {ln}\n"
                f"Gravação: {gravando}"
            ),
            color=0x51CF66 if not self.state["paused"] else 0xFCC419,
            timestamp=datetime.now(timezone.utc))
        await ctx.send(embed=embed)

    @commands.command(name="forcenow")
    async def cmd_forcenow(self, ctx):
        await ctx.send(embed=discord.Embed(
            description="⚡ Ciclo forçado! Verificando fontes...",
            color=0x5865F2, timestamp=datetime.now(timezone.utc)))
        rss_cog = self.bot.get_cog("RSSCog")
        if rss_cog:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, rss_cog._run_blog_cycle)
            await loop.run_in_executor(None, rss_cog._run_news_cycle)

    @commands.command(name="pausar")
    async def cmd_pausar(self, ctx):
        self.state["paused"] = True
        await ctx.send(embed=discord.Embed(
            description="⏸ Bot pausado. Use `!resumir` para continuar.",
            color=0xFCC419, timestamp=datetime.now(timezone.utc)))

    @commands.command(name="resumir")
    async def cmd_resumir(self, ctx):
        self.state["paused"] = False
        await ctx.send(embed=discord.Embed(
            description="▶️ Bot retomado!",
            color=0x51CF66, timestamp=datetime.now(timezone.utc)))

    @commands.command(name="fontes")
    async def cmd_fontes(self, ctx):
        blogs = "\n".join(f"• {s['name']}" for s in BLOG_SOURCES)
        news  = "\n".join(f"• {s['name']}" for s in NEWS_SOURCES)
        await ctx.send(embed=discord.Embed(
            description=f"**📡 Fontes ativas**\n\n**Blogs** (1 post/1h)\n{blogs}\n\n**Jornais** (1 post rotativo/1h)\n{news}",
            color=0x5865F2, timestamp=datetime.now(timezone.utc)))


def setup(bot, state, voice_session):
    bot.add_cog(TextCommandsCog(bot, state, voice_session))
