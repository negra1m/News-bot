"""
Cog JONES — Oportunidades de projeto.
Monitora Workana BR, 99Freelas e outras fontes a cada 4h.
Posta leads relevantes no canal #oportunidades.
"""

import asyncio
import hashlib
import re

import feedparser
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone

import runtime_config
from db import is_seen, mark_seen


# ─── Parsing ─────────────────────────────────

def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

def _post_id(entry) -> str:
    raw = entry.get("id") or entry.get("link", "")
    return "opp_" + hashlib.md5(raw.encode()).hexdigest()

def _extract_budget(title: str, desc: str) -> str | None:
    text = title + " " + desc
    m = re.search(
        r"(USD|R\$|BRL|\$|€)\s*[\d.,]+(?:\s*[-–]\s*(?:USD|R\$|BRL|\$|€)?\s*[\d.,]+)?",
        text, re.I
    )
    return m.group(0).strip() if m else None

def _extract_skills(entry) -> str | None:
    cats = [t.get("term", "").strip() for t in entry.get("tags", []) if t.get("term")]
    return ", ".join(cats) if cats else None

def _is_relevant(title: str, desc: str, keywords: list) -> bool:
    text = (title + " " + desc).lower()
    return any(kw.lower() in text for kw in keywords)

def _parse_entry(entry, source: dict) -> dict:
    title    = _clean(entry.get("title", ""))
    link     = entry.get("link", "")
    desc_raw = entry.get("summary", "") or entry.get("description", "") or ""
    desc     = _clean(desc_raw)
    return {
        "id":          _post_id(entry),
        "source":      source["name"],
        "color":       source["color"],
        "title":       title,
        "link":        link,
        "published":   entry.get("published", ""),
        "description": desc[:600] + ("..." if len(desc) > 600 else ""),
        "budget":      _extract_budget(title, desc_raw),
        "skills":      _extract_skills(entry),
    }

def fetch_opportunities(source: dict, keywords: list) -> list:
    try:
        feed = feedparser.parse(source["rss"])
        results = []
        for entry in feed.entries:
            post = _parse_entry(entry, source)
            if not post["title"]:
                continue
            if is_seen(post["id"]):
                continue
            if not _is_relevant(post["title"], post["description"], keywords):
                continue
            results.append(post)
        return results
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
        channel_id = runtime_config.get_opp_channel_id()
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print("[OPP] Canal oportunidades não encontrado.")
            return
        await self._buscar_e_enviar(channel)

    @opp_task.before_loop
    async def before_opp(self):
        await self.bot.wait_until_ready()

    async def _buscar_e_enviar(self, channel) -> int:
        sources  = runtime_config.get_opp_sources()
        keywords = runtime_config.get_opp_keywords()
        loop     = asyncio.get_event_loop()
        total    = 0
        for source in sources:
            posts = await loop.run_in_executor(None, fetch_opportunities, source, keywords)
            for post in posts:
                try:
                    await self._send_embed(channel, post)
                    mark_seen(post["id"], post["source"], post["title"], post["link"])
                    total += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[OPP ERROR] send: {e}")
        return total

    async def _send_embed(self, channel, post: dict):
        lines = [f"🔧 **Projeto:** {post['title']}"]
        if post.get("skills"):
            lines.append(f"👥 **Precisamos de:** {post['skills']}")
        if post.get("budget"):
            lines.append(f"💰 **Orçamento:** {post['budget']}")
        lines.append(f"📣 **Contato:** <{post['link']}>")
        if post.get("description"):
            lines.append(f"\n**Descrição:**\n{post['description']}")

        embed = discord.Embed(
            description="\n".join(lines),
            color=post["color"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"{post['source']} • {post.get('published', '')}")
        await channel.send(embed=embed)

    @commands.command(name="oportunidades")
    async def cmd_oportunidades(self, ctx):
        """Força busca imediata de oportunidades."""
        channel_id = runtime_config.get_opp_channel_id()
        dest = self.bot.get_channel(channel_id) if channel_id else ctx.channel

        await ctx.send(embed=discord.Embed(
            description="🔍 Buscando oportunidades agora...",
            color=0xF39C12, timestamp=datetime.now(timezone.utc)))

        total = await self._buscar_e_enviar(dest or ctx.channel)

        msg = f"✅ **{total}** oportunidade(s) nova(s) encontrada(s)." if total \
              else "— Nenhuma oportunidade nova no momento."
        await ctx.send(embed=discord.Embed(
            description=msg,
            color=0x51CF66 if total else 0x636E72,
            timestamp=datetime.now(timezone.utc)))
