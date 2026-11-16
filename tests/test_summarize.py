import json

import requests

from briefing.summarize import call_gemini, summarize_stories, first_sentences

MODEL = "gemini-flash-lite-latest"


def http_error(status):
    """A requests error that carries an HTTP status, like the real service sends."""
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


def story(number):
    return {"title": f"Title {number}", "link": f"https://example.com/{number}",
            "description": "Feed text one. Feed text two. Feed text three. Feed text four."}


def fake_ask(calls):
    def ask(prompt, model, api_key):
        calls.append(prompt)
        listing = json.loads(prompt.split("Stories:\n", 1)[1])
        return json.dumps([{"id": entry["id"],
                            "summary": f"AI summary of {entry['title']}. Second. Third. Fourth."}
                           for entry in listing])
    return ask


def test_first_sentences_keeps_only_three():  # AC-3.1
    assert first_sentences("One.  Two!\nThree? Four.") == "One. Two! Three?"
    assert first_sentences("The U.S. Senate voted. It passed.") == "The U.S. Senate voted. It passed."
    assert first_sentences("One. Two. Three.", 2) == "One. Two."
    assert first_sentences("") == ""


def test_ai_summary_is_used_and_trimmed():  # AC-3.1
    stories, cache, calls = [story(0)], {}, []
    used = summarize_stories(stories, cache, MODEL, "key", ask=fake_ask(calls))
    assert stories[0]["summary"] == "AI summary of Title 0. Second. Third."
    assert cache == {"https://example.com/0": "AI summary of Title 0. Second. Third."}
    assert used == 1


def test_prompt_asks_for_context_from_the_feed_only():  # FR-4
    calls = []
    summarize_stories([story(0)], {}, MODEL, "key", ask=fake_ask(calls))
    assert "at most 3 short sentences" in calls[0] and "Use only facts" in calls[0]


def test_cached_summaries_are_not_requested_again():
    stories, calls = [story(0), story(1)], []
    cache = {"https://example.com/0": "Saved earlier."}
    summarize_stories(stories, cache, MODEL, "key", ask=fake_ask(calls))
    assert stories[0]["summary"] == "Saved earlier."
    assert len(calls) == 1 and '"Title 0"' not in calls[0] and '"Title 1"' in calls[0]


def test_at_most_8_requests_for_a_full_page():
    stories, calls = [story(number) for number in range(80)], []
    assert summarize_stories(stories, {}, MODEL, "key", ask=fake_ask(calls)) == 8
    assert len(calls) == 8 and all(item["summary"] for item in stories)


def test_failed_request_falls_back_to_the_feed_text():  # AC-6.1
    def broken(prompt, model, api_key):
        raise RuntimeError("limit reached")

    stories = [story(0)]
    summarize_stories(stories, {}, MODEL, "key", ask=broken)
    assert stories[0]["summary"] == "Feed text one. Feed text two. Feed text three."


def test_no_key_means_no_requests():  # AC-6.1
    stories, calls = [story(0)], []
    assert summarize_stories(stories, {}, MODEL, "", ask=fake_ask(calls)) == 0
    assert calls == [] and stories[0]["summary"] == "Feed text one. Feed text two. Feed text three."


def test_history_stories_are_not_sent_to_the_ai():
    event, calls = dict(story(0), history=True), []
    assert summarize_stories([event], {}, MODEL, "key", ask=fake_ask(calls)) == 0
    assert event["summary"] == "Feed text one. Feed text two. Feed text three."


def test_call_gemini_keeps_the_key_out_of_the_address(monkeypatch):
    sent = {}

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}

    def post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, body=json)
        return Reply()

    monkeypatch.setattr("briefing.summarize.requests.post", post)
    assert call_gemini("hello", MODEL, "secret") == "[]"
    assert sent["url"].endswith("/models/gemini-flash-lite-latest:generateContent")
    assert "secret" not in sent["url"] and sent["headers"]["x-goog-api-key"] == "secret"
    assert sent["body"]["contents"][0]["parts"][0]["text"] == "hello"


def test_request_cap_cannot_be_raised_above_8():
    stories, calls = [story(number) for number in range(200)], []
    assert summarize_stories(stories, {}, MODEL, "key", max_requests=20, ask=fake_ask(calls)) == 8
    assert len(calls) == 8


def test_a_refused_request_ends_the_requests():  # AC-6.1
    calls = []

    def refused(prompt, model, api_key):
        calls.append(prompt)
        raise http_error(429)

    stories = [story(number) for number in range(25)]
    assert summarize_stories(stories, {}, MODEL, "key", ask=refused) == 1
    assert len(calls) == 1
    assert all(item["summary"] == "Feed text one. Feed text two. Feed text three." for item in stories)


def failing_first_call(calls, error):
    """An ask that raises `error` on the first call only, then answers like fake_ask."""
    normal = fake_ask(calls)

    def ask(prompt, model, api_key):
        if not calls:
            calls.append(prompt)
            raise error
        return normal(prompt, model, api_key)
    return ask


def test_one_failed_request_does_not_stop_the_rest():  # AC-6.1
    calls = []
    stories = [story(number) for number in range(25)]
    ask = failing_first_call(calls, http_error(503))
    assert summarize_stories(stories, {}, MODEL, "key", ask=ask) == 3
    assert len(calls) == 3
    assert all(item["summary"] == "Feed text one. Feed text two. Feed text three."
               for item in stories[:10])
    assert all(item["summary"] == f"AI summary of {item['title']}. Second. Third."
               for item in stories[10:])


def test_a_request_with_no_reply_does_not_stop_the_rest():  # AC-6.1
    calls = []
    stories = [story(number) for number in range(25)]
    ask = failing_first_call(calls, requests.ConnectionError("offline"))
    assert summarize_stories(stories, {}, MODEL, "key", ask=ask) == 3
    assert len(calls) == 3


def test_the_ai_is_given_the_detail_text():  # AC-3.4
    item, calls = story(0), []
    item["detail"] = "Article text with many facts."
    summarize_stories([item], {}, MODEL, "key", ask=fake_ask(calls))
    assert "Article text with many facts." in calls[0]
    assert item["description"] not in calls[0]


def test_without_detail_the_description_is_sent():
    item, calls = story(0), []
    summarize_stories([item], {}, MODEL, "key", ask=fake_ask(calls))
    assert item["description"] in calls[0]


def test_prompt_tells_the_ai_to_ignore_page_clutter():
    calls = []
    summarize_stories([story(0)], {}, MODEL, "key", ask=fake_ask(calls))
    assert "Ignore" in calls[0]
