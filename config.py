import os
import sys
from pathlib import Path

# ─── Variáveis de ambiente ───────────────────
DISCORD_WEBHOOK_URL      = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOKEN        = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID       = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
ANTHROPIC_API_KEY        = os.getenv("ANTHROPIC_API_KEY", "")
OPORTUNIDADES_CHANNEL_ID  = int(os.getenv("OPORTUNIDADES_CHANNEL_ID", "0"))
OPORTUNIDADES_WEBHOOK_URL = os.getenv("OPORTUNIDADES_WEBHOOK_URL", "")

DEBUG = "--debug" in sys.argv

# ─── Fontes RSS — Blogs oficiais (1h, 1 post) ──
BLOG_SOURCES = [
    {"name": "Anthropic News",    "color": 0xCC785C,
     "rss": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml"},
    {"name": "Google AI Blog",    "color": 0x4285F4,
     "rss": "https://blog.google/technology/ai/rss/"},
    {"name": "DeepMind Blog",     "color": 0x1A73E8,
     "rss": "https://deepmind.google/blog/rss.xml"},
]

# ─── Fontes RSS — Jornais AI (1h, rotativo) ─────
NEWS_SOURCES = [
    {"name": "The Verge AI",      "color": 0x5100FF,
     "rss": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "TechCrunch AI",     "color": 0x0A7D3E,
     "rss": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "Wired AI",          "color": 0x000000,
     "rss": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"name": "Axios AI",          "color": 0x0066CC,
     "rss": "https://api.axios.com/feed/technology"},
    {"name": "The Rundown AI",    "color": 0x6C5CE7,
     "rss": "https://www.therundown.ai/feed"},
    {"name": "Product Hunt AI",   "color": 0xDA552F,
     "rss": "https://www.producthunt.com/feed?category=artificial-intelligence"},
    # Reddit underground AI
    {"name": "r/LocalLLaMA",      "color": 0xFF6B6B,
     "rss": "https://www.reddit.com/r/LocalLLaMA/hot/.rss"},
    {"name": "r/singularity",     "color": 0xA29BFE,
     "rss": "https://www.reddit.com/r/singularity/hot/.rss"},
    {"name": "r/ClaudeAI",        "color": 0xCC785C,
     "rss": "https://www.reddit.com/r/ClaudeAI/hot/.rss"},
    {"name": "r/ollama",          "color": 0x55EFC4,
     "rss": "https://www.reddit.com/r/ollama/hot/.rss"},
    {"name": "r/artificial",      "color": 0x636E72,
     "rss": "https://www.reddit.com/r/artificial/hot/.rss"},
]

# ─── Constantes ──────────────────────────────
BLOG_CYCLE_INTERVAL = 3600
NEWS_CYCLE_INTERVAL = 3600
BLOG_MAX_POSTS      = 1
NEWS_MAX_POSTS      = 1
DELAY_BETWEEN       = 5
RANDOM_EXTRA_DELAY  = 5

# ─── Paths ───────────────────────────────────
DB_PATH = Path("/app/data/seen_posts.db") if Path("/app/data").exists() else Path(__file__).parent / "seen_posts.db"
RECORDINGS_DIR = Path("/app/data/recordings") if Path("/app/data").exists() else Path(__file__).parent / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Filtro de relevância ────────────────────
# Todas as fontes agora são AI-focused, então são trusted
TRUSTED_SOURCES = [
    "Anthropic", "Google AI", "DeepMind",
    "Verge", "TechCrunch", "Wired", "Axios",
    "Rundown", "Product Hunt",
    "LocalLLaMA", "singularity", "ClaudeAI", "ollama", "artificial",
]

KEYWORDS_TECH = [
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "gpt", "claude", "gemini", "copilot", "chatbot", "neural network",
    "model", "inference", "fine-tuning", "embedding", "agent", "rag",
    "generative", "diffusion", "transformer", "openai", "anthropic",
    "google deepmind", "microsoft", "meta ai", "nvidia",
    "inteligência artificial", "ia generativa", "modelo de linguagem",
]

KEYWORDS_BLOCK = [
    "sports", "football", "soccer", "basketball", "nfl", "nba",
    "celebrity", "kardashian", "entertainment", "grammy", "oscar",
    "fashion", "beauty", "cooking", "recipe", "travel", "tourism",
    "weather", "horoscope", "zodiac", "reality tv",
]

# ─── Oportunidades de projeto (JONES) ────────
# Workana/99freelas/Upwork não têm RSS público — fontes validadas:
OPPORTUNITIES_SOURCES = [
    {"name": "RemoteOK",          "color": 0x00B894,
     "rss": "https://remoteok.com/remote-dev-jobs.rss"},
    {"name": "We Work Remotely",  "color": 0x6C5CE7,
     "rss": "https://weworkremotely.com/categories/remote-programming-jobs.rss"},
    {"name": "Jobicy Dev",        "color": 0x0984E3,
     "rss": "https://jobicy.com/?feed=job_feed&job_categories=engineering"},
    {"name": "Reddit r/forhire",  "color": 0xFF4500,
     "rss": "https://www.reddit.com/r/forhire/search.rss?q=flair%3AHiring&restrict_sr=on&sort=new"},
]

KEYWORDS_OPPORTUNITIES = [
    "react", "python", "node", "typescript", "next", "vue", "django", "flask",
    "mobile", "app", "api", "backend", "frontend", "fullstack", "full-stack",
    "website", "software", "javascript", "php", "laravel", "developer", "engineer",
    "web", "ios", "android", "kotlin", "swift", "ruby", "rails",
]
