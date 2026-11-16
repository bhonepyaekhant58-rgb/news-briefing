import pytest

from briefing.config import (SettingsError, check_settings, load_settings,
                             ordered_topics, story_counts, topics_key)

OTHERS = ["Politics", "Big events", "Health", "Music & Entertainment",
          "Celebrity", "Religion", "History", "Trending"]


def topics(*pairs):
    return {"topics": [{"name": name, "priority": priority} for name, priority in pairs]}


STARTING = topics(("Tech", "high"), ("AI", "high"), ("Business", "high"),
                  *[(name, "normal") for name in OTHERS])


def test_starting_list_gives_10_and_5():  # AC-2.3
    counts = story_counts(STARTING)
    assert [counts[name] for name in ("Tech", "AI", "Business")] == [10, 10, 10]
    assert all(counts[name] == 5 for name in OTHERS)
    assert sum(counts.values()) == 70


@pytest.mark.parametrize("size,high", [(1, 0), (1, 1), (3, 0), (5, 5), (7, 3), (20, 0), (20, 20)])
def test_counts_stay_inside_limits(size, high):  # AC-2.4
    settings = topics(*[(f"t{i}", "high" if i < high else "normal") for i in range(size)])
    counts = story_counts(settings)
    assert all(2 <= count <= 12 for count in counts.values())
    assert sum(counts.values()) <= 80


def test_high_priority_gets_double():  # AC-5.5
    counts = story_counts(topics(("a", "high"), *[(f"n{i}", "normal") for i in range(12)]))
    assert counts["a"] == 2 * counts["n0"]


def test_high_priority_topics_come_first():  # AC-2.1
    settings = topics(("a", "normal"), ("b", "high"), ("c", "normal"), ("d", "high"))
    assert [topic["name"] for topic in ordered_topics(settings)] == ["b", "d", "a", "c"]


def test_topics_key_ignores_case_and_spaces():
    assert topics_key(topics((" Tech ", "high"), ("AI", "normal"))) == "tech:high|ai:normal"


@pytest.mark.parametrize("bad,word", [
    ({"topics": []}, "at least 1"),
    (topics(*[(f"t{i}", "normal") for i in range(21)]), "most allowed"),
    (topics(("a", "normal"), ("A", "normal")), "twice"),
    (topics(("", "normal")), "name"),
    (topics(("a", "urgent")), "priority"),
    ({"topics": [{"name": "a"}], "story_target": 500}, "story_target"),
    ({"topics": [{"name": 5}]}, "name"),
    ({"topics": [{"name": "a", "feeds": "https://example.com/feed"}]}, "feeds"),
    ({"topics": [{"name": "a"}], "max_ai_requests": "8"}, "max_ai_requests"),
    ({"topics": [{"name": "a"}], "max_ai_requests": 20}, "max_ai_requests"),
])
def test_mistakes_are_named(bad, word):  # error scenario: settings mistake
    with pytest.raises(SettingsError, match=word):
        check_settings(bad)


def test_broken_file_is_reported(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(SettingsError, match="not valid JSON"):
        load_settings(path)


def test_real_settings_file_is_valid():  # AC-2.2, AC-5.1
    settings = load_settings("settings.json")
    assert [topic["name"] for topic in ordered_topics(settings)] == ["Tech", "AI", "Business"] + OTHERS
    assert len(settings["suggested"]) >= 20
