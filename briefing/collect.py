"""Collect recent stories for each topic from public news feeds."""
import calendar
import html
import json
import re
import time
from urllib.parse import quote_plus

import feedparser
import requests

USER_AGENT = "news-briefing/1.0 (personal news page)"
DAY = 24 * 60 * 60
THAILAND_OFFSET = 7 * 60 * 60


def fetch(url):
    """Download one feed. Raises an error if the site cannot be reached."""
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    return response.content


def search_url(term):
    """A Google News search feed for any topic, limited to the last day."""
    return ("https://news.google.com/rss/search?q=" + quote_plus(term + " when:1d")
            + "&hl=en-US&gl=US&ceid=US:en")


def clean_text(value, limit=300):
    """Remove HTML tags and extra spaces; shorten long text at a word break."""
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def image_of(entry):
    """The story's picture address, or an empty string when the feed gives none."""
    for key in ("media_content", "media_thumbnail"):
        for media in entry.get(key, []):
            if str(media.get("url", "")).startswith("http"):
                return media["url"]
    for link in entry.get("links", []):
        address = str(link.get("href", ""))
        if (link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image")
                and address.startswith("http")):
            return address
    return ""


def parse_feed(content, now, region=False):
    """Turn one downloaded feed into Story dicts, keeping the last 24 hours only."""
    parsed = feedparser.parse(content)
    feed_title = parsed.feed.get("title", "")
    stories = []
    for entry in parsed.entries:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        link = entry.get("link", "")
        if not published or not link.startswith("http"):
            continue
        seconds = calendar.timegm(published)
        if now - seconds > DAY:
            continue
        source = entry.get("source", {}).get("title", "") or feed_title
        title = clean_text(entry.get("title", ""), 200)
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        description = clean_text(entry.get("summary", ""), 600)
        if description.lower().startswith(title.lower()[:40]) or len(description.split()) < 3:
            description = ""  # the feed gave no real text of its own
        content = clean_text((entry.get("content") or [{}])[0].get("value", ""), 1500)
        if title:
            stories.append({"title": title, "link": link, "source": source,
                            "description": description, "content": content,
                            "image": image_of(entry),
                            "published": seconds, "region": region})
    return stories


def topic_feeds(topic):
    """Every feed address for a topic, each with a flag: is it a region feed?"""
    feeds = [(url, False) for url in topic.get("feeds", [])]
    feeds += [(search_url(term), False) for term in topic.get("search", [])]
    feeds += [(search_url(term), True) for term in topic.get("region_search", [])]
    if not feeds:
        feeds = [(search_url(topic["name"]), False)]
    return feeds


def collect_topic(topic, now, fetch=fetch):
    """Return (stories grouped by feed, how many feeds failed)."""
    groups, failed = [], 0
    for url, region in topic_feeds(topic):
        try:
            groups.append(parse_feed(fetch(url), now, region))
        except Exception as error:  # one bad feed must never stop the build
            failed += 1
            print(f"  feed failed: {url} ({error})")
    return groups, failed


def history_stories(now, count, fetch=fetch):
    """Events that happened on today's Thailand date in past years."""
    day = time.gmtime(now + THAILAND_OFFSET)
    url = ("https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/"
           f"{day.tm_mon:02d}/{day.tm_mday:02d}")
    events = json.loads(fetch(url)).get("events", [])
    step = max(1, len(events) // count)
    stories = []
    for event in events[::step][:count]:
        page = (event.get("pages") or [{}])[0]
        year = event.get("year")
        link = page.get("content_urls", {}).get("desktop", {}).get("page", "")
        stories.append({"title": f"On this day in {year}",
                        "link": link or f"https://en.wikipedia.org/wiki/{year}",
                        "source": "Wikipedia",
                        "description": clean_text(event.get("text", "")), "content": "",
                        "image": page.get("thumbnail", {}).get("source", ""),
                        "published": now, "region": False, "history": True})
    return stories
