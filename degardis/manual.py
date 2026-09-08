from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.resources import files

import yaml

from .model import CURRENT_FORMAT_VERSION


MANUAL_DIR = "manual_topics"
CATALOG = "topics.yaml"
TOPICS_PLACEHOLDER = "{{topics}}"


@dataclass(frozen=True)
class Topic:
    name: str
    summary: str
    related: tuple[str, ...] = ()


def _resource(name: str) -> str:
    return files("degardis").joinpath(MANUAL_DIR, name).read_text(encoding="utf-8")


def _resolve(text: str) -> str:
    """Substitute at read time, so a manual file states the placeholder and the
    version the compiler accepts is the only one any reader can be shown."""
    return text.replace("{{format_version}}", str(CURRENT_FORMAT_VERSION))


def _load_catalog() -> tuple[Topic, ...]:
    """Read the catalog that sits beside the topics it describes.

    It is data rather than code: a name, a summary, and a cross-reference
    describe the topic files beside it. The catalog carries topics and nothing
    else, so every entry in it is a name `degardis manual` prints, and prose
    no such name reaches stays in the template the document form of the manual
    is generated from.
    """
    catalog = yaml.safe_load(_resource(CATALOG))
    return tuple(
        Topic(item["name"], item["summary"], tuple(item.get("related", ())))
        for item in catalog["topics"]
    )


TOPICS = _load_catalog()


def read_topic(name: str) -> str:
    return _resolve(_resource(name + ".md")).strip()


def topic_title(topic: Topic) -> str:
    return read_topic(topic.name).splitlines()[0].lstrip("# ")


def topic_anchor(topic: Topic) -> str:
    return re.sub(r"[^\w\- ]", "", topic_title(topic).lower()).replace(" ", "-")


def describe_topics() -> str:
    width = max(len(topic.name) for topic in TOPICS)
    return "\n".join(f"  {topic.name:<{width}}  {topic.summary}" for topic in TOPICS)


def _related(topic: Topic, *, cli: bool) -> str:
    catalog = {item.name: item for item in TOPICS}
    if cli:
        links = list(topic.related)
    else:
        links = [f"[{topic_title(catalog[name])}](#{topic_anchor(catalog[name])})" for name in topic.related]
    return "\n\nSee also: " + ", ".join(links) + "." if links else ""


def render_topic(topic: Topic) -> str:
    """Print one topic, restating its document links as the topics they name.

    A link a reader cannot follow has to say where to look instead, which is the
    topic's own name: the reference is what the sentence carries, and rendering
    it as a command would put an instruction in the reader's way that its author
    never wrote.
    """
    anchors = {topic_anchor(item): item.name for item in TOPICS}
    lines = read_topic(topic.name).splitlines()
    lines[0] = "# " + lines[0].lstrip("# ")
    fence = ""
    for index, line in enumerate(lines):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            run = marker.group(1)
            if not fence:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not line[marker.end():].strip():
                fence = ""
        elif not fence:
            lines[index] = re.sub(
                r"\[([^\]]+)\]\(#([\w-]+)\)",
                lambda match: f"{match[1]} (see {anchors[match[2]]})",
                line,
            )
    return "\n".join(lines) + _related(topic, cli=True) + "\n"


def render_manual(template: str) -> str:
    """Fill a document template with the same topics the CLI prints.

    The caller supplies the template rather than this package holding it.
    The document's heading, its lead, and any section that is not a topic
    are prose no installed CLI can reach, so keeping them beside the topics
    would ship text the manual directory cannot print, and keeping them
    here would write part of the manual in Python. A template carrying no
    placeholder is refused: substituting nothing would generate a manual
    with every topic missing, which the staleness check would then call
    current.
    """
    if TOPICS_PLACEHOLDER not in template:
        raise ValueError(f"The manual template must contain {TOPICS_PLACEHOLDER}.")
    body = "\n\n".join(read_topic(topic.name) + _related(topic, cli=False) for topic in TOPICS)
    return _resolve(template).replace(TOPICS_PLACEHOLDER, body)
