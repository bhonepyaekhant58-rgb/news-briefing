import json
from email.utils import formatdate

from briefing.collect import (clean_text, collect_topic, history_stories, parse_feed,
                              search_url, topic_feeds)

NOW = 1_800_000_000  # 15 January 2027, 15:00 in Thailand


def item(title, link="https://example.com/a", age=600, description="", extra=""):
    date = formatdate(NOW - age, usegmt=True)
    return (f"<item><title>{title}</title><link>{link}</link><pubDate>{date}</pubDate>"
            f"<description>{description}</description>{extra}</item>")


def rss(*items):
    return ('<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" '
            'xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            f"<channel><title>Example News</title>{''.join(items)}</channel></rss>").encode()


def test_story_fields_are_filled():
    extra = '<media:content url="https://example.com/a.jpg" medium="image"/>'
    feed = rss(item("Big news", description="&lt;b&gt;Bold&lt;/b&gt; words  here", extra=extra))
    [story] = parse_feed(feed, NOW)
    assert story["title"] == "Big news"
    assert story["link"] == "https://example.com/a"
    assert story["source"] == "Example News"
    assert story["description"] == "Bold words here"
    assert story["image"] == "https://example.com/a.jpg"
    assert story["region"] is False


def test_old_and_undated_stories_are_dropped():  # FR-2: last 24 hours only
    feed = rss(item("Fresh"), item("Stale", link="https://example.com/b", age=25 * 3600),
               "<item><title>No date</title><link>https://example.com/c</link></item>")
    assert [story["title"] for story in parse_feed(feed, NOW)] == ["Fresh"]


def test_google_news_title_and_source_are_split():
    extra = '<source url="https://paper.example">The Paper</source>'
    feed = rss(item("Rates rise again - The Paper", description="Rates rise again The Paper", extra=extra))
    [story] = parse_feed(feed, NOW)
    assert (story["title"], story["source"], story["description"]) == ("Rates rise again", "The Paper", "")


def test_unsafe_links_are_dropped():
    assert parse_feed(rss(item("Bad", link="javascript:alert(1)")), NOW) == []


def test_typed_topic_is_searched_by_its_name():  # AC-5.3
    [(url, region)] = topic_feeds({"name": "electric cars"})
    assert url == search_url("electric cars") and region is False
    assert "electric+cars+when%3A1d" in url


def test_search_terms_and_region_feeds():  # AC-2.6, AC-2.7
    topic = {"name": "Business", "feeds": ["https://example.com/feed"],
             "search": ["digital marketing"], "region_search": ["Myanmar business"]}
    assert topic_feeds(topic) == [("https://example.com/feed", False),
                                  (search_url("digital marketing"), False),
                                  (search_url("Myanmar business"), True)]


def test_one_dead_feed_does_not_stop_the_rest():  # AC-6.2
    def fetch(url):
        if "dead" in url:
            raise OSError("site is down")
        return rss(item("Works"))

    topic = {"name": "T", "feeds": ["https://dead.example/feed", "https://ok.example/feed"]}
    groups, failed = collect_topic(topic, NOW, fetch)
    assert failed == 1
    assert [[story["title"] for story in group] for group in groups] == [["Works"]]


def test_region_feed_marks_its_stories():  # AC-2.7
    groups, _ = collect_topic({"name": "T", "region_search": ["Myanmar"]}, NOW,
                              lambda url: rss(item("Local")))
    assert groups[0][0]["region"] is True


def test_history_gives_events_with_their_year():  # AC-3.3
    events = [{"year": 1900 + i, "text": f"Event {i} happened.",
               "pages": [{"content_urls": {"desktop": {"page": f"https://en.wikipedia.org/wiki/E{i}"}},
                          "thumbnail": {"source": f"https://upload.example/{i}.jpg"}}]}
              for i in range(30)]
    seen = []

    def fetch(url):
        seen.append(url)
        return json.dumps({"events": events}).encode()

    stories = history_stories(NOW, 5, fetch)
    assert seen == ["https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/01/15"]
    assert len(stories) == 5
    assert stories[0]["title"] == "On this day in 1900"
    assert stories[0]["description"] == "Event 0 happened."
    assert stories[0]["link"] == "https://en.wikipedia.org/wiki/E0"
    assert all(story["history"] and story["source"] == "Wikipedia" for story in stories)


def test_clean_text_shortens_long_text():
    text = clean_text("word " * 200, limit=50)
    assert len(text) <= 51 and text.endswith("…")


def test_a_one_word_description_is_dropped():
    link_only = "&lt;a href=&quot;https://news.example/item?id=1&quot;&gt;Comments&lt;/a&gt;"
    [story] = parse_feed(rss(item("Show: a new tool", description=link_only)), NOW)
    assert story["description"] == ""


def test_description_keeps_enough_text_for_context():  # FR-4
    long_text = " ".join(f"word{i}" for i in range(120))  # about 800 characters
    [story] = parse_feed(rss(item("Long story", description=long_text)), NOW)
    assert 400 < len(story["description"]) <= 601


def test_feed_content_field_is_kept():  # AC-3.5
    words = " ".join(f"word{i}" for i in range(300))
    extra = f"<content:encoded><![CDATA[<p>{words}</p>]]></content:encoded>"
    [story] = parse_feed(rss(item("Long read", extra=extra)), NOW)
    assert "<" not in story["content"]
    assert 600 < len(story["content"]) <= 1501
    [plain] = parse_feed(rss(item("Plain story")), NOW)
    assert plain["content"] == ""
