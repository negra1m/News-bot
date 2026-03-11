"""
Bot de Notícias → Discord
- Blogs oficiais: ciclo de 15min, 1 post por fonte
- Jornais tech: ciclo de 1h, 2 posts por fonte
- Filtro de relevância: IA, tech, geopolítica que afeta tech
- Comandos no Discord: !status, !forcenow, !pausar, !resumir, !fontes, !ajuda
- Use --debug para logs detalhados
"""

import feedparser
import requests
import sqlite3
import time
import random
import hashlib
import sys
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURAÇÃO GERAL
# ─────────────────────────────────────────────

# Webhook para ENVIAR notícias
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI"

# Token do bot do Discord para LER comandos
# Crie em: discord.com/developers → New Application → Bot → Token
DISCORD_BOT_TOKEN = "SEU_BOT_TOKEN_AQUI"

# ID do canal onde o bot vai ler comandos (clique direito no canal → Copiar ID)
DISCORD_CHANNEL_ID = "SEU_CHANNEL_ID_AQUI"

# ─────────────────────────────────────────────
# FONTES — BLOGS (15min, 1 post por ciclo)
# ─────────────────────────────────────────────

BLOG_SOURCES = [
    {
        "name":  "Cloudflare Blog",
        "color": 0xF6821F,
        "rss":   "https://blog.cloudflare.com/rss/",
    },
    {
        "name":  "Anthropic News",
        "color": 0xCC785C,
        "rss":   "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml",
    },
    {
        "name":  "Replit Blog",
        "color": 0xF26207,
        "rss":   "https://blog.replit.com/feed.xml",
    },

]

# ─────────────────────────────────────────────
# FONTES — JORNAIS (1h, 2 posts por ciclo)
# ─────────────────────────────────────────────

NEWS_SOURCES = [
    {
        "name":  "Reuters Technology",
        "color": 0xFF6B6B,
        "rss":   "https://feeds.reuters.com/reuters/technology",
    },
    {
        "name":  "TechCrunch",
        "color": 0x0A7D3E,
        "rss":   "https://techcrunch.com/feed/",
    },
]

# ─────────────────────────────────────────────
# INTERVALOS
# ─────────────────────────────────────────────

BLOG_CYCLE_INTERVAL  = 3600  # 1 hora
NEWS_CYCLE_INTERVAL  = 3600  # 1 hora
BLOG_MAX_POSTS       = 1
NEWS_MAX_POSTS       = 1
DELAY_BETWEEN        = 5
RANDOM_EXTRA_DELAY   = 5

DB_PATH = Path(__file__).parent / "seen_posts.db"
DEBUG   = "--debug" in sys.argv

# Estado global
state = {
    "paused":         False,
    "force_now":      False,
    "start_time":     datetime.now(timezone.utc),
    "last_blog_cycle": None,
    "last_news_cycle": None,
    "total_sent":     0,
    "news_source_idx": 0,
}

def log(msg):
    if DEBUG:
        print(msg)

# ─────────────────────────────────────────────
# BANCO DE DADOS
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            id        TEXT PRIMARY KEY,
            source    TEXT NOT NULL,
            title     TEXT,
            link      TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def is_seen(post_id: str) -> bool:
    conn   = sqlite3.connect(DB_PATH)
    result = conn.execute("SELECT 1 FROM seen WHERE id = ?", (post_id,)).fetchone()
    conn.close()
    return result is not None

def mark_seen(post_id: str, source: str, title: str, link: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO seen (id, source, title, link) VALUES (?, ?, ?, ?)",
        (post_id, source, title, link)
    )
    conn.commit()
    conn.close()

def count_seen(source: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    n    = conn.execute("SELECT COUNT(*) FROM seen WHERE source = ?", (source,)).fetchone()[0]
    conn.close()
    return n

def count_total_seen() -> int:
    conn = sqlite3.connect(DB_PATH)
    n    = conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
    conn.close()
    return n

# ─────────────────────────────────────────────
# FILTRO DE RELEVÂNCIA
# ─────────────────────────────────────────────

# Fontes confiáveis — todo conteúdo é tech por definição
TRUSTED_SOURCES = ["Cloudflare", "Replit", "Anthropic", "Perplexity"]

# Para passar o filtro, o post PRECISA ter pelo menos uma dessas
KEYWORDS_TECH = [
    # IA e modelos
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "gpt", "claude", "gemini", "copilot", "chatbot", "neural network",
    "model", "inference", "fine-tuning", "embedding", "agent", "rag",
    "generative", "diffusion", "transformer",
    # Desenvolvimento e infraestrutura
    "api", "sdk", "open source", "developer", "programming", "code",
    "cloud", "serverless", "edge computing", "kubernetes", "docker",
    "devops", "cicd", "database", "backend", "frontend", "framework",
    # Produtos e empresas tech
    "openai", "anthropic", "google deepmind", "microsoft", "meta ai",
    "nvidia", "cloudflare", "replit", "vercel", "aws", "azure", "gcp",
    "apple", "tesla", "spacex", "palantir", "databricks",
    "software", "hardware", "chip", "semiconductor", "gpu", "processor",
    "startup", "tech funding", "series a", "series b", "acquisition",
    # Segurança e privacidade
    "cybersecurity", "data breach", "vulnerability", "encryption",
    "zero-day", "ransomware", "malware", "phishing",
    # Geopolítica SÓ quando afeta tech
    "tech tariff", "chip ban", "semiconductor export", "tech sanction",
    "ai regulation", "tech antitrust", "data privacy law", "gdpr",
    "tech war", "chip supply chain",
    # Outros temas tech
    "quantum computing", "robotics", "automation", "drone", "ev",
    "electric vehicle", "battery technology", "5g", "6g",
]

# Qualquer post com essas palavras é BLOQUEADO, mesmo que tenha keywords tech
KEYWORDS_BLOCK = [
    "sports", "football", "soccer", "basketball", "baseball", "tennis", "nfl", "nba",
    "celebrity", "actor", "actress", "singer", "rapper", "kardashian",
    "entertainment", "box office", "grammy", "oscar", "emmy",
    "fashion", "beauty", "makeup", "skincare", "luxury",
    "cooking", "recipe", "restaurant", "food review",
    "travel", "tourism", "hotel", "vacation",
    "weather", "horoscope", "zodiac", "astrology",
    "reality tv", "dating show",
]

def is_relevant(post: dict) -> bool:
    """Só passa posts genuinamente de tecnologia."""
    text = (post.get("title", "") + " " + post.get("description", "")).lower()

    # Bloqueia categorias irrelevantes primeiro
    for kw in KEYWORDS_BLOCK:
        if kw in text:
            log(f"    [FILTRO] Bloqueado: '{kw}' — {post['title'][:60]}")
            return False

    # Fontes 100% tech — passa direto
    if any(name in post.get("source", "") for name in TRUSTED_SOURCES):
        return True

    # Para Reuters e TechCrunch — exige keyword tech obrigatoriamente
    for kw in KEYWORDS_TECH:
        if kw in text:
            return True

    log(f"    [FILTRO] Sem keyword tech: {post['title'][:60]}")
    return False

# ─────────────────────────────────────────────
# RSS
# ─────────────────────────────────────────────

def make_post_id(entry) -> str:
    raw = entry.get("id") or entry.get("link", "")
    return hashlib.md5(raw.encode()).hexdigest()

def get_post_image(entry) -> str | None:
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        return entry.media_thumbnail[0].get('url')
    if hasattr(entry, 'media_content') and entry.media_content:
        for m in entry.media_content:
            if m.get('type', '').startswith('image'):
                return m.get('url')
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for e in entry.enclosures:
            if 'image' in e.get('type', ''):
                return e.get('href')
    summary = entry.get('summary', '') or ''
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if match:
        return match.group(1)
    return None

def get_post_description(entry) -> str:
    summary = entry.get('summary', '') or ''
    if entry.get('content'):
        summary = entry.content[0].get('value', summary)
    clean = re.sub(r'<[^>]+>', '', summary).strip()
    return clean[:200] + '...' if len(clean) > 200 else clean

def fetch_rss(source: dict) -> list[dict]:
    log(f"    [RSS] {source['rss']}")
    try:
        feed = feedparser.parse(source["rss"])
        if not feed.entries:
            print(f"    [WARN] Feed vazio: {source['name']}")
            return []
        posts = []
        for entry in feed.entries:
            post_id     = make_post_id(entry)
            title       = re.sub(r"<[^>]+>", "", entry.get("title", "")).strip()
            link        = entry.get("link", "")
            published   = entry.get("published", "")
            image       = get_post_image(entry)
            description = get_post_description(entry)
            if not title:
                continue
            posts.append({
                "id":          post_id,
                "source":      source["name"],
                "color":       source["color"],
                "title":       title,
                "link":        link,
                "published":   published,
                "image":       image,
                "description": description,
            })
        log(f"    [RSS] {len(posts)} posts encontrados")
        return posts
    except Exception as e:
        print(f"    [ERROR] {source['name']}: {e}")
        return []

# ─────────────────────────────────────────────
# DISCORD — ENVIO
# ─────────────────────────────────────────────

def send_to_discord(post: dict) -> bool:
    embed = {
        "author":    {"name": post["source"]},
        "title":     post["title"][:256],
        "url":       post["link"],
        "color":     post["color"],
        "footer":    {"text": post.get("published", "")},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if post.get("description"):
        embed["description"] = post["description"]
    if post.get("image"):
        embed["image"] = {"url": post["image"]}

    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=10
        )
        time.sleep(0.5)
        if resp.status_code in (200, 204):
            return True
        print(f"    [ERROR] Discord {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"    [ERROR] {e}")
        return False

def send_command_response(message: str, color: int = 0x5865F2):
    """Envia uma resposta de comando como embed no Discord."""
    embed = {
        "description": message,
        "color":       color,
        "footer":      {"text": "News Bot"},
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
    except Exception as e:
        print(f"[ERROR] Falha ao responder comando: {e}")

# ─────────────────────────────────────────────
# DISCORD — COMANDOS
# ─────────────────────────────────────────────

def get_discord_messages(after_id: str = None) -> list[dict]:
    """Busca mensagens recentes do canal."""
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    params  = {"limit": 10}
    if after_id:
        params["after"] = after_id
    try:
        resp = requests.get(
            f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages",
            headers=headers,
            params=params,
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log(f"[CMD] Erro ao buscar mensagens: {e}")
    return []

def handle_command(cmd: str):
    cmd = cmd.strip().lower()
    print(f"[CMD] Recebido: {cmd}")

    if cmd == "!ajuda":
        send_command_response(
            "**📋 Comandos disponíveis**\n"
            "`!status` — situação atual do bot\n"
            "`!forcenow` — forçar ciclo imediatamente\n"
            "`!pausar` — pausar envio de notícias\n"
            "`!resumir` — retomar envio\n"
            "`!fontes` — listar fontes ativas\n"
            "`!ajuda` — mostrar esta mensagem"
        )

    elif cmd == "!status":
        uptime    = datetime.now(timezone.utc) - state["start_time"]
        horas     = int(uptime.total_seconds() // 3600)
        minutos   = int((uptime.total_seconds() % 3600) // 60)
        pausado   = "⏸ Pausado" if state["paused"] else "▶️ Rodando"
        last_blog = state["last_blog_cycle"].strftime("%H:%M:%S") if state["last_blog_cycle"] else "—"
        last_news = state["last_news_cycle"].strftime("%H:%M:%S") if state["last_news_cycle"] else "—"
        send_command_response(
            f"**🤖 Status do Bot**\n"
            f"Estado: {pausado}\n"
            f"Uptime: {horas}h {minutos}min\n"
            f"Notícias enviadas: {state['total_sent']}\n"
            f"No banco: {count_total_seen()}\n"
            f"Último ciclo blogs: {last_blog}\n"
            f"Último ciclo jornais: {last_news}",
            color=0x51CF66 if not state["paused"] else 0xFCC419
        )

    elif cmd == "!forcenow":
        state["force_now"] = True
        send_command_response("⚡ Ciclo forçado! Verificando fontes agora...")

    elif cmd == "!pausar":
        state["paused"] = True
        send_command_response("⏸ Bot pausado. Use `!resumir` para continuar.", color=0xFCC419)

    elif cmd == "!resumir":
        state["paused"] = False
        send_command_response("▶️ Bot retomado!", color=0x51CF66)

    elif cmd == "!fontes":
        blogs = "\n".join(f"• {s['name']} (15min)" for s in BLOG_SOURCES)
        news  = "\n".join(f"• {s['name']} (1h)" for s in NEWS_SOURCES)
        send_command_response(
            f"**📡 Fontes ativas**\n\n"
            f"**Blogs** (1 post/15min)\n{blogs}\n\n"
            f"**Jornais** (2 posts/1h)\n{news}"
        )

def poll_commands():
    """Thread que fica verificando comandos no Discord a cada 5s."""
    last_message_id = None
    print("[CMD] Listener de comandos iniciado")

    # Pega o ID da última mensagem pra não reprocessar antigas
    msgs = get_discord_messages()
    if msgs:
        last_message_id = msgs[0]["id"]

    while True:
        time.sleep(5)
        try:
            msgs = get_discord_messages(after_id=last_message_id)
            for msg in reversed(msgs):
                last_message_id = msg["id"]
                content = msg.get("content", "").strip()
                if content.startswith("!"):
                    handle_command(content)
        except Exception as e:
            log(f"[CMD] Erro no poll: {e}")

# ─────────────────────────────────────────────
# LÓGICA DE CICLO
# ─────────────────────────────────────────────

def process_source(source: dict, max_posts: int) -> int:
    log(f"    [DB] '{source['name']}' tem {count_seen(source['name'])} posts no banco")
    posts = fetch_rss(source)
    if not posts:
        return 0

    new_posts = [p for p in posts if not is_seen(p["id"])]
    new_posts = [p for p in new_posts if is_relevant(p)]
    log(f"    [COMPARE] {len(posts)} RSS | {len(posts)-len(new_posts)} já vistos/filtrados | {len(new_posts)} novos")

    if not new_posts:
        print(f"    — Nada novo")
        return 0

    to_send = new_posts[:max_posts]
    sent    = 0
    for post in reversed(to_send):
        ok = send_to_discord(post)
        if ok:
            mark_seen(post["id"], post["source"], post["title"], post["link"])
            print(f"    ✓ {post['title'][:80]}")
            sent += 1
            state["total_sent"] += 1
        else:
            print(f"    ✗ Falha: {post['title'][:60]}")

    if len(new_posts) > max_posts:
        print(f"    ⚠ {len(new_posts) - max_posts} adiado(s) pro próximo ciclo")

    return sent


def run_blog_cycle():
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'─'*52}")
    print(f"  [BLOGS] Ciclo às {now}")
    print(f"{'─'*52}")
    total = 0
    sources = BLOG_SOURCES[:]
    random.shuffle(sources)
    for i, source in enumerate(sources):
        print(f"\n  [{i+1}/{len(sources)}] {source['name']}")
        total += process_source(source, BLOG_MAX_POSTS)
        if i < len(sources) - 1:
            wait = DELAY_BETWEEN + random.randint(0, RANDOM_EXTRA_DELAY)
            print(f"    ⏳ {wait}s...")
            time.sleep(wait)
    state["last_blog_cycle"] = datetime.now()
    print(f"\n  Blogs: {total} post(s) enviado(s)")


def run_news_cycle():
    now = datetime.now().strftime("%H:%M:%S")

    # Alterna entre as fontes de jornal a cada ciclo
    idx    = state["news_source_idx"] % len(NEWS_SOURCES)
    source = NEWS_SOURCES[idx]
    state["news_source_idx"] += 1

    print(f"\n{'='*52}")
    print(f"  [JORNAIS] Ciclo às {now} — {source['name']}")
    print(f"{'='*52}")

    posts = fetch_rss(source)
    new   = [p for p in posts if not is_seen(p["id"]) and is_relevant(p)]
    log(f"    [COMPARE] {len(posts)} RSS | {len(new)} novos relevantes")

    if not new:
        print(f"    — Nada novo em {source['name']}")
        state["last_news_cycle"] = datetime.now()
        return

    post = new[0]  # 1 notícia por ciclo
    ok   = send_to_discord(post)
    if ok:
        mark_seen(post["id"], post["source"], post["title"], post["link"])
        print(f"  ✓ [{post['source']}] {post['title'][:70]}")
        state["total_sent"] += 1
    else:
        print(f"  ✗ Falha: {post['title'][:60]}")

    state["last_news_cycle"] = datetime.now()
    print(f"\n  Próximo jornal: {NEWS_SOURCES[(idx+1) % len(NEWS_SOURCES)]['name']}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 52)
    print("  Bot de Notícias → Discord")
    print("=" * 52)
    print(f"Blogs  : {len(BLOG_SOURCES)} fontes, 1 post a cada 15min")
    print(f"Jornais: {len(NEWS_SOURCES)} fontes, 2 posts a cada 1h")
    print(f"Comandos: !ajuda !status !forcenow !pausar !resumir !fontes")
    print(f"Debug  : {'sim' if DEBUG else 'não (use --debug)'}")
    print()

    init_db()

    # Inicia thread de comandos se o token estiver configurado
    if DISCORD_BOT_TOKEN != "SEU_BOT_TOKEN_AQUI":
        t = threading.Thread(target=poll_commands, daemon=True)
        t.start()
    else:
        print("[WARN] DISCORD_BOT_TOKEN não configurado — comandos desativados")

    last_blog_run = 0
    last_news_run = 0  # roda imediatamente na primeira vez, depois espera 1h

    while True:
        now = time.time()

        if state["paused"] and not state["force_now"]:
            time.sleep(5)
            continue

        force = state["force_now"]
        if force:
            state["force_now"] = False

        # Ciclo de blogs (15min)
        if force or (now - last_blog_run >= BLOG_CYCLE_INTERVAL):
            try:
                run_blog_cycle()
            except Exception as e:
                print(f"[ERROR] Blogs: {e}")
            last_blog_run = time.time()
            remaining_news = max(0, NEWS_CYCLE_INTERVAL - (time.time() - last_news_run))
            next_news = datetime.fromtimestamp(time.time() + remaining_news).strftime("%H:%M:%S")
            print(f"  Próximo jornal às {next_news} (em {int(remaining_news//60)}min)")

        # Ciclo de jornais (1h) — nunca roda junto com blogs
        if not force and (now - last_news_run >= NEWS_CYCLE_INTERVAL):
            try:
                run_news_cycle()
            except Exception as e:
                print(f"[ERROR] Jornais: {e}")
            last_news_run = time.time()

        time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot encerrado.")
