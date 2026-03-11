"""
Bot de Notícias: X (Twitter) → RSS/Nitter → Discord
Monitora perfis do X via RSS e envia novidades no Discord.
"""

import feedparser
import requests
import sqlite3
import time
import json
import hashlib
import re
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURAÇÃO — edite aqui
# ─────────────────────────────────────────────

# Webhook do Discord (crie em: Canal > Configurações > Integrações > Webhooks)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI"

# Perfis do X que você quer monitorar (só o @, sem o @)
PROFILES = [
    "Reuters",
    "BBCBreaking",
    "g1",
    # adicione quantos quiser
]

# Instâncias públicas do Nitter (o bot tenta cada uma em ordem)
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
]

# Intervalo entre verificações (em segundos). 300 = 5 minutos
CHECK_INTERVAL = 300

# Número máximo de posts por perfil por rodada (evita spam no Discord)
MAX_POSTS_PER_PROFILE = 3

# Caminho do banco de dados local
DB_PATH = Path(__file__).parent / "seen_posts.db"

# ─────────────────────────────────────────────
# BANCO DE DADOS
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            id TEXT PRIMARY KEY,
            profile TEXT,
            title TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def is_seen(post_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT 1 FROM seen WHERE id = ?", (post_id,))
    result = cur.fetchone() is not None
    conn.close()
    return result

def mark_seen(post_id: str, profile: str, title: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO seen (id, profile, title) VALUES (?, ?, ?)",
        (post_id, profile, title)
    )
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# RSS / NITTER
# ─────────────────────────────────────────────

def fetch_rss(profile: str) -> list[dict]:
    """Tenta buscar o feed RSS do perfil via instâncias do Nitter."""
    for instance in NITTER_INSTANCES:
        url = f"{instance}/{profile}/rss"
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                posts = []
                for entry in feed.entries:
                    post_id = hashlib.md5(entry.get("id", entry.link).encode()).hexdigest()
                    title = clean_text(entry.get("title", ""))
                    link = entry.get("link", "")
                    published = entry.get("published", "")
                    # Filtra respostas (começa com @)
                    if title.startswith("@"):
                        continue
                    # Filtra RT
                    if title.startswith("RT "):
                        continue
                    posts.append({
                        "id": post_id,
                        "profile": profile,
                        "title": title,
                        "link": link,
                        "published": published,
                        "instance": instance,
                    })
                return posts
        except Exception as e:
            print(f"[WARN] {instance} falhou para @{profile}: {e}")
            continue
    print(f"[ERROR] Nenhuma instância funcionou para @{profile}")
    return []

def clean_text(text: str) -> str:
    """Remove tags HTML simples do título."""
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

# ─────────────────────────────────────────────
# DISCORD
# ─────────────────────────────────────────────

PROFILE_COLORS = [
    0x1DA1F2,  # azul Twitter
    0xFF6B6B,  # vermelho
    0x51CF66,  # verde
    0xFCC419,  # amarelo
    0x845EF7,  # roxo
]

def profile_color(profile: str) -> int:
    idx = sum(ord(c) for c in profile) % len(PROFILE_COLORS)
    return PROFILE_COLORS[idx]

def send_to_discord(post: dict):
    """Envia um post como embed no Discord."""
    embed = {
        "author": {
            "name": f"@{post['profile']} no X",
            "url": f"https://twitter.com/{post['profile']}",
            "icon_url": "https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        },
        "description": post["title"],
        "url": post["link"].replace(post.get("instance", ""), "https://twitter.com"),
        "color": profile_color(post["profile"]),
        "footer": {"text": post.get("published", "")},
        "timestamp": datetime.utcnow().isoformat(),
    }

    payload = {"embeds": [embed]}

    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        if resp.status_code in (200, 204):
            print(f"[OK] Enviado: @{post['profile']} — {post['title'][:60]}...")
        else:
            print(f"[ERROR] Discord retornou {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[ERROR] Falha ao enviar para Discord: {e}")

    # Respeita rate limit do Discord (5 webhooks/2s)
    time.sleep(0.5)

# ─────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────

def check_profiles():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Verificando {len(PROFILES)} perfis...")
    total_new = 0

    for profile in PROFILES:
        posts = fetch_rss(profile)
        new_posts = [p for p in posts if not is_seen(p["id"])]
        # Limita por rodada para não spammar
        new_posts = new_posts[:MAX_POSTS_PER_PROFILE]

        for post in reversed(new_posts):  # Ordem cronológica
            send_to_discord(post)
            mark_seen(post["id"], post["profile"], post["title"])
            total_new += 1

        if new_posts:
            print(f"  @{profile}: {len(new_posts)} novo(s)")
        else:
            print(f"  @{profile}: nada novo")

    print(f"Total enviado: {total_new} post(s)")

def main():
    print("=" * 50)
    print("  Bot de Notícias — X → Discord")
    print("=" * 50)
    print(f"Perfis monitorados: {', '.join('@' + p for p in PROFILES)}")
    print(f"Intervalo: {CHECK_INTERVAL}s ({CHECK_INTERVAL//60} min)")
    print()

    init_db()

    while True:
        try:
            check_profiles()
        except KeyboardInterrupt:
            print("\nBot encerrado.")
            break
        except Exception as e:
            print(f"[ERROR] Erro inesperado: {e}")

        print(f"Aguardando {CHECK_INTERVAL}s...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()