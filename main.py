#!/usr/bin/env python3
import os
import json
import logging
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser

# Telegram token từ GitHub Secret
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
INTERVAL = 600  # chỉ tham khảo, workflow chạy theo schedule
JSON_SENT_FILE = "sent_links.json"
JSON_CHAT_FILE = "active_chats.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))
sent_links = {}
active_chats = set()

def load_sent_links():
    global sent_links
    if os.path.exists(JSON_SENT_FILE):
        try:
            with open(JSON_SENT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                sent_links = {int(k): set(v) for k, v in data.items()}
            logger.info("✅ Loaded sent_links successfully")
        except Exception as e:
            logger.error(f"❌ Error loading JSON: {e}")

def save_sent_links():
    try:
        data = {str(k): list(v) for k, v in sent_links.items()}
        with open(JSON_SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ Error saving JSON: {e}")

def load_active_chats():
    global active_chats
    if os.path.exists(JSON_CHAT_FILE):
        try:
            with open(JSON_CHAT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                active_chats = set(data)
            logger.info("✅ Loaded active_chats")
        except Exception as e:
            logger.warning(f"⚠️ Could not load active_chats: {e}")

def fetch_rss(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (TelegramGameBot/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        return feed.entries or []
    except Exception as e:
        logger.error(f"❌ Error fetching {url}: {e}")
        return []

def get_entry_datetime(entry):
    pub_dt = None
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            pub_dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "published"):
            pub_dt = dateparser.parse(entry.published).astimezone(timezone.utc)
        elif hasattr(entry, "updated"):
            pub_dt = dateparser.parse(entry.updated).astimezone(timezone.utc)
    except Exception as e:
        logger.warning(f"⚠️ Cannot parse entry datetime: {e}")

    if pub_dt:
        return pub_dt.astimezone(VN_TZ)
    else:
        return datetime.now(VN_TZ)

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ Error sending message: {e}")
        return False

def send_news_to_chat(chat_id):
    load_sent_links()

    sources = [
        ("🎮 GameK", "http://gamek.vn/home.rss"),
        ("🎯 IGN", "https://feeds.feedburner.com/ign/news"),
        ("📱 Pocket Gamer", "https://www.pocketgamer.com/news/index.rss"),
        ("🎲 Gematsu", "https://www.gematsu.com/feed"),
    ]

    if chat_id not in sent_links:
        sent_links[chat_id] = set()

    collected_news = {}
    total_new_articles = 0

    for name, url in sources:
        entries = fetch_rss(url)
        collected = []

        for entry in entries:
            pub_dt = get_entry_datetime(entry)
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", "No title")

            if link not in sent_links[chat_id]:
                collected.append({
                    "title": title,
                    "link": link,
                    "pub_dt": pub_dt
                })
                sent_links[chat_id].add(link)
                total_new_articles += 1

        if collected:
            collected_news[name] = collected

    if collected_news:
        for source, articles in collected_news.items():
            for article in articles:
                text = f"📰 **{source}**\n\n🔹 {article['title']}\n\n🔗 {article['link']}"
                send_telegram_message(chat_id, text)

        save_sent_links()
        logger.info(f"📤 Sent {total_new_articles} new articles to chat {chat_id}")
    else:
        logger.info(f"📭 No new articles for chat {chat_id}")

if __name__ == "__main__":
    logger.info("🚀 Running Gaming News Bot (GitHub Actions mode)...")
    load_sent_links()
    load_active_chats()

    if not active_chats:
        logger.warning("⚠️ No active chats found. Add chat IDs to active_chats.json")
    else:
        for chat_id in active_chats:
            send_news_to_chat(chat_id)

    logger.info("✅ Script finished")
