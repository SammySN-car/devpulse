# src/devpulse/bot.py
from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

import discord
from discord import app_commands

from .composer import compose_digest
from .judge import OllamaJudge, free_ram_mb
from .models import Item
from .pipeline import run_pipeline
from .settings import Settings
from .store import Store


def can_refresh(user_id: int, owner_id: int | None) -> bool:
    return owner_id is not None and user_id == owner_id


def seconds_until(hhmm: str, now: datetime) -> float:
    hour, minute = (int(part) for part in hhmm.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def safe_run(run_digest: Callable[[], str]) -> str:
    try:
        return run_digest()
    except Exception as exc:
        return f"daily run skipped: {exc}"


def _first_ready(state: dict[str, bool]) -> bool:
    if state.get("started"):
        return False
    state["started"] = True
    return True


def cmd_dig(store: Store, topic: str) -> str:
    rows = store.search(topic)
    if not rows:
        return f"no stored verdicts match {topic!r}"
    lines = [f"results for {topic!r}:"]
    for item, j in rows[:10]:
        lines.append(f"- {item.title} [q {j.quality}] {j.verdict}")
    return "\n".join(lines)


def cmd_sleeper(store: Store, days: int = 7) -> str:
    rows = store.sleepers(days)
    if not rows:
        return f"no sleeper picks in the last {days} days"
    lines = [f"sleeper picks, last {days} days:"]
    for item, j in rows[:5]:
        pct = round(item.engagement_pct * 100)
        lines.append(f"- {item.title} [q {j.quality}, engagement bottom {pct}%] {j.verdict}")
    return "\n".join(lines)


def cmd_releases(store: Store) -> str:
    releases = store.releases()
    if not releases:
        return "no new watchlist releases"
    return "recent releases:\n" + "\n".join(f"- {r.title}" for r in releases)


def cmd_status(store: Store) -> str:
    row = store.last_digest()
    if row is None:
        return "no digest runs yet"
    msg = f"last run: {row[4]}, {row[1]} scanned, {row[2]} judged"
    if row[3]:
        msg += f", skipped: {row[3]}"
    return msg


def build_run_digest(settings: Settings, store: Store,
                     collectors: Sequence[Callable[[], list[Item]]] | None = None,
                     judge_factory: Callable[[], OllamaJudge] | None = None,
                     *, free_ram: Callable[[], int] = free_ram_mb,
                     guard_mb: int = 1500,
                     ) -> Callable[[], str]:
    def run() -> str:
        factory = judge_factory or (lambda: OllamaJudge(settings.model))
        stats = run_pipeline(store, judge_factory=factory, collectors=collectors,
                             token=settings.github_token, watchlist=settings.watchlist,
                             model=settings.model, free_ram=free_ram,
                             guard_mb=guard_mb)
        ranked = sorted(store.judged_rows(),
                        key=lambda pair: (pair[1].relevance, pair[1].quality),
                        reverse=True)[:5]
        sleepers = store.sleepers()
        return compose_digest(
            date_str=str(datetime.now().date()),
            top=ranked,
            sleeper=sleepers[0] if sleepers else None,
            releases=store.releases(),
            stats=stats,
            model=settings.model,
        )

    return run


def build_bot(settings: Settings, store: Store, run_digest: Callable[[], str]) -> discord.Client:
    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)

    @tree.command(name="dig", description="Search stored verdicts by topic")
    @app_commands.describe(topic="keyword, e.g. fastapi")
    async def dig_cmd(interaction: discord.Interaction, topic: str) -> None:
        await interaction.response.send_message(cmd_dig(store, topic)[:1999])

    @tree.command(name="sleeper", description="Best sleeper picks from the last 7 days")
    async def sleeper_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(cmd_sleeper(store)[:1999])

    @tree.command(name="releases", description="Recent watchlist releases")
    async def releases_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(cmd_releases(store)[:1999])

    @tree.command(name="status", description="Last digest run and judge health")
    async def status_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(cmd_status(store)[:1999])

    @tree.command(name="refresh", description="Force a digest run now (owner only)")
    async def refresh_cmd(interaction: discord.Interaction) -> None:
        if not can_refresh(interaction.user.id, settings.owner_id):
            await interaction.response.send_message(
                "only the owner can run /refresh", ephemeral=True)
            return
        await interaction.response.send_message("collecting and judging...")
        msg = await asyncio.to_thread(safe_run, run_digest)
        await interaction.followup.send(msg[:1999])

    async def scheduler() -> None:
        while not bot.is_closed():
            await asyncio.sleep(seconds_until(settings.digest_time, datetime.now()))
            msg = await asyncio.to_thread(safe_run, run_digest)
            channel = bot.get_channel(settings.digest_channel_id)
            if channel is not None:
                await channel.send(msg[:1999])

    state: dict[str, bool] = {}

    @bot.event
    async def on_ready() -> None:
        if not _first_ready(state):
            return
        await tree.sync()
        bot.loop.create_task(scheduler())

    return bot
