from briefing.choose import choose_stories


def story(title, link=None, region=False):
    return {"title": title, "link": link or "https://example.com/" + title.replace(" ", "-"),
            "region": region}


def titles(stories):
    return [item["title"] for item in stories]


def test_feeds_take_turns():
    first = [story("Apples arrive early"), story("Bananas bounce back")]
    second = [story("Cherries change colour"), story("Dates decline sharply")]
    chosen = choose_stories([first, second], 3, [])
    assert titles(chosen) == ["Apples arrive early", "Cherries change colour", "Bananas bounce back"]


def test_same_story_from_two_sources_appears_once():  # AC-2.8
    first = [story("Central bank raises interest rates again today", "https://one.example/x")]
    second = [story("Central bank raises interest rates again", "https://two.example/y"),
              story("Volcano erupts near island village")]
    chosen = choose_stories([first, second], 5, [])
    assert titles(chosen) == ["Central bank raises interest rates again today",
                              "Volcano erupts near island village"]


def test_story_used_by_an_earlier_topic_is_skipped():  # AC-2.8
    earlier = [story("Rocket launch delayed by weather")]
    feed = [story("Rocket launch delayed by weather"), story("Markets close higher on Friday")]
    assert titles(choose_stories([feed], 5, earlier)) == ["Markets close higher on Friday"]


def test_different_stories_sharing_one_word_are_both_kept():
    feed = [story("Tesla shares jump"), story("Tesla recalls trucks")]
    assert len(choose_stories([feed], 5, [])) == 2


def test_a_region_story_is_always_included():  # AC-2.7
    world_one = [story("Parliament votes tonight"), story("Summit ends early")]
    world_two = [story("Storm closes airports")]
    region = [story("Yangon market reopens", region=True)]
    chosen = choose_stories([world_one, world_two, region], 2, [])
    assert titles(chosen) == ["Parliament votes tonight", "Yangon market reopens"]


def test_fewer_stories_than_asked_returns_what_exists():
    assert len(choose_stories([[story("Only story here")]], 5, [])) == 1
