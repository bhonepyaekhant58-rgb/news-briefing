import requests

from briefing.article import add_details, article_text

LONG = "This is a long paragraph about the story with plenty of detail in it. " * 3
RULES_ALLOW = "User-agent: *\nAllow: /"
RULES_DENY = "User-agent: *\nDisallow: /"


def page(*paragraphs, description=""):
    meta = f'<meta property="og:description" content="{description}">'
    body = "".join(f"<p>{text}</p>" for text in paragraphs)
    return (f"<html><head>{meta}</head><body><script>var hidden = 1;</script>"
            f"<p>Menu</p>{body}</body></html>")


def story(link, **extra):
    result = {"title": "T", "link": link, "description": "Short feed text here.", "content": ""}
    result.update(extra)
    return result


def fake_pages(pages):
    """A fake fetch_page: looks the address up in a dict. Returns (fetch_page, asked)."""
    asked = []

    def fetch_page(url):
        asked.append(url)
        if url in pages:
            value = pages[url]
            if isinstance(value, Exception):
                raise value
            return value
        raise OSError("not found")

    return fetch_page, asked


def test_article_text_keeps_long_paragraphs_only():
    text = article_text(page(LONG, "Another " + LONG))
    assert "long paragraph about the story" in text
    assert "Menu" not in text and "hidden" not in text


def test_article_text_drops_repeated_paragraphs():
    boilerplate = "Sign up for our newsletter to get the latest news sent to your inbox every single day. " * 2
    text = article_text(page(boilerplate, LONG, boilerplate))
    assert LONG.strip() in text
    assert "newsletter" not in text


def test_article_text_falls_back_to_the_page_description():
    text = article_text(page("Short one.", "Short two.", description="The page's own description of the story."))
    assert text == "The page's own description of the story."


def test_article_text_is_cut_to_1500_characters():
    paragraphs = [f"Paragraph number {i} is different. " + LONG for i in range(10)]
    assert len(article_text(page(*paragraphs))) <= 1501


def test_article_page_becomes_the_detail():  # AC-3.4
    fetch_page, asked = fake_pages({"https://site.example/robots.txt": RULES_ALLOW,
                                    "https://site.example/a": page(LONG)})
    item = story("https://site.example/a")
    assert add_details([item], {}, fetch_page) == 1
    assert "long paragraph about the story" in item["detail"]


def test_google_news_links_are_not_followed():  # AC-3.5
    fetch_page, asked = fake_pages({})
    item = story("https://news.google.com/rss/articles/abc", content="Fuller feed text.")
    add_details([item], {}, fetch_page)
    assert item["detail"] == "Fuller feed text."
    assert asked == []


def test_already_summarized_and_history_stories_are_not_read():
    fetch_page, asked = fake_pages({})
    done = story("https://site.example/done")
    old = story("https://site.example/old", history=True)
    add_details([done, old], {"https://site.example/done": "Saved."}, fetch_page)
    assert asked == []
    assert done["detail"] == done["description"] and old["detail"] == old["description"]


def test_a_site_that_forbids_readers_is_not_read():  # AC-3.5
    fetch_page, asked = fake_pages({"https://site.example/robots.txt": RULES_DENY,
                                    "https://site.example/a": page(LONG)})
    item = story("https://site.example/a")
    assert add_details([item], {}, fetch_page) == 0
    assert "https://site.example/a" not in asked
    assert item["detail"] == item["description"]


def test_a_missing_rules_file_means_reading_is_allowed():
    response = requests.Response()
    response.status_code = 404
    error = requests.HTTPError("404 error", response=response)
    fetch_page, asked = fake_pages({"https://site.example/robots.txt": error,
                                    "https://site.example/a": page(LONG)})
    item = story("https://site.example/a")
    assert add_details([item], {}, fetch_page) == 1
    assert "https://site.example/a" in asked


def test_unreadable_rules_mean_the_site_is_skipped():
    fetch_page, asked = fake_pages({"https://site.example/robots.txt": OSError("broken"),
                                    "https://site.example/a": page(LONG)})
    add_details([story("https://site.example/a")], {}, fetch_page)
    assert "https://site.example/a" not in asked


def test_a_page_that_fails_does_not_stop_the_build():  # AC-3.5
    fetch_page, asked = fake_pages({
        "https://bad.example/robots.txt": RULES_ALLOW,
        "https://bad.example/a": OSError("page broke"),
        "https://good.example/robots.txt": RULES_ALLOW,
        "https://good.example/b": page(LONG)})
    broken, working = story("https://bad.example/a"), story("https://good.example/b")
    add_details([broken, working], {}, fetch_page)
    assert broken["detail"] == broken["description"]
    assert "long paragraph about the story" in working["detail"]


def test_reading_stops_when_time_runs_out():
    fetch_page, asked = fake_pages({"https://site.example/robots.txt": RULES_ALLOW,
                                    "https://site.example/a": page(LONG)})
    times = iter([0])

    def clock():
        return next(times, 1000)

    add_details([story("https://site.example/a")], {}, fetch_page, clock)
    assert asked == []


def test_rules_are_fetched_once_per_site():
    fetch_page, asked = fake_pages({"https://site.example/robots.txt": RULES_ALLOW,
                                    "https://site.example/a": page(LONG),
                                    "https://site.example/b": page("Other " + LONG)})
    add_details([story("https://site.example/a"), story("https://site.example/b")], {}, fetch_page)
    assert asked.count("https://site.example/robots.txt") == 1
