import json

from briefing.summarize import call_gemini, summarize_stories, two_sentences

MODEL = "gemini-flash-lite-latest"


def story(number):
    return {"title": f"Title {number}", "link": f"https://example.com/{number}",
            "description": "Feed text one. Feed text two. Feed text three."}


def fake_ask(calls):
    def ask(prompt, model, api_key):
        calls.append(prompt)
        listing = json.loads(prompt.split("Stories:\n", 1)[1])
        return json.dumps([{"id": entry["id"],
                            "summary": f"AI summary of {entry['title']}. Second. Third."}
                           for entry in listing])
    return ask


def test_two_sentences_keeps_only_two():  # AC-3.1
    assert two_sentences("One.  Two!\nThree? Four.") == "One. Two!"
    assert two_sentences("The U.S. Senate voted. It passed.") == "The U.S. Senate voted. It passed."
    assert two_sentences("") == ""


def test_ai_summary_is_used_and_trimmed():  # AC-3.1
    stories, cache, calls = [story(0)], {}, []
    used = summarize_stories(stories, cache, MODEL, "key", ask=fake_ask(calls))
    assert stories[0]["summary"] == "AI summary of Title 0. Second."
    assert cache == {"https://example.com/0": "AI summary of Title 0. Second."}
    assert used == 1


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
    assert stories[0]["summary"] == "Feed text one. Feed text two."


def test_no_key_means_no_requests():  # AC-6.1
    stories, calls = [story(0)], []
    assert summarize_stories(stories, {}, MODEL, "", ask=fake_ask(calls)) == 0
    assert calls == [] and stories[0]["summary"] == "Feed text one. Feed text two."


def test_history_stories_are_not_sent_to_the_ai():
    event, calls = dict(story(0), history=True), []
    assert summarize_stories([event], {}, MODEL, "key", ask=fake_ask(calls)) == 0
    assert event["summary"] == "Feed text one. Feed text two."


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
