"""Write the finished page into the output folder."""
import json
import re
import shutil
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from briefing.config import topics_key

HERE = Path(__file__).parent
THAILAND = timezone(timedelta(hours=7))


def section_for(topic, stories):
    """Everything the page needs to draw one topic."""
    name = topic["name"].strip()
    key = name.lower()
    return {
        "name": name,
        "key": key,
        "slug": "topic-" + (re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "x"),
        "hue": zlib.crc32(key.encode("utf-8")) % 360,  # same name, same colour, every day
        "icon": topic.get("icon") or name[0].upper(),
        "high": topic.get("priority") == "high",
        "stories": stories,
    }


def render_page(sections, settings, now, repo, out_dir="site"):
    """Write index.html, status.json and the static files into out_dir."""
    built = datetime.fromtimestamp(now, THAILAND)
    key = topics_key(settings)
    environment = Environment(loader=FileSystemLoader(HERE / "templates"),
                              autoescape=select_autoescape(["html"]))
    page = environment.get_template("page.html").render(
        sections=sections,
        built_date=built.strftime("%A, %d %B %Y"),
        built_time=built.strftime("%H:%M"),
        config={"repo": repo, "builtKey": key, "builtDay": built.strftime("%Y-%m-%d")},
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    for file in (HERE / "static").iterdir():
        shutil.copy(file, out / file.name)
    status = {"built_at": built.isoformat(), "topics_key": key}
    (out / "status.json").write_text(json.dumps(status), encoding="utf-8")
