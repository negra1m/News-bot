import asyncio
import hashlib
import random
import re
import time

import feedparser
import requests
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone

from config import (
    DISCORD_WEBHOOK_URL, BLOG_SOURCES, NEWS_SOURCES,
    BLOG_MAX_POSTS, DELAY_BETWEEN, RANDOM_EXTRA_DELAY,
    NEWS_CYCLE_INTERVAL, TRUSTED_SOURCES, KEYWORDS_TECH, KEYWORDS_BLOCK,
)
from db import is_seen, mark_seen, enqueue, dequeue, is_in_queue


# ─── Filtro ──────────────────────────────────

def is_relevant(post):
    text = (post.get("title","") + " " + post.get("description","")).lower()
    for kw in KEYWORDS_BLOCK:
        if kw in text:
            return False
    if any(name in post.get("source","") for name in TRUSTED_SOURCES):
        return True
    for kw in KEYWORDS_TECH:
        if kw in text:
            return True
    return False


# ─── RSS helpers ─────────────────────────────

def make_post_id(entry):
    raw = entry.get("id") or entry.get("link","")
    return hashlib.md5(raw.encode()).hexdigest()

def get_post_image(entry):
    if hasattr(entry,"media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    if hasattr(entry,"media_content") and entry.media_content:
        for m in entry.media_content:
            if m.get("type","").startswith("image"):
                return m.get("url")
    if hasattr(entry,"enclosures") and entry.enclosures:
        for e in entry.enclosures:
            if "image" in e.get("type",""):
                return e.get("href")
    summary = entry.get("summary","") or ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    return m.group(1) if m else None

def get_post_description(entry):
    summary = entry.get("summary","") or ""
    if entry.get("content"):
        summary = entry.content[0].get("value", summary)
    clean = re.sub(r"<[^>]+>","",summary).strip()
    return clean[:200] + "..." if len(clean) > 200 else clean

def fetch_rss(source):
    try:
        feed = feedparser.parse(source["rss"])
        if not feed.entries:
            return []
        posts = []
        for entry in feed.entries:
            pub_parsed = entry.get("published_parsed")
            if pub_parsed:
                import calendar
                age_h = (time.time() - calendar.timegm(pub_parsed)) / 3600
                if age_h > 24:
                    continue
            post_id = make_post_id(entry)
            title   = re.sub(r"<[^>]+>","", entry.get("title","")).strip()
            if not title:
                continue
            posts.append({
                "id": post_id, "source": source["name"], "color": source["color"],
                "title": title, "link": entry.get("link",""),
                "published": entry.get("published",""),
                "image": get_post_image(entry), "description": get_post_description(entry),
            })
        return posts
    except Exception as e:
        print(f"[RSS ERROR] {source['name']}: {e}")
        return []

def send_to_discord(post):
    embed = {
        "author": {"name": post["source"]}, "title": post["title"][:256],
        "url": post["link"], "color": post["color"],
        "footer": {"text": post.get("published","")},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if post.get("description"):
        embed["description"] = post["description"]
    if post.get("image"):
        embed["image"] = {"url": post["image"]}
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds":[embed]}, timeout=10)
        time.sleep(0.5)
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
        return False

def process_source(source, max_posts, state):
    posts = fetch_rss(source)
    for p in posts:
        if not is_seen(p["id"]) and not is_in_queue(p["id"]):
            if is_relevant(p):
                enqueue(p)
            else:
                mark_seen(p["id"], p["source"], p.get("title",""), p.get("link",""))
    sent = 0
    for _ in range(max_posts):
        post = dequeue()
        if not post:
            break
        if send_to_discord(post):
            mark_seen(post["id"], post["source"], post["title"], post["link"])
            print(f"    ✓ {post['title'][:80]}")
            sent += 1
            state["total_sent"] += 1
        else:
            enqueue(post)
    return sent


# ─── Cog ─────────────────────────────────────

class RSSCog(commands.Cog):
    def __init__(self, bot, state):
        self.bot   = bot
        self.state = state

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.blog_task.is_running():
            self.blog_task.start()
        if not self.news_task.is_running():
            self.news_task.start()
        print("[RSS] Ciclos iniciados.")

    @tasks.loop(hours=1)
    async def blog_task(self):
        if self.state["paused"]:
            return
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._run_blog_cycle)
        except Exception as e:
            print(f"[TASK ERROR] blog_cycle: {e}")

    @tasks.loop(hours=1)
    async def news_task(self):
        if self.state["paused"]:
            return
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._run_news_cycle)
        except Exception as e:
            print(f"[TASK ERROR] news_cycle: {e}")

    @blog_task.before_loop
    async def before_blog(self):
        await self.bot.wait_until_ready()

    @news_task.before_loop
    async def before_news(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(NEWS_CYCLE_INTERVAL)

    def _run_blog_cycle(self):
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'─'*52}\n  [BLOGS] Ciclo às {now}\n{'─'*52}")
        total = 0
        sources = BLOG_SOURCES[:]
        random.shuffle(sources)
        for i, source in enumerate(sources):
            print(f"\n  [{i+1}/{len(sources)}] {source['name']}")
            total += process_source(source, BLOG_MAX_POSTS, self.state)
            if i < len(sources) - 1:
                time.sleep(DELAY_BETWEEN + random.randint(0, RANDOM_EXTRA_DELAY))
        self.state["last_blog_cycle"] = datetime.now()
        print(f"\n  Blogs: {total} post(s) enviado(s)")

    def _run_news_cycle(self):
        idx    = self.state["news_source_idx"] % len(NEWS_SOURCES)
        source = NEWS_SOURCES[idx]
        self.state["news_source_idx"] += 1
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*52}\n  [JORNAIS] Ciclo às {now} — {source['name']}\n{'='*52}")
        posts = fetch_rss(source)
        new   = [p for p in posts if not is_seen(p["id"]) and is_relevant(p)]
        if not new:
            print(f"    — Nada novo em {source['name']}")
            self.state["last_news_cycle"] = datetime.now()
            return
        post = new[0]
        if send_to_discord(post):
            mark_seen(post["id"], post["source"], post["title"], post["link"])
            print(f"  ✓ [{post['source']}] {post['title'][:70]}")
            self.state["total_sent"] += 1
        self.state["last_news_cycle"] = datetime.now()


def setup(bot, state):
    bot.add_cog(RSSCog(bot, state))
