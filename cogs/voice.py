"""
Cog de gravação de reuniões via voz.
Usa discord-ext-voice-recv + discord.py 2.7 (DAVE support).
Monkeypatch para compatibilidade DAVE ↔ voice_recv.
"""

import asyncio
import time
import discord
import discord.opus
from discord.ext import commands
from discord.ext import voice_recv
from datetime import datetime, timezone

from config import ANTHROPIC_API_KEY, RECORDINGS_DIR
from audio import mix_wav_files, transcrever_whisper, resumir_claude

# ─── Opus ────────────────────────────────────
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus("libopus.so.0")
        print("[OPUS] Carregado com sucesso")
    except Exception as e:
        print(f"[OPUS] FALHA: {e}")

# ─── DAVE Monkeypatch ────────────────────────
# voice_recv decripta transporte mas não DAVE (e2ee).
# Patch _process_packet para: 1) tentar DAVE decrypt, 2) fallback silence se opus falha.
# O vc reference é armazenado como global quando !reuniao conecta.
_active_vc = None  # set by cmd_reuniao

try:
    from discord.ext.voice_recv import opus as vr_opus
    from discord.ext.voice_recv import router as vr_router
    from discord.voice_state import davey

    # 1) Patch _process_packet: DAVE decrypt + opus fallback
    _orig_process_packet = vr_opus.PacketDecoder._process_packet

    def _patched_process_packet(self_decoder, packet):
        global _active_vc
        vc = _active_vc

        if vc and packet.decrypted_data:
            try:
                conn = vc._connection
                dave_sess = getattr(conn, 'dave_session', None)
                if dave_sess:
                    ssrc = packet.ssrc
                    user_id = vc._ssrc_to_id.get(ssrc, 0) if hasattr(vc, '_ssrc_to_id') else 0
                    if user_id:
                        decrypted = dave_sess.decrypt(
                            user_id, davey.MediaType.audio,
                            bytes(packet.decrypted_data))
                        if decrypted:
                            packet.decrypted_data = bytes(decrypted)
            except Exception:
                pass

        try:
            return _orig_process_packet(self_decoder, packet)
        except Exception:
            return packet, b'\x00' * 3840

    vr_opus.PacketDecoder._process_packet = _patched_process_packet

    # 2) Patch _do_run: wrap em try/except pra nunca crashar
    _orig_do_run = vr_router.PacketRouter._do_run

    def _patched_do_run(self_router):
        while not self_router._end_thread.is_set():
            try:
                self_router.waiter.wait()
                with self_router._lock:
                    for decoder in self_router.waiter.items:
                        try:
                            data = decoder.pop_data()
                            if data is not None:
                                self_router.sink.write(data.source, data)
                        except Exception:
                            pass  # skip bad packet, keep running
            except Exception:
                pass  # keep the router alive no matter what

    vr_router.PacketRouter._do_run = _patched_do_run

    print("[PATCH] DAVE decrypt + resilient router applied")

except Exception as e:
    print(f"[PATCH] Failed: {e}")
    import traceback
    traceback.print_exc()


class VoiceCog(commands.Cog):
    def __init__(self, bot, voice_session):
        self.bot           = bot
        self.voice_session = voice_session

    def _on_voice_packet(self, sink, voice_data):
        """Callback do BasicSink — acumula PCM por usuário."""
        vs = self.voice_session
        if not vs.get("active"):
            return
        uid = voice_data.source.id if voice_data.source else 0
        if uid not in vs["pcm_buffers"]:
            vs["pcm_buffers"][uid] = bytearray()
            print(f"[VOICE] Novo participante: {voice_data.source} ({len(voice_data.pcm)} bytes PCM)")
        vs["pcm_buffers"][uid].extend(voice_data.pcm)

    @commands.command(name="reuniao")
    async def cmd_reuniao(self, ctx):
        vs = self.voice_session

        if not ctx.author.voice:
            await ctx.send(embed=discord.Embed(
                description="❌ Entre em um canal de voz primeiro, depois chame `!reuniao`.",
                color=0xFF4444))
            return

        if vs["active"]:
            await ctx.send(embed=discord.Embed(
                description="⚠️ Já existe uma gravação em andamento. Use `!parar` para encerrar.",
                color=0xFCC419))
            return

        channel = ctx.author.voice.channel
        print(f"[VOICE] Conectando em: {channel.name}")

        if ctx.guild.voice_client:
            try:
                await ctx.guild.voice_client.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(2)

        try:
            global _active_vc
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient, timeout=30, self_deaf=False)
            _active_vc = vc  # Para o DAVE patch
            print(f"[VOICE] Conectado! is_connected={vc.is_connected()}")
        except Exception as e:
            print(f"[VOICE] FALHA: {type(e).__name__}: {e}")
            await ctx.send(embed=discord.Embed(
                description=f"❌ Não consegui entrar no canal de voz.\n`{type(e).__name__}: {e}`",
                color=0xFF4444))
            return

        vs["pcm_buffers"] = {}
        try:
            sink = voice_recv.BasicSink(self._on_voice_packet)
            vc.listen(sink)
            print("[VOICE] Gravação iniciada (BasicSink)")
        except Exception as e:
            print(f"[VOICE] FALHA listen: {e}")
            await ctx.send(embed=discord.Embed(
                description=f"❌ Falha ao iniciar gravação.\n`{e}`", color=0xFF4444))
            await vc.disconnect(force=True)
            return

        vs["vc"]           = vc
        vs["text_channel"] = ctx.channel
        vs["start_time"]   = datetime.now()
        vs["active"]       = True
        self._cleanup_old()

        await ctx.send(embed=discord.Embed(
            title="🎙️ Gravação iniciada",
            description=(
                f"**Canal:** {channel.name}\n"
                f"**Iniciada às:** {vs['start_time'].strftime('%H:%M:%S')}\n\n"
                "Use `!parar` quando quiser encerrar.\n"
                "O áudio fica salvo por **24h** para download."
            ),
            color=0x57F287, timestamp=datetime.now(timezone.utc)))

    @commands.command(name="parar")
    async def cmd_parar(self, ctx):
        vs = self.voice_session
        if not vs.get("active"):
            await ctx.send(embed=discord.Embed(
                description="❌ Nenhuma gravação em andamento.", color=0xFF4444))
            return

        vc = vs["vc"]
        vs["active"] = False
        try:
            vc.stop_listening()
        except Exception:
            pass
        try:
            await vc.disconnect(force=True)
        except Exception:
            pass
        vs["vc"] = None
        global _active_vc
        _active_vc = None

        duracao  = int((datetime.now() - vs["start_time"]).total_seconds()) if vs["start_time"] else 0
        text_ch  = vs["text_channel"]
        pcm_bufs = vs["pcm_buffers"]
        total_bytes = sum(len(b) for b in pcm_bufs.values())
        print(f"[VOICE] Parado: {len(pcm_bufs)} part., {duracao}s, {total_bytes} bytes PCM")

        await ctx.send(embed=discord.Embed(
            description=(
                f"⏹️ Gravação encerrada — **{duracao//60}min {duracao%60}s**\n"
                f"**{len(pcm_bufs)} participante(s)** capturado(s)\n"
                "⏳ Processando, aguarde..."
            ),
            color=0x5865F2, timestamp=datetime.now(timezone.utc)))

        if not pcm_bufs or total_bytes == 0:
            await text_ch.send(embed=discord.Embed(
                description="❌ Nenhum áudio foi capturado.", color=0xFF4444))
            return

        loop = asyncio.get_event_loop()
        wav_mixed = await loop.run_in_executor(None, self._pcm_to_wav, pcm_bufs)
        if wav_mixed is None:
            await text_ch.send(embed=discord.Embed(
                description="❌ Falha ao processar áudio.", color=0xFF4444))
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_path = RECORDINGS_DIR / f"reuniao_{ts}.wav"
        with open(wav_path, "wb") as f:
            f.write(wav_mixed.read())
        wav_mixed.seek(0)
        wav_size_mb = wav_path.stat().st_size / (1024 * 1024)

        if wav_size_mb < 25:
            wav_mixed.seek(0)
            await text_ch.send(
                content=f"🎙️ **Áudio** ({wav_size_mb:.1f} MB) — expira em **24h**",
                file=discord.File(wav_mixed, filename=f"reuniao_{ts}.wav"))

        wav_mixed.seek(0)
        transcricao = await loop.run_in_executor(None, transcrever_whisper, wav_mixed)
        if not transcricao:
            await text_ch.send(embed=discord.Embed(
                description="❌ Falha na transcrição.", color=0xFF4444))
            return

        await text_ch.send(embed=discord.Embed(
            description="🧠 Transcrição pronta. Gerando resumo...", color=0x5865F2))

        resumo = None
        if ANTHROPIC_API_KEY:
            resumo = await loop.run_in_executor(None, resumir_claude, transcricao)
        await self._enviar_embeds(text_ch, transcricao, resumo, duracao)

    def _pcm_to_wav(self, pcm_buffers):
        import io, wave, numpy as np
        mixed = None
        for uid, pcm_data in pcm_buffers.items():
            if not pcm_data:
                continue
            arr = np.frombuffer(bytes(pcm_data), dtype=np.int16).astype(np.float32)
            if len(arr) % 2 == 0:
                arr = arr.reshape(-1, 2).mean(axis=1)
            target_len = int(len(arr) * 16000 / 48000)
            if target_len == 0:
                continue
            arr = np.interp(np.linspace(0, len(arr), target_len), np.arange(len(arr)), arr)
            if mixed is None:
                mixed = arr
            else:
                if len(arr) > len(mixed):
                    mixed = np.pad(mixed, (0, len(arr) - len(mixed)))
                else:
                    arr = np.pad(arr, (0, len(mixed) - len(arr)))
                mixed = np.clip(mixed + arr, -32768, 32767)
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

    async def _enviar_embeds(self, channel, transcricao, resumo, duracao_s):
        agora  = datetime.now(timezone.utc).isoformat()
        titulo = f"📋 Reunião — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        embeds = []
        if resumo:
            embeds.append({"title": titulo, "description": resumo[:4000], "color": 0x5865F2,
                           "footer": {"text": f"Duração: {duracao_s//60}min {duracao_s%60}s"}, "timestamp": agora})
        MAX = 3900
        partes = [transcricao[i:i+MAX] for i in range(0, len(transcricao), MAX)]
        for idx, parte in enumerate(partes):
            label = "📝 Transcrição" + (f" ({idx+1}/{len(partes)})" if len(partes) > 1 else "")
            embeds.append({"title": label, "description": parte, "color": 0x2D3436, "timestamp": agora})
        for i in range(0, len(embeds), 10):
            await channel.send(embeds=[discord.Embed.from_dict(e) for e in embeds[i:i+10]])

    def _cleanup_old(self):
        now = time.time()
        for f in RECORDINGS_DIR.glob("*.wav"):
            if now - f.stat().st_mtime > 86400:
                f.unlink()
                print(f"[CLEANUP] Removido {f.name}")


def setup(bot, voice_session):
    bot.add_cog(VoiceCog(bot, voice_session))
