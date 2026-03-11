"""
Bot de Notícias: X (Twitter) → Twscrape → Discord
- Usa Twscrape para buscar tweets sem API oficial
- Ciclo mínimo de 1 hora
- Alterna perfis com pausas aleatórias
- Só envia posts ainda não registrados no banco local
- Use --debug para logs detalhados
"""

import asyncio
import sqlite3
import time
import random
import sys
import requests
from datetime import datetime, timezone
from pathlib import Path

import twscrape

# ─────────────────────────────────────────────
# CONFIGURAÇÃO — edite aqui
# ─────────────────────────────────────────────

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI"

# Conta do X usada pelo twscrape para autenticar
# Recomendado: crie uma conta secundária só pra isso
X_ACCOUNTS = [
    {
        "cookies":  "auth_token=SEU_AUTH_TOKEN; ct0=SEU_CT0",
        "username": "SEU_USUARIO_X",
        "password": "SUA_SENHA_X",
        "email":    "SEU_EMAIL_X",
    },
]

PROFILES = [
    "CloudflareDev",
    "Polymarket",
    "claudeai",
    "trq212",
    "Reuters",
]

CYCLE_INTERVAL         = 3600  # segundos entre ciclos (1 hora)
DELAY_BETWEEN_PROFILES = 20    # pausa base entre perfis (segundos)
RANDOM_EXTRA_DELAY     = 10    # pausa extra aleatória máxima (segundos)
MAX_POSTS_PER_PROFILE  = 3     # máximo de posts novos por perfil por ciclo
TWEETS_TO_FETCH        = 20    # quantos tweets buscar por perfil por ciclo

DB_PATH = Path(__file__).parent / "seen_posts.db"
DEBUG   = "--debug" in sys.argv

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
            profile   TEXT NOT NULL,
            title     TEXT,
            link      TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    log(f"[DB] Banco inicializado em {DB_PATH}")

def is_seen(post_id: str) -> bool:
    conn   = sqlite3.connect(DB_PATH)
    result = conn.execute("SELECT 1 FROM seen WHERE id = ?", (post_id,)).fetchone()
    conn.close()
    return result is not None

def mark_seen(post_id: str, profile: str, title: str, link: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO seen (id, profile, title, link) VALUES (?, ?, ?, ?)",
        (post_id, profile, title, link)
    )
    conn.commit()
    conn.close()

def count_seen(profile: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    n    = conn.execute("SELECT COUNT(*) FROM seen WHERE profile = ?", (profile,)).fetchone()[0]
    conn.close()
    return n

# ─────────────────────────────────────────────
# TWSCRAPE
# ─────────────────────────────────────────────

async def setup_accounts(api: twscrape.API):
    """Adiciona contas via cookies (mais confiável que login automático)."""
    for acc in X_ACCOUNTS:
        await api.pool.add_account(
            username=acc["username"],
            password=acc["password"],
            email=acc["email"],
            email_password=acc.get("email_password", acc["password"]),
            cookies=acc.get("cookies", ""),
        )
    # Se já temos cookies, não precisa fazer login
    has_cookies = any(acc.get("cookies") for acc in X_ACCOUNTS)
    if not has_cookies:
        await api.pool.login_all()
        log("[AUTH] Login automático realizado")
    else:
        log("[AUTH] Usando cookies — login automático pulado")

async def fetch_tweets(api: twscrape.API, profile: str) -> list[dict]:
    """Busca os tweets mais recentes de um perfil."""
    posts = []
    try:
        user = await api.user_by_login(profile)
        if not user:
            print(f"    [ERROR] Perfil @{profile} não encontrado")
            return []

        async for tweet in api.user_tweets(user.id, limit=TWEETS_TO_FETCH):
            # Ignora replies e retweets
            if tweet.inReplyToTweetId:
                log(f"    [SKIP] Reply: {tweet.rawContent[:60]}")
                continue
            if tweet.retweetedTweet:
                log(f"    [SKIP] RT: {tweet.rawContent[:60]}")
                continue

            post_id = str(tweet.id)
            link    = f"https://twitter.com/{profile}/status/{tweet.id}"

            posts.append({
                "id":        post_id,
                "profile":   profile,
                "title":     tweet.rawContent,
                "link":      link,
                "published": tweet.date.strftime("%d/%m/%Y %H:%M") if tweet.date else "",
            })

        log(f"    [FETCH] {len(posts)} tweets válidos de @{profile}")
    except Exception as e:
        print(f"    [ERROR] Falha ao buscar @{profile}: {e}")

    return posts

# ─────────────────────────────────────────────
# DISCORD
# ─────────────────────────────────────────────

PROFILE_COLORS = [0x1DA1F2, 0xFF6B6B, 0x51CF66, 0xFCC419, 0x845EF7]

def profile_color(profile: str) -> int:
    return PROFILE_COLORS[sum(ord(c) for c in profile) % len(PROFILE_COLORS)]

def send_to_discord(post: dict) -> bool:
    embed = {
        "author": {
            "name":     f"@{post['profile']} no X",
            "url":      f"https://twitter.com/{post['profile']}",
            "icon_url": "https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        },
        "description": post["title"],
        "url":          post["link"],
        "color":        profile_color(post["profile"]),
        "footer":       {
        "cookies":  "auth_token=SEU_AUTH_TOKEN; ct0=SEU_CT0","text": post.get("published", "")},
        "timestamp":    datetime.utcnow().isoformat(),
    }
    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=10
        )
        time.sleep(0.5)  # rate limit do Discord
        if resp.status_code in (200, 204):
            return True
        print(f"    [ERROR] Discord {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"    [ERROR] {e}")
        return False

# ─────────────────────────────────────────────
# LÓGICA PRINCIPAL
# ─────────────────────────────────────────────

async def process_profile(api: twscrape.API, profile: str) -> int:
    log(f"    [DB] @{profile} tem {count_seen(profile)} post(s) no banco")

    posts = await fetch_tweets(api, profile)
    if not posts:
        return 0

    new_posts  = [p for p in posts if not is_seen(p["id"])]
    seen_count = len(posts) - len(new_posts)

    log(f"    [COMPARE] {len(posts)} tweets | {seen_count} já vistos | {len(new_posts)} novos")

    if not new_posts:
        print(f"    — Nada novo (todos os {len(posts)} tweets já foram enviados antes)")
        return 0

    to_send = new_posts[:MAX_POSTS_PER_PROFILE]
    sent    = 0

    for post in reversed(to_send):  # ordem cronológica
        ok = send_to_discord(post)
        if ok:
            mark_seen(post["id"], post["profile"], post["title"], post["link"])
            print(f"    ✓ {post['title'][:80]}")
            sent += 1
        else:
            print(f"    ✗ Falha: {post['title'][:60]}")

    if len(new_posts) > MAX_POSTS_PER_PROFILE:
        print(f"    ⚠ {len(new_posts) - MAX_POSTS_PER_PROFILE} novo(s) adiado(s) pro próximo ciclo")

    return sent


async def run_cycle(api: twscrape.API):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*52}")
    print(f"  Ciclo iniciado às {now}")
    print(f"{'='*52}")

    total_new      = 0
    profiles_order = PROFILES[:]
    random.shuffle(profiles_order)

    for i, profile in enumerate(profiles_order):
        print(f"\n  [{i+1}/{len(profiles_order)}] @{profile}")
        sent       = await process_profile(api, profile)
        total_new += sent

        if i < len(profiles_order) - 1:
            wait = DELAY_BETWEEN_PROFILES + random.randint(0, RANDOM_EXTRA_DELAY)
            print(f"    ⏳ Aguardando {wait}s...")
            await asyncio.sleep(wait)

    print(f"\n  {'─'*48}")
    print(f"  Ciclo concluído — {total_new} post(s) enviado(s)")
    print(f"  {'─'*48}")


async def main():
    print("=" * 52)
    print("  Bot de Notícias — X → Discord (Twscrape)")
    print("=" * 52)
    print(f"Perfis : {', '.join('@' + p for p in PROFILES)}")
    print(f"Ciclo  : a cada {CYCLE_INTERVAL // 60} min")
    print(f"Delay  : {DELAY_BETWEEN_PROFILES}–{DELAY_BETWEEN_PROFILES + RANDOM_EXTRA_DELAY}s entre perfis")
    print(f"Debug  : {'sim' if DEBUG else 'não (use --debug)'}")
    print()

    init_db()

    api = twscrape.API()
    await setup_accounts(api)

    while True:
        cycle_start = time.time()

        try:
            await run_cycle(api)
        except KeyboardInterrupt:
            print("\nBot encerrado.")
            break
        except Exception as e:
            print(f"[ERROR] Erro inesperado: {e}")

        elapsed   = time.time() - cycle_start
        remaining = max(0, CYCLE_INTERVAL - elapsed)

        if remaining > 0:
            next_time = datetime.fromtimestamp(time.time() + remaining).strftime("%H:%M:%S")
            print(f"\nPróximo ciclo às {next_time} "
                  f"(em {int(remaining // 60)}min {int(remaining % 60)}s)\n")
            await asyncio.sleep(remaining)

if __name__ == "__main__":
    asyncio.run(main())
