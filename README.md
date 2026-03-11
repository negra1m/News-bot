# 🤖 Bot de Notícias — X → Discord

Monitora perfis do X (Twitter) via RSS (Nitter) e envia as novidades em um canal do Discord.

---

## ⚙️ Configuração (3 passos)

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Criar o Webhook no Discord
1. Abra o canal do Discord onde quer receber as notícias
2. Clique em **Configurações do Canal** (ícone de engrenagem)
3. Vá em **Integrações → Webhooks → Novo Webhook**
4. Copie a URL do webhook

### 3. Editar o `bot.py`
Abra `bot.py` e edite a seção `CONFIGURAÇÃO`:

```python
# Cole aqui a URL do webhook
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."

# Perfis que você quer monitorar
PROFILES = [
    "Reuters",
    "BBCBreaking",
    "g1",
    "folha",
    # adicione quantos quiser...
]

# Intervalo de verificação em segundos (padrão: 5 minutos)
CHECK_INTERVAL = 300
```

---

## ▶️ Executar

```bash
python bot.py
```

---

## 🔄 Rodar em segundo plano (Linux/Mac)

```bash
# Com nohup
nohup python bot.py &

# Ou com tmux
tmux new -s newsbot
python bot.py
# Ctrl+B depois D para desatachar
```

## 🪟 Rodar em segundo plano (Windows)

```powershell
# Criar uma task agendada ou simplesmente:
pythonw bot.py
```

---

## 📋 Como funciona

```
Perfis configurados
       ↓
  Nitter (RSS)          ← instâncias públicas gratuitas
       ↓
  Filtragem             ← remove respostas e RTs
       ↓
  Deduplicação          ← SQLite local (seen_posts.db)
       ↓
  Discord Webhook       ← embed com autor, texto e link
```

---

## ⚠️ Avisos

- **Nitter** são instâncias públicas mantidas por voluntários e podem cair. O bot tenta múltiplas automaticamente.
- O bot filtra respostas (`@alguem ...`) e retweets (`RT ...`) por padrão.
- `seen_posts.db` é criado automaticamente na mesma pasta do bot.
- Cada perfil envia no máximo **3 posts por rodada** para evitar spam (configurável via `MAX_POSTS_PER_PROFILE`).
