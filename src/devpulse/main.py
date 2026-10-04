# src/devpulse/main.py
from .bot import build_bot, build_run_digest
from .settings import load_settings
from .store import Store


def main() -> None:
    settings = load_settings()
    store = Store("devpulse.db")
    store.init_schema()
    run_digest = build_run_digest(settings, store)
    bot = build_bot(settings, store, run_digest)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
