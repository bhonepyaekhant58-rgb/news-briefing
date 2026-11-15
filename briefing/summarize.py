"""Write a short summary for every story, with the feed's own text as the fallback."""
import json
import re

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BATCH = 10

PROMPT = """You write summaries for a personal news page.
For each story below, write a summary of at most 2 short sentences in plain English.
Use only facts found in that story's title and description. Do not add anything else.
Reply with JSON only: a list of objects like {"id": 0, "summary": "..."}.

Stories:
"""


def two_sentences(text):
    """Keep at most the first two sentences."""
    parts = re.split(r"(?<![A-Z]\.)(?<=[.!?])\s+", " ".join((text or "").split()))
    return " ".join(parts[:2])


def call_gemini(prompt, model, api_key):
    """Send one request to Gemini and return its reply text."""
    response = requests.post(
        API.format(model=model),
        headers={"x-goog-api-key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json"}},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def summarize_stories(stories, cache, model, api_key, max_requests=8, ask=call_gemini):
    """Fill story['summary'] for every story. Returns the number of AI requests used."""
    for story in stories:
        story["summary"] = cache.get(story["link"], "")
    todo = [story for story in stories if not story["summary"] and not story.get("history")]
    used = 0
    if api_key and todo:
        size = max(BATCH, -(-len(todo) // max(1, max_requests)))  # -(-a // b) rounds up
        for start in range(0, len(todo), size):
            batch = todo[start:start + size]
            listing = json.dumps(
                [{"id": number, "title": story["title"], "description": story["description"]}
                 for number, story in enumerate(batch)], ensure_ascii=False)
            used += 1
            try:
                for answer in json.loads(ask(PROMPT + listing, model, api_key)):
                    story = batch[int(answer["id"])]
                    story["summary"] = two_sentences(str(answer["summary"]))
                    cache[story["link"]] = story["summary"]
            except Exception as error:  # any failure falls back to the feed's own text
                print(f"  AI request failed, using feed descriptions: {error}")
    for story in stories:
        if not story["summary"]:
            story["summary"] = two_sentences(story["description"])
    return used
