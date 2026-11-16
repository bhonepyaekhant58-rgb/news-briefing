"""Read settings.json, check it for mistakes, and share out the stories."""
import json
from pathlib import Path

MAX_TOPICS = 20


class SettingsError(Exception):
    """settings.json has a mistake. The message names the problem."""


def load_settings(path="settings.json"):
    """Read the settings file and check it. Raises SettingsError on any mistake."""
    try:
        settings = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SettingsError(f"{path} was not found")
    except json.JSONDecodeError as error:
        raise SettingsError(f"{path} is not valid JSON: {error}")
    check_settings(settings)
    return settings


def check_settings(settings):
    """Raise SettingsError if the topic list or story target breaks a rule."""
    topics = settings.get("topics")
    if not isinstance(topics, list) or not topics:
        raise SettingsError("settings must have at least 1 topic")
    if len(topics) > MAX_TOPICS:
        raise SettingsError(f"settings has {len(topics)} topics; the most allowed is {MAX_TOPICS}")
    seen = set()
    for topic in topics:
        name = topic.get("name") if isinstance(topic, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise SettingsError("every topic needs a name")
        name = name.strip()
        if name.lower() in seen:
            raise SettingsError(f"topic '{name}' is listed twice")
        seen.add(name.lower())
        priority = topic.get("priority", "normal")
        if priority not in ("high", "normal"):
            raise SettingsError(f"topic '{name}' has priority '{priority}'; use 'high' or 'normal'")
        for field in ("feeds", "search", "region_search"):
            value = topic.get(field, [])
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise SettingsError(f"topic '{name}': '{field}' must be a list of text inside [ ] brackets")
    target = settings.get("story_target", 70)
    if not isinstance(target, int) or not 1 <= target <= 80:
        raise SettingsError("story_target must be a whole number from 1 to 80")
    limit = settings.get("max_ai_requests", 8)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 8:
        raise SettingsError("max_ai_requests must be a whole number from 1 to 8")


def ordered_topics(settings):
    """High-priority topics first, then the rest, each group in list order."""
    topics = settings["topics"]
    high = [topic for topic in topics if topic.get("priority") == "high"]
    normal = [topic for topic in topics if topic.get("priority") != "high"]
    return high + normal


def topics_key(settings):
    """One line of text that describes the topic list. The page builds the same text."""
    return "|".join(f"{topic['name'].strip().lower()}:{topic.get('priority', 'normal')}"
                    for topic in settings["topics"])


def story_counts(settings):
    """Share the story target among topics. High priority gets a double share."""
    topics = settings["topics"]
    shares = sum(2 if topic.get("priority") == "high" else 1 for topic in topics)
    base = settings.get("story_target", 70) // shares
    counts = {}
    for topic in topics:
        wanted = base * 2 if topic.get("priority") == "high" else base
        counts[topic["name"]] = max(2, min(12, wanted))
    return counts
