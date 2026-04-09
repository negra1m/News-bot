"""
Cog de configuração em runtime — comandos !conf.

!conf                              → mostra config atual
!conf canal opp <id>               → define canal de oportunidades
!conf opp list/add/del             → gerenciar fontes de oportunidades
!conf kw list/add/del              → gerenciar keywords de oportunidades
!conf reddit add <sub> opp|news    → adicionar subreddit (oportunidades ou notícias)
!conf reddit del <sub> opp|news    → remover subreddit
!conf reddit list                  → listar subreddits ativos
!conf reset                        → volta tudo ao padrão
"""

import discord
from discord.ext import commands
from datetime import datetime, timezone

import runtime_config


def _ts():
    return datetime.now(timezone.utc)

def _embed(desc, color=0x5865F2):
    return discord.Embed(description=desc, color=color, timestamp=_ts())


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ─── !conf (raiz) ────────────────────────

    @commands.group(name="conf", invoke_without_command=True)
    async def cmd_conf(self, ctx):
        ch_id    = runtime_config.get_opp_channel_id()
        sources  = runtime_config.get_opp_sources()
        keywords = runtime_config.get_opp_keywords()

        fontes_txt = "\n".join(f"  • **{s['name']}** — `{s['rss'][:60]}...`" for s in sources) \
                     or "  (nenhuma)"
        kw_txt = ", ".join(f"`{k}`" for k in keywords[:15])
        if len(keywords) > 15:
            kw_txt += f" … +{len(keywords)-15} mais"

        desc = (
            "**⚙️ Configuração atual**\n\n"
            f"**Canal oportunidades:** <#{ch_id}> (`{ch_id}`)\n\n"
            f"**Fontes de oportunidades ({len(sources)}):**\n{fontes_txt}\n\n"
            f"**Keywords ({len(keywords)}):**\n{kw_txt}\n\n"
            "Use `!conf opp`, `!conf kw`, `!conf canal` ou `!conf reset`."
        )
        await ctx.send(embed=_embed(desc))

    # ─── !conf canal ─────────────────────────

    @cmd_conf.group(name="canal", invoke_without_command=True)
    async def conf_canal(self, ctx):
        await ctx.send(embed=_embed(
            "Uso: `!conf canal opp <channel_id>`\n"
            "Exemplo: `!conf canal opp 1351997270861811742`",
            color=0xFCC419))

    @conf_canal.command(name="opp")
    async def conf_canal_opp(self, ctx, channel_id: int):
        ch = self.bot.get_channel(channel_id)
        if not ch:
            await ctx.send(embed=_embed(
                f"❌ Canal `{channel_id}` não encontrado. Verifique o ID.", color=0xFF4444))
            return
        runtime_config.set_opp_channel_id(channel_id)
        await ctx.send(embed=_embed(f"✅ Canal de oportunidades definido para <#{channel_id}>.", color=0x51CF66))

    # ─── !conf opp ───────────────────────────

    @cmd_conf.group(name="opp", invoke_without_command=True)
    async def conf_opp(self, ctx):
        sources = runtime_config.get_opp_sources()
        if not sources:
            await ctx.send(embed=_embed("Nenhuma fonte configurada.", color=0xFCC419))
            return
        lines = [f"`{i+1}.` **{s['name']}**\n   `{s['rss']}`" for i, s in enumerate(sources)]
        await ctx.send(embed=_embed(
            "**📡 Fontes de oportunidades:**\n\n" + "\n\n".join(lines) +
            "\n\n`!conf opp add <nome> <url>` · `!conf opp del <nome>`"))

    @conf_opp.command(name="list")
    async def conf_opp_list(self, ctx):
        await self.conf_opp(ctx)

    @conf_opp.command(name="add")
    async def conf_opp_add(self, ctx, nome: str, url: str):
        if not url.startswith("http"):
            await ctx.send(embed=_embed("❌ URL inválida.", color=0xFF4444))
            return
        sources = list(runtime_config.get_opp_sources())
        if any(s["name"].lower() == nome.lower() for s in sources):
            await ctx.send(embed=_embed(f"❌ Já existe uma fonte chamada **{nome}**.", color=0xFF4444))
            return
        sources.append({"name": nome, "color": 0xF39C12, "rss": url})
        runtime_config.set_opp_sources(sources)
        await ctx.send(embed=_embed(f"✅ Fonte **{nome}** adicionada.", color=0x51CF66))

    @conf_opp.command(name="del")
    async def conf_opp_del(self, ctx, *, nome: str):
        sources = list(runtime_config.get_opp_sources())
        nova = [s for s in sources if s["name"].lower() != nome.lower()]
        if len(nova) == len(sources):
            await ctx.send(embed=_embed(f"❌ Fonte **{nome}** não encontrada.", color=0xFF4444))
            return
        runtime_config.set_opp_sources(nova)
        await ctx.send(embed=_embed(f"✅ Fonte **{nome}** removida.", color=0x51CF66))

    # ─── !conf kw ────────────────────────────

    @cmd_conf.group(name="kw", invoke_without_command=True)
    async def conf_kw(self, ctx):
        keywords = runtime_config.get_opp_keywords()
        kw_fmt = "\n".join(
            "  " + "  ".join(f"`{kw}`" for kw in keywords[i:i+6])
            for i in range(0, len(keywords), 6)
        )
        await ctx.send(embed=_embed(
            f"**🔍 Keywords de oportunidades ({len(keywords)}):**\n\n{kw_fmt}\n\n"
            "`!conf kw add <palavra>` · `!conf kw del <palavra>`"))

    @conf_kw.command(name="list")
    async def conf_kw_list(self, ctx):
        await self.conf_kw(ctx)

    @conf_kw.command(name="add")
    async def conf_kw_add(self, ctx, *, keyword: str):
        keyword = keyword.strip().lower()
        kws = list(runtime_config.get_opp_keywords())
        if keyword in kws:
            await ctx.send(embed=_embed(f"— Keyword `{keyword}` já existe.", color=0xFCC419))
            return
        kws.append(keyword)
        runtime_config.set_opp_keywords(kws)
        await ctx.send(embed=_embed(f"✅ Keyword `{keyword}` adicionada. ({len(kws)} total)", color=0x51CF66))

    @conf_kw.command(name="del")
    async def conf_kw_del(self, ctx, *, keyword: str):
        keyword = keyword.strip().lower()
        kws = list(runtime_config.get_opp_keywords())
        if keyword not in kws:
            await ctx.send(embed=_embed(f"❌ Keyword `{keyword}` não encontrada.", color=0xFF4444))
            return
        kws.remove(keyword)
        runtime_config.set_opp_keywords(kws)
        await ctx.send(embed=_embed(f"✅ Keyword `{keyword}` removida. ({len(kws)} total)", color=0x51CF66))

    # ─── !conf reddit ────────────────────────

    @cmd_conf.group(name="reddit", invoke_without_command=True)
    async def conf_reddit(self, ctx):
        opp_subs = [s for s in runtime_config.get_opp_sources() if "reddit.com" in s.get("rss", "")]
        news_subs = [s for s in runtime_config.get_news_sources() if "reddit.com" in s.get("rss", "")]
        lines = []
        if opp_subs:
            lines.append("**Oportunidades:**")
            lines.extend(f"  • `{s['name']}`" for s in opp_subs)
        if news_subs:
            lines.append("**Notícias:**")
            lines.extend(f"  • `{s['name']}`" for s in news_subs)
        if not lines:
            lines.append("Nenhum subreddit configurado.")
        lines.append("\n`!conf reddit add <sub> opp` · `!conf reddit add <sub> news`")
        lines.append("`!conf reddit del <sub> opp` · `!conf reddit del <sub> news`")
        await ctx.send(embed=_embed("\n".join(lines)))

    @conf_reddit.command(name="list")
    async def conf_reddit_list(self, ctx):
        await self.conf_reddit(ctx)

    @conf_reddit.command(name="add")
    async def conf_reddit_add(self, ctx, sub: str, tipo: str = "news"):
        sub = sub.strip().lstrip("r/")
        tipo = tipo.lower()
        if tipo not in ("opp", "news"):
            await ctx.send(embed=_embed("❌ Tipo deve ser `opp` ou `news`.", color=0xFF4444))
            return

        if tipo == "opp":
            rss_url = f"https://www.reddit.com/r/{sub}/search.rss?q=flair%3AHiring&restrict_sr=on&sort=new"
        else:
            rss_url = f"https://www.reddit.com/r/{sub}/hot/.rss"

        name = f"r/{sub}"
        source = {"name": name, "color": 0xFF4500, "rss": rss_url}

        if tipo == "opp":
            sources = list(runtime_config.get_opp_sources())
            if any(s["name"].lower() == name.lower() for s in sources):
                await ctx.send(embed=_embed(f"— `{name}` já está nas oportunidades.", color=0xFCC419))
                return
            sources.append(source)
            runtime_config.set_opp_sources(sources)
        else:
            sources = list(runtime_config.get_news_sources())
            if any(s["name"].lower() == name.lower() for s in sources):
                await ctx.send(embed=_embed(f"— `{name}` já está nas notícias.", color=0xFCC419))
                return
            sources.append(source)
            runtime_config.set_news_sources(sources)

        await ctx.send(embed=_embed(
            f"✅ `{name}` adicionado às **{'oportunidades' if tipo == 'opp' else 'notícias'}**.\n"
            f"RSS: `{rss_url[:70]}...`", color=0x51CF66))

    @conf_reddit.command(name="del")
    async def conf_reddit_del(self, ctx, sub: str, tipo: str = "news"):
        sub = sub.strip().lstrip("r/")
        tipo = tipo.lower()
        name = f"r/{sub}"

        if tipo == "opp":
            sources = list(runtime_config.get_opp_sources())
            nova = [s for s in sources if s["name"].lower() != name.lower()]
            if len(nova) == len(sources):
                await ctx.send(embed=_embed(f"❌ `{name}` não encontrado nas oportunidades.", color=0xFF4444))
                return
            runtime_config.set_opp_sources(nova)
        elif tipo == "news":
            sources = list(runtime_config.get_news_sources())
            nova = [s for s in sources if s["name"].lower() != name.lower()]
            if len(nova) == len(sources):
                await ctx.send(embed=_embed(f"❌ `{name}` não encontrado nas notícias.", color=0xFF4444))
                return
            runtime_config.set_news_sources(nova)
        else:
            await ctx.send(embed=_embed("❌ Tipo deve ser `opp` ou `news`.", color=0xFF4444))
            return

        await ctx.send(embed=_embed(
            f"✅ `{name}` removido das **{'oportunidades' if tipo == 'opp' else 'notícias'}**.", color=0x51CF66))

    # ─── !conf reset ─────────────────────────

    @cmd_conf.command(name="reset")
    async def conf_reset(self, ctx):
        runtime_config.reset()
        await ctx.send(embed=_embed(
            "🔄 Configuração resetada para os defaults do `config.py`.", color=0xFCC419))
