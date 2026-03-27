import io
import os
import tempfile
import wave
import numpy as np

from config import ANTHROPIC_API_KEY

_whisper_model = None


def mix_wav_files(wav_buffers: list[io.BytesIO]) -> io.BytesIO | None:
    """Mixa WAV buffers de múltiplos participantes em mono 16kHz para Whisper."""
    mixed = None
    for buf in wav_buffers:
        try:
            buf.seek(0)
            with wave.open(buf, "rb") as wf:
                framerate  = wf.getframerate()
                n_channels = wf.getnchannels()
                raw        = wf.readframes(wf.getnframes())

            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

            if n_channels == 2:
                arr = arr.reshape(-1, 2).mean(axis=1)

            if framerate != 16000:
                target_len = int(len(arr) * 16000 / framerate)
                arr = np.interp(
                    np.linspace(0, len(arr), target_len),
                    np.arange(len(arr)),
                    arr
                )

            if mixed is None:
                mixed = arr
            else:
                if len(arr) > len(mixed):
                    mixed = np.pad(mixed, (0, len(arr) - len(mixed)))
                else:
                    arr = np.pad(arr, (0, len(mixed) - len(arr)))
                mixed = np.clip(mixed + arr, -32768, 32767)

        except Exception as e:
            print(f"[AUDIO] Erro ao misturar faixa: {e}")

    if mixed is None:
        return None

    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(mixed.astype(np.int16).tobytes())
    out.seek(0)
    return out


def transcrever_whisper(wav_buf: io.BytesIO) -> str | None:
    """Transcreve com faster-whisper local (CPU)."""
    global _whisper_model
    try:
        from faster_whisper import WhisperModel
        if _whisper_model is None:
            print("[WHISPER] Carregando modelo 'small' (primeira vez, pode demorar)...")
            _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
            print("[WHISPER] Modelo carregado.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_buf.seek(0)
            tmp.write(wav_buf.read())
            tmp_path = tmp.name

        segments, info = _whisper_model.transcribe(tmp_path, language="pt", beam_size=5)
        os.unlink(tmp_path)

        texto = " ".join(seg.text.strip() for seg in segments)
        print(f"[WHISPER] Transcrição concluída ({len(texto)} chars, lang={info.language})")
        return texto.strip() or None
    except Exception as e:
        print(f"[WHISPER ERROR] {e}")
        return None


def resumir_claude(transcricao: str) -> str | None:
    """Gera resumo executivo + decisões usando Claude Haiku."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=(
                "Você é um assistente executivo. Analise a transcrição de uma reunião "
                "e produza um resumo estruturado em português brasileiro. Seja direto e objetivo."
            ),
            messages=[{"role": "user", "content": (
                f"Transcrição:\n\n{transcricao}\n\n"
                "Produza:\n"
                "1. **Resumo** (3-5 linhas)\n"
                "2. **Decisões tomadas** (bullet points)\n"
                "3. **Próximos passos / ações** (quem faz o quê)\n"
                "4. **Pendências / dúvidas em aberto** (se houver)"
            )}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[CLAUDE ERROR] {e}")
        return None
