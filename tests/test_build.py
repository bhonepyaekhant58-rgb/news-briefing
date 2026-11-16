import json
import zlib
from email.utils import formatdate

import pytest

from briefing import build as build_module
from briefing.build import BuildError, build
from briefing.config import load_settings

STARTING = "tests/starting_settings.json"  # a fixed copy; the real settings.json is edited by the owner
NOW = 1_800_000_000  # 15 January 2027, 15:00 in Thailand


def fake_fetch(url):
    if "onthisday" in url:
        events = [{"year": 1900 + i, "text": f"Event {i} happened.", "pages": []} for i in range(30)]
        return json.dumps({"events": events}).encode()
    if "nothinghere" in url:
        return b'<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>'
    tag = zlib.crc32(url.encode())
    date = formatdate(NOW - 600, usegmt=True)
    items = "".join(
        f"<item><title>alpha{tag}x{i} bravo{tag}x{i} charlie{tag}x{i}</title>"
        f"<link>https://example.com/{tag}/{i}</link><pubDate>{date}</pubDate>"
        f"<description>Words about item {i} here.</description></item>" for i in range(15))
    return (f'<?xml version="1.0"?><rss version="2.0"><channel><title>Feed {tag}</title>'
            f"{items}</channel></rss>").encode()


def fake_ask(calls):
    def ask(prompt, model, api_key):
        calls.append(prompt)
        listing = json.loads(prompt.split("Stories:\n", 1)[1])
        return json.dumps([{"id": entry["id"], "summary": "Short summary."} for entry in listing])
    return ask


def no_pages(url):
    raise OSError("offline")


def run(tmp_path, settings, fetch=fake_fetch, calls=None, fetch_page=no_pages):
    build(settings, NOW, "key", "owner/repo", tmp_path / "site", tmp_path / "state.json",
          fetch, fake_ask([] if calls is None else calls), fetch_page=fetch_page)
    return (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def test_starting_topics_fill_the_page(tmp_path):  # AC-2.3
    calls = []
    page = run(tmp_path, load_settings(STARTING), calls=calls)
    assert page.count('class="card"') == 70
    assert 1 <= len(calls) <= 8
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["day"] == "2027-01-15" and len(state["summaries"]) == 65


def test_second_build_on_the_same_day_reuses_summaries(tmp_path):
    settings = load_settings(STARTING)
    run(tmp_path, settings)
    calls = []
    run(tmp_path, settings, calls=calls)
    assert calls == []


def test_every_source_failing_leaves_the_old_page(tmp_path):  # AC-6.4
    def dead(url):
        raise OSError("offline")

    with pytest.raises(BuildError, match="every news source failed"):
        run(tmp_path, load_settings(STARTING), fetch=dead)
    assert not (tmp_path / "site" / "index.html").exists()


def test_one_dead_site_does_not_stop_the_build(tmp_path):  # AC-6.2
    def flaky(url):
        if "techcrunch" in url:
            raise OSError("offline")
        return fake_fetch(url)

    page = run(tmp_path, load_settings(STARTING), fetch=flaky)
    assert page.count('class="card"') == 70


def test_typed_topic_without_news_says_no_stories_today(tmp_path):  # AC-5.3, AC-6.3
    page = run(tmp_path, {"topics": [{"name": "Tech"}, {"name": "nothinghere"}]})
    assert "No stories today" in page and 'data-topic="nothinghere"' in page


def test_settings_edits_change_the_page(tmp_path):  # AC-5.9
    page = run(tmp_path, {"story_target": 6, "topics": [{"name": "Tech"}, {"name": "Space"}]})
    assert page.count('class="card"') == 6


def test_a_mistake_in_settings_stops_the_build(tmp_path, monkeypatch, capsys):
    (tmp_path / "settings.json").write_text('{"topics": []}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as stop:
        build_module.main()
    assert stop.value.code == 1
    assert "BUILD STOPPED" in capsys.readouterr().out and not (tmp_path / "site").exists()


def test_summaries_are_written_from_article_pages(tmp_path):  # AC-3.4
    def pages(url):
        if url.endswith("/robots.txt"):
            return "User-agent: *\nAllow: /"
        return "<html><body><p>" + "ARTICLE-BODY " + "detail " * 40 + "</p></body></html>"

    calls = []
    page = run(tmp_path, load_settings(STARTING), calls=calls, fetch_page=pages)
    assert any("ARTICLE-BODY" in prompt for prompt in calls)
    assert page.count('class="card"') == 70


def test_unreadable_articles_do_not_stop_the_build(tmp_path, capsys):  # AC-3.5
    page = run(tmp_path, load_settings(STARTING), fetch_page=no_pages)
    assert page.count('class="card"') == 70
    assert "Articles read: 0" in capsys.readouterr().out
