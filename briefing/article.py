"""Read a story's own article page, so its summary has more to work from."""
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from briefing.collect import USER_AGENT, clean_text

DETAIL_LIMIT = 1500                # characters of text given to the AI for one story
TIME_LIMIT = 120                   # seconds one build may spend reading article pages
SKIP_SITES = ("news.google.com",)  # these links do not lead straight to the article


def fetch_page(url):
    """Download one web page as text. Raises an error if it cannot be read."""
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=8)
    response.raise_for_status()
    return response.text


class Paragraphs(HTMLParser):
    """Collect the text of every <p> on a page, and the page's own description."""

    def __init__(self):
        super().__init__()
        self.paragraphs, self.description = [], ""
        self.inside, self.skip, self.text = False, 0, []

    def close_paragraph(self):
        if self.inside:
            self.paragraphs.append(" ".join("".join(self.text).split()))
            self.inside = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        is_description = attrs.get("property") == "og:description" or attrs.get("name") == "description"
        if tag == "meta" and is_description and not self.description:
            self.description = attrs.get("content") or ""
        elif tag in ("script", "style"):
            self.skip += 1
        elif tag == "p":
            self.close_paragraph()
            self.inside, self.text = True, []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag == "p":
            self.close_paragraph()

    def handle_data(self, data):
        if self.inside and not self.skip:
            self.text.append(data)


def article_text(page):
    """The main text of an article page: its longer paragraphs, or the page's description."""
    parser = Paragraphs()
    parser.feed(page)
    parser.close_paragraph()
    # Short paragraphs are menus and captions; repeated ones are notices shown on every page.
    body = " ".join(text for text in parser.paragraphs
                    if len(text) >= 80 and parser.paragraphs.count(text) == 1)
    return clean_text(body if len(body) >= 200 else parser.description, DETAIL_LIMIT)


def allowed(url, rules, fetch_page=fetch_page):
    """True when the site's robots.txt lets an automatic reader open this page."""
    parts = urlsplit(url)
    site = f"{parts.scheme}://{parts.netloc}"
    if site not in rules:
        parser = RobotFileParser()
        try:
            parser.parse(fetch_page(site + "/robots.txt").splitlines())
        except requests.HTTPError as error:
            if getattr(error.response, "status_code", None) == 404:
                parser.parse([])  # no rules file means nothing is forbidden
            else:
                parser = None     # rules could not be read: leave the site alone
        except Exception:
            parser = None
        rules[site] = parser
    return rules[site] is not None and rules[site].can_fetch(USER_AGENT, url)


def add_details(stories, cache, fetch_page=fetch_page, clock=time.monotonic):
    """Set story['detail'], the text the AI summarizes from. Returns how many articles were read."""
    rules, started, read = {}, clock(), 0
    for story in stories:
        story["detail"] = story.get("content") or story["description"]
        if story.get("history") or story["link"] in cache:
            continue  # nothing to summarize, or already summarized today
        if urlsplit(story["link"]).netloc in SKIP_SITES or clock() - started > TIME_LIMIT:
            continue
        try:
            if allowed(story["link"], rules, fetch_page):
                text = article_text(fetch_page(story["link"]))
                if len(text) > len(story["detail"]):
                    story["detail"] = text
                    read += 1
        except Exception as error:  # a page that cannot be read must never stop the build
            print(f"  article not read: {story['link']} ({error})")
    return read
