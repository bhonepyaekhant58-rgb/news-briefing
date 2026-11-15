"""Choose which collected stories go on the page."""
import re


def words(title):
    """The longer words of a headline, used to spot the same story twice."""
    return {word for word in re.findall(r"[a-z0-9]+", title.lower()) if len(word) > 3}


def same_story(a, b):
    """True when two stories are the same: same link, same headline, or nearly the same words."""
    if a["link"] == b["link"] or a["title"].lower() == b["title"].lower():
        return True
    first, second = words(a["title"]), words(b["title"])
    shared = first & second
    return len(shared) >= 3 and len(shared) / len(first | second) >= 0.6


def choose_stories(per_feed, count, used):
    """Take turns between feeds, keeping each feed's order, skipping repeats."""
    chosen = []
    queues = [list(group) for group in per_feed]
    while len(chosen) < count and any(queues):
        for queue in queues:
            if queue and len(chosen) < count:
                story = queue.pop(0)
                if not any(same_story(story, other) for other in used + chosen):
                    chosen.append(story)
    if chosen and not any(story["region"] for story in chosen):
        for group in per_feed:
            for story in group:
                if story["region"] and not any(same_story(story, other) for other in used + chosen):
                    chosen[-1] = story  # make room for one Myanmar or Southeast Asia story
                    return chosen
    return chosen
