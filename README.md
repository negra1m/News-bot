# 🤖 Bot de Notícias — X → Discord (Twscrape)

Monitora perfis do X via Twscrape e envia novidades no Discord.

---

## ⚙️ Configuração

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Criar o Webhook no Discord
1. Canal → **Configurações → Integrações → Webhooks → Novo Webhook**
2. Copie a URL do webhook

### 3. Criar uma conta secundária no X
Recomendado criar uma conta só pra isso (ex: um email novo).
Evita risco de suspender sua conta principal.

### 4. Editar o `bot.py`
```python
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."

X_ACCOUNTS = [
    {
        "username": "minha_conta_bot",
        "password": "minha_senha",
        "email":    "email@exemplo.com",
    },
]

PROFILES = [
    "CloudflareDev",
    "Polymarket",
    "claudeai",
    "trq212",
    "Reuters",
]
```

---

## ▶️ Executar

```bash
# Normal
python bot.py

# Com logs detalhados
python bot.py --debug
```

---

## 🔄 Rodar em segundo plano

```bash
# Linux/Mac
nohup python bot.py &

# Windows
pythonw bot.py
```

---

## ⚠️ Avisos

- Use uma **conta secundária** do X — nunca a principal
- O Twscrape armazena o login em `accounts.db` na mesma pasta
- Se a conta for suspensa, crie outra e atualize o `bot.py`
- O bot ignora replies e retweets automaticamente
