"""
Transcritor de Calls → Discord
─────────────────────────────────────────────
Uso:
  python transcrever.py                  → grava do microfone até Ctrl+C
  python transcrever.py reuniao.mp3      → transcreve arquivo de áudio
  python transcrever.py --no-discord     → só imprime no terminal

Requer:
  pip install openai sounddevice soundfile numpy

Variáveis de ambiente (ou editar aqui embaixo):
  OPENAI_API_KEY
  DISCORD_WEBHOOK_URL   (mesmo do bot de notícias, ou um webhook separado)
"""

import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG — edite aqui ou use variáveis de ambiente
# ─────────────────────────────────────────────

OPENAI_API_KEY       = os.getenv("OPENAI_API_KEY", "SUA_OPENAI_KEY_AQUI")
DISCORD_WEBHOOK_URL  = os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI")
RESUMO_COM_IA        = True   # False = só transcreve, sem resumo
SAMPLE_RATE          = 16000  # Hz — padrão Whisper
MAX_GRAVACAO_MIN     = 120    # segurança: para de gravar após N minutos


# ─────────────────────────────────────────────
# GRAVAÇÃO DE ÁUDIO
# ─────────────────────────────────────────────

def gravar_audio(caminho_saida: str) -> bool:
    """Grava áudio do microfone até Ctrl+C. Salva em WAV."""
    try:
        import sounddevice as sd
        import soundfile as sf
        import numpy as np
    except ImportError:
        print("[ERRO] Instale as dependências: pip install sounddevice soundfile numpy")
        return False

    chunks = []
    parar  = threading.Event()

    def callback(indata, frames, time, status):
        if status:
            print(f"[WARN] {status}")
        chunks.append(indata.copy())

    print(f"\n🎙️  Gravando... (Ctrl+C para parar e transcrever)\n")
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", callback=callback):
            sd.sleep(MAX_GRAVACAO_MIN * 60 * 1000)
    except KeyboardInterrupt:
        pass

    if not chunks:
        print("[ERRO] Nenhum áudio gravado.")
        return False

    audio = np.concatenate(chunks, axis=0)
    sf.write(caminho_saida, audio, SAMPLE_RATE)
    duracao = len(audio) / SAMPLE_RATE
    print(f"\n✅ Gravação finalizada: {duracao:.0f}s → {caminho_saida}")
    return True


# ─────────────────────────────────────────────
# TRANSCRIÇÃO (Whisper via OpenAI API)
# ─────────────────────────────────────────────

def transcrever_audio(caminho_audio: str) -> str | None:
    """Envia o arquivo para a API Whisper da OpenAI e retorna a transcrição."""
    try:
        from openai import OpenAI
    except ImportError:
        print("[ERRO] Instale: pip install openai")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    print(f"\n🔄 Transcrevendo '{Path(caminho_audio).name}'...")

    with open(caminho_audio, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="pt",
            response_format="text",
        )

    texto = resp.strip() if isinstance(resp, str) else resp.text.strip()
    print(f"✅ Transcrição concluída ({len(texto)} chars)")
    return texto


# ─────────────────────────────────────────────
# RESUMO COM IA (Claude via API)
# ─────────────────────────────────────────────

def resumir_transcricao(transcricao: str) -> str | None:
    """Gera resumo executivo + decisões usando Claude."""
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    print("\n🧠 Gerando resumo com IA...")

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um assistente executivo. Analise a transcrição de uma reunião "
                    "e produza um resumo estruturado em português brasileiro. "
                    "Seja direto e objetivo."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Transcrição da reunião:\n\n{transcricao}\n\n"
                    "Produza:\n"
                    "1. **Resumo** (3-5 linhas do que foi discutido)\n"
                    "2. **Decisões tomadas** (lista com bullet points)\n"
                    "3. **Próximos passos / ações** (quem faz o quê)\n"
                    "4. **Pendências / dúvidas em aberto** (se houver)"
                ),
            },
        ],
        max_tokens=1000,
    )

    resumo = resp.choices[0].message.content.strip()
    print("✅ Resumo gerado")
    return resumo


# ─────────────────────────────────────────────
# ENVIO PARA O DISCORD
# ─────────────────────────────────────────────

def enviar_discord(transcricao: str, resumo: str | None, nome_arquivo: str):
    """Envia transcrição e resumo como embeds no Discord."""
    import requests

    agora = datetime.now(timezone.utc).isoformat()
    titulo = f"📋 Call — {datetime.now().strftime('%d/%m/%Y %H:%M')}"

    embeds = []

    # Embed 1 — Resumo (se disponível)
    if resumo:
        embeds.append({
            "title":       titulo,
            "description": resumo[:4000],
            "color":       0x5865F2,
            "footer":      {"text": f"Arquivo: {nome_arquivo}"},
            "timestamp":   agora,
        })

    # Embed 2 — Transcrição completa (dividida se necessário)
    MAX = 4000
    partes = [transcricao[i:i+MAX] for i in range(0, len(transcricao), MAX)]
    for idx, parte in enumerate(partes):
        label = f"📝 Transcrição completa" + (f" (parte {idx+1}/{len(partes)})" if len(partes) > 1 else "")
        embeds.append({
            "title":       label if idx == 0 else f"↳ Transcrição (parte {idx+1})",
            "description": parte,
            "color":       0x2D3436,
            "timestamp":   agora,
        })

    # Envia em lotes de 10 embeds
    for i in range(0, len(embeds), 10):
        lote = embeds[i:i+10]
        resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": lote}, timeout=15)
        if resp.status_code not in (200, 204):
            print(f"[ERRO] Discord {resp.status_code}: {resp.text[:200]}")
            return False

    print(f"✅ Enviado para o Discord ({len(embeds)} embed(s))")
    return True


# ─────────────────────────────────────────────
# SALVAR LOCALMENTE
# ─────────────────────────────────────────────

def salvar_local(transcricao: str, resumo: str | None, nome_base: str):
    """Salva .txt com transcrição e resumo na mesma pasta do script."""
    pasta = Path(__file__).parent / "transcricoes"
    pasta.mkdir(exist_ok=True)

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = pasta / f"{ts}_{nome_base}.txt"

    with open(path, "w", encoding="utf-8") as f:
        if resumo:
            f.write("═" * 60 + "\n")
            f.write("RESUMO\n")
            f.write("═" * 60 + "\n\n")
            f.write(resumo + "\n\n")
        f.write("═" * 60 + "\n")
        f.write("TRANSCRIÇÃO COMPLETA\n")
        f.write("═" * 60 + "\n\n")
        f.write(transcricao + "\n")

    print(f"💾 Salvo em: {path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    sem_discord = "--no-discord" in sys.argv
    args        = [a for a in sys.argv[1:] if not a.startswith("--")]

    if OPENAI_API_KEY == "SUA_OPENAI_KEY_AQUI":
        print("[ERRO] Configure OPENAI_API_KEY no script ou como variável de ambiente.")
        sys.exit(1)

    # Determina arquivo de áudio
    if args:
        caminho_audio = args[0]
        if not Path(caminho_audio).exists():
            print(f"[ERRO] Arquivo não encontrado: {caminho_audio}")
            sys.exit(1)
        nome_base = Path(caminho_audio).stem
    else:
        # Grava do microfone
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        caminho_audio = tmp.name
        tmp.close()
        ok = gravar_audio(caminho_audio)
        if not ok:
            sys.exit(1)
        nome_base = "gravacao"

    # Transcreve
    transcricao = transcrever_audio(caminho_audio)
    if not transcricao:
        print("[ERRO] Falha na transcrição.")
        sys.exit(1)

    # Resumo
    resumo = resumir_transcricao(transcricao) if RESUMO_COM_IA else None

    # Exibe no terminal
    print("\n" + "═" * 60)
    if resumo:
        print("RESUMO:\n")
        print(resumo)
        print("\n" + "─" * 60)
    print("TRANSCRIÇÃO:\n")
    print(transcricao[:2000] + ("..." if len(transcricao) > 2000 else ""))
    print("═" * 60)

    # Salva localmente
    salvar_local(transcricao, resumo, nome_base)

    # Envia pro Discord
    if not sem_discord and DISCORD_WEBHOOK_URL != "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI":
        enviar_discord(transcricao, resumo, nome_base)
    elif sem_discord:
        print("ℹ️  --no-discord: não enviado ao Discord")
    else:
        print("[WARN] DISCORD_WEBHOOK_URL não configurado — não enviado ao Discord")


if __name__ == "__main__":
    main()
