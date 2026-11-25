"""Logging System + Notification System (ohne sensible Daten)."""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler("logs/bot.log"), logging.StreamHandler()])
log = logging.getLogger("bot")

RESEARCH_LOG = Path("logs/research_log.jsonl")


def research_log(msg: str, level: str = "INFO"):
    log.info(msg) if level == "INFO" else log.warning(msg)
    with RESEARCH_LOG.open("a") as f:
        f.write(json.dumps({"time": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
                            "level": level, "msg": msg}, ensure_ascii=False) + "\n")


def read_research_log(n=40):
    if not RESEARCH_LOG.exists():
        return []
    lines = RESEARCH_LOG.read_text().splitlines()[-n:]
    return [json.loads(x) for x in reversed(lines)]


def notify(msg: str):
    """Telegram, falls TELEGRAM_TOKEN und TELEGRAM_CHAT_ID gesetzt sind (GitHub Secrets)."""
    log.info("NOTIFY: %s", msg)
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": "[DEMO] " + msg}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10)
    except Exception as e:  # Token nie loggen
        log.warning("Benachrichtigung fehlgeschlagen: %s", type(e).__name__)
