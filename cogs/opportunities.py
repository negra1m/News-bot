"""
Cog JONES — Oportunidades de projeto.
Monitora Workana BR e Upwork a cada 4h e posta leads relevantes
no canal #oportunidades via bot (não webhook).
"""

import asyncio
import hashlib
import re
import time

import feedparser
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone

from config import OPORTUNIDADES_CHANNEL_ID, OPPORTUNITIES_SOURCES, KEYWORDS_OPPORTUNITIES
from db import is_seen, mark_seen


# ─── Helpers ─────────────────────────────────

def _post_id(entry):
    raw = entry.get("id") or entry.get("link", "")
    return "opp_" + hashlib.md5(raw.encode()).hexdigest()

def _clean(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()

def _is_relevant(title, description):
    text = (title + " " + description).lower()
    return any(kw in text for kw in KEYWORDS_OPPORTUNITIES)

def _extract_budget(entry):
    """Tenta extrair orçamento de campos comuns de RSS de freelance."""
    for field in ("budget", "price", "salary"):
        val = entry.get(field)
        if val:
            return str(val)
    summary = _clean(entry.get("summary", ""))
    m = re.search(r"(R\$|USD|\$)\s*[\d.,]+", summary)
    return m.group(0) if m else None

def fetch_opportunities(source):
    try:
        feed = feedparser.parse(source["rss"])
        posts = []
        for entry in feed.entries:
            post_id = _post_id(entry)
            if is_seen(post_id):
                continue
            title = _clean(entry.get("title", ""))
            if not title:
                continue
            desc = _clean(entry.get("summary", "") or "")
            if not _is_relevant(title, desc):
                continue
            posts.append({
                "id":          post_id,
                "source":      source["name"],
                "color":       source["color"],
                "title":       title,
                "link":        entry.get("link", ""),
                "published":   entry.get("published", ""),
                "description": desc[:200] + ("..." if len(desc) > 200 else ""),
                "budget":      _extract_budget(entry),
            })
        return posts
    except Exception as e:
        print(f"[OPP ERROR] {source['name']}: {e}")
        return []


# ─── Cog ─────────────────────────────────────

class OpportunitiesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        if not self.opp_task.is_running():
            self.opp_task.start()
        print("[OPP] Ciclo de oportunidades iniciado (4h).")

    @tasks.loop(hours=4)
    async def opp_task(self):
        if not OPORTUNIDADES_CHANNEL_ID:
            return
        channel = self.bot.get_channel(OPORTUNIDADES_CHANNEL_ID)
        if not channel:
            print("[OPP] Canal oportunidades não encontrado.")
            return

        loop = asyncio.get_event_loop()
        total = 0
        for source in OPPORTUNITIES_SOURCES:
            posts = await loop.run_in_executor(None, fetch_opportunities, source)
            for post in posts:
                try:
                    await self._send_opportunity(channel, post)
                    mark_seen(post["id"], post["source"], post["title"], post["link"])
                    total += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[OPP ERROR] send: {e}")

        if total:
            print(f"[OPP] {total} oportunidade(s) enviada(s)")

    @opp_task.before_loop
    async def before_opp(self):
        await self.bot.wait_until_ready()

    async def _send_opportunity(self, channel, post):
        embed = discord.Embed(
            title=post["title"][:256],
            url=post["link"],
            color=post["color"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=f"💼 {post['source']}")
        if post["description"]:
            embed.description = post["description"]
        if post["budget"]:
            embed.add_field(name="💰 Orçamento", value=post["budget"], inline=True)
        embed.set_footer(text=post.get("published", ""))
        await channel.send(embed=embed)

    @commands.command(name="oportunidades")
    async def cmd_oportunidades(self, ctx):
        """Força busca imediata de oportunidades."""
        await ctx.send(embed=discord.Embed(
            description="🔍 Buscando oportunidades agora...",
            color=0xF39C12, timestamp=datetime.now(timezone.utc)))
        loop = asyncio.get_event_loop()
        total = 0
        for source in OPPORTUNITIES_SOURCES:
            posts = await loop.run_in_executor(None, fetch_opportunities, source)
            channel = self.bot.get_channel(OPORTUNIDADES_CHANNEL_ID) or ctx.channel
            for post in posts:
                try:
                    await self._send_opportunity(channel, post)
                    mark_seen(post["id"], post["source"], post["title"], post["link"])
                    total += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[OPP ERROR] send: {e}")
        await ctx.send(embed=discord.Embed(
            description=f"✅ {total} oportunidade(s) encontrada(s)." if total else "— Nenhuma oportunidade nova no momento.",
            color=0x51CF66 if total else 0x636E72,
            timestamp=datetime.now(timezone.utc)))


def setup(bot):
    bot.add_cog(OpportunitiesCog(bot))
