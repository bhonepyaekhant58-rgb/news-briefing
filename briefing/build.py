"""Build today's briefing: collect, choose, summarize, then write the page."""
import json
import os
import sys
import time
from pathlib import Path

from briefing import article, collect, summarize
from briefing.choose import choose_stories
from briefing.config import SettingsError, load_settings, ordered_topics, story_counts, topics_key
from briefing.render import render_page, section_for


class BuildError(Exception):
    """The build cannot finish. The page that is already published stays as it is."""


def thailand_day(now):
    return time.strftime("%Y-%m-%d", time.gmtime(now + collect.THAILAND_OFFSET))


def load_cache(state_path, now):
    """Summaries already written today, as a dict of link -> summary."""
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(state.get("summaries", {})) if state.get("day") == thailand_day(now) else {}


def build(settings, now, api_key="", repo="", out_dir="site", state_path="data/state.json",
          fetch=collect.fetch, ask=summarize.call_gemini, fetch_page=article.fetch_page):
    """Build the page into out_dir. Raises BuildError if every news source failed."""
    counts = story_counts(settings)
    sections, used, tried, failed = [], [], 0, 0
    for topic in ordered_topics(settings):
        count = counts[topic["name"]]
        if topic.get("kind") == "history":
            tried += 1
            try:
                stories = collect.history_stories(now, count, fetch)
            except Exception as error:  # history is one source among many
                failed += 1
                stories = []
                print(f"  history failed: {error}")
        else:
            groups, bad = collect.collect_topic(topic, now, fetch)
            tried += len(collect.topic_feeds(topic))
            failed += bad
            stories = choose_stories(groups, count, used)
            used += stories
        print(f"{topic['name']}: {len(stories)} of {count} stories")
        sections.append((topic, stories))
    if tried == failed:
        raise BuildError("every news source failed, so the page was left as it is")

    cache = load_cache(state_path, now)
    everything = [story for _, stories in sections for story in stories]
    articles_read = article.add_details(everything, cache, fetch_page)
    print(f"Articles read: {articles_read}")
    requests_used = summarize.summarize_stories(
        everything, cache, settings.get("model", "gemini-flash-lite-latest"), api_key,
        settings.get("max_ai_requests", 8), ask)
    print(f"AI requests used: {requests_used}")

    render_page([section_for(topic, stories) for topic, stories in sections],
                settings, now, repo, out_dir)
    state = {"day": thailand_day(now), "topics_key": topics_key(settings), "summaries": cache}
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    try:
        settings = load_settings("settings.json")
        build(settings, time.time(), os.environ.get("GEMINI_API_KEY", ""),
              os.environ.get("GITHUB_REPOSITORY", ""))
    except (SettingsError, BuildError) as error:
        print(f"BUILD STOPPED: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
