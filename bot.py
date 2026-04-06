# ​‍​​​‍‍​​‍‍​​‍​‍​‍‍​‍​​‍​‍‍‍​‍​​​‍‍​‍‍‍‍​​‍​​​​​​‍‍‍​​​​​‍‍​‍‍‍‍​‍‍‍​​‍​​​‍​​​​​​​‍​‍‍​‍​​‍​​​​​​‍​​​‍‍​​‍‍​​‍​‍​‍‍‍​‍‍‍​​‍​​​​​​‍​​​​‍‍​‍‍​‍‍‍‍​‍‍​‍‍​‍​‍‍‍​​​​​‍‍​​​​‍​‍‍​‍‍‍​​‍‍‍‍​​‍​​‍​​​​​​‍‍‍‍‍​​​​‍​​​​​​‍​‍​‍‍​​‍‍​‍​​‍​‍‍​‍‍‍​​‍‍​‍​​‍
"""
Bot de Notícias + Transcrição de Reuniões → Discord
"""

import logging
import sys

import discord
from discord.ext import commands
from datetime import datetime, timezone

from config import DISCORD_BOT_TOKEN, ANTHROPIC_API_KEY, BLOG_SOURCES, NEWS_SOURCES, DEBUG
from db import init_db

# ─── Logging ─────────────────────────────────
# Mostra logs do discord.voice pra debugar conexão
logging.basicConfig(level=logging.INFO if DEBUG else logging.WARNING, stream=sys.stdout)
logging.getLogger("discord.voice_state").setLevel(logging.DEBUG)
logging.getLogger("discord.voice_client").setLevel(logging.DEBUG)
logging.getLogger("discord.gateway").setLevel(logging.INFO)

# ─── Estado global ───────────────────────────

state = {
    "paused":          False,
    "force_now":       False,
    "start_time":      datetime.now(timezone.utc),
    "last_blog_cycle": None,
    "last_news_cycle": None,
    "total_sent":      0,
    "news_source_idx": 0,
}

voice_session = {
    "vc":           None,
    "pcm_buffers":  {},
    "text_channel": None,
    "start_time":   None,
    "active":       False,
}

# ─── Bot setup ───────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states    = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"[BOT] Logado como {bot.user} ({bot.user.id})")
    init_db()

    # Registra cogs (async no discord.py 2.7+)
    from cogs.rss import RSSCog
    from cogs.text_commands import TextCommandsCog
    from cogs.voice import VoiceCog
    from cogs.opportunities import OpportunitiesCog
    from cogs.admin import AdminCog

    if not bot.get_cog("RSSCog"):
        await bot.add_cog(RSSCog(bot, state))
    if not bot.get_cog("TextCommandsCog"):
        await bot.add_cog(TextCommandsCog(bot, state, voice_session))
    if not bot.get_cog("VoiceCog"):
        await bot.add_cog(VoiceCog(bot, voice_session))
    if not bot.get_cog("OpportunitiesCog"):
        await bot.add_cog(OpportunitiesCog(bot))
    if not bot.get_cog("AdminCog"):
        await bot.add_cog(AdminCog(bot))

    print("[BOT] Cogs carregados. Pronto.")


# ─── Main ────────────────────────────────────

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("[ERRO] DISCORD_BOT_TOKEN não configurado.")
        sys.exit(1)

    print("=" * 52)
    print("  Bot de Notícias + Transcrição de Reuniões")
    print("=" * 52)
    print(f"Blogs  : {len(BLOG_SOURCES)} fontes, 1 post/h")
    print(f"Jornais: {len(NEWS_SOURCES)} fontes, 1 post rotativo/h")
    print(f"Whisper: faster-whisper local (modelo small, CPU)")
    print(f"Claude : {'✓' if ANTHROPIC_API_KEY else '✗'}")
    print(f"Debug  : {'sim' if DEBUG else 'não (use --debug)'}")
    print()
    bot.run(DISCORD_BOT_TOKEN)
