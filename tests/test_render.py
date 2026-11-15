import json

from briefing.render import render_page, section_for

NOW = 1_800_000_000  # Friday 15 January 2027, 15:00 in Thailand
SETTINGS = {"topics": [{"name": "Tech", "priority": "high"}, {"name": "Health"}]}


def story(title="A headline", image=""):
    return {"title": title, "link": "https://example.com/story", "source": "Example News",
            "summary": "First sentence. Second sentence.", "image": image}


def build_page(tmp_path, tech=None, health=None):
    sections = [
        section_for({"name": "Tech", "priority": "high", "icon": "💻"},
                    [story()] if tech is None else tech),
        section_for({"name": "Health"}, [story("Other headline")] if health is None else health),
    ]
    render_page(sections, SETTINGS, NOW, "owner/repo", tmp_path)
    return (tmp_path / "index.html").read_text(encoding="utf-8")


def test_date_and_build_time_are_shown(tmp_path):  # AC-1.1
    page = build_page(tmp_path)
    assert "Friday, 15 January 2027" in page and "15:00" in page


def test_topics_are_in_order_with_a_menu(tmp_path):  # AC-2.1, AC-2.5, AC-4.2
    page = build_page(tmp_path)
    assert page.index('id="topic-tech"') < page.index('id="topic-health"')
    assert 'href="#topic-tech"' in page and 'href="#topic-health"' in page
    assert page.count('class="topic high"') == 1


def test_story_card_has_headline_summary_source_and_link(tmp_path):  # AC-3.1, AC-3.2
    page = build_page(tmp_path)
    assert "A headline" in page and "First sentence. Second sentence." in page
    assert "Example News" in page
    assert 'href="https://example.com/story" target="_blank" rel="noopener noreferrer"' in page


def test_image_appears_only_when_the_feed_gave_one(tmp_path):  # AC-4.3
    page = build_page(tmp_path, tech=[story(image="https://example.com/a.jpg"), story("No picture")])
    assert page.count("<img") == 1 and 'src="https://example.com/a.jpg"' in page


def test_empty_topic_says_no_stories_today(tmp_path):  # AC-6.3
    assert "No stories today" in build_page(tmp_path, health=[])


def test_text_from_feeds_cannot_run_as_code(tmp_path):
    page = build_page(tmp_path, tech=[story("<script>alert(1)</script>")])
    assert "<script>alert(1)" not in page and "&lt;script&gt;" in page


def test_topic_colour_and_icon_stay_the_same(tmp_path):  # AC-4.4
    first, again = section_for({"name": "electric cars"}, []), section_for({"name": "Electric Cars "}, [])
    assert first["hue"] == again["hue"] and 0 <= first["hue"] < 360
    assert first["icon"] == "E" and first["slug"] == "topic-electric-cars"


def test_phone_and_theme_basics(tmp_path):  # AC-4.1, AC-4.5
    page = build_page(tmp_path)
    styles = (tmp_path / "style.css").read_text(encoding="utf-8")
    assert 'name="viewport"' in page and "prefers-color-scheme: dark" in styles


def test_status_file_and_page_settings(tmp_path):
    page = build_page(tmp_path)
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["topics_key"] == "tech:high|health:normal"
    assert '"repo": "owner/repo"' in page and '"builtDay": "2027-01-15"' in page
    assert 'id="picker"' in page and 'id="open-picker"' in page


def test_picker_script_is_published(tmp_path):  # FR-6
    build_page(tmp_path)
    script = (tmp_path / "app.js").read_text(encoding="utf-8")
    assert "/contents/settings.json" in script and "briefing-access-key" in script
