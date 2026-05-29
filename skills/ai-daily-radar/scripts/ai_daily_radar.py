#!/usr/bin/env python3
"""Generate a lightweight AI Daily Radar Markdown report."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import os
import re
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Candidate:
    title: str
    url: str
    source: str
    published: dt.datetime | None
    heat: float
    heat_label: str
    priority: float
    source_type: str = "news"
    snippet: str = ""
    title_zh: str = ""
    summary_zh: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    score_reasons: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        score = 2.0 + self.priority
        if self.published:
            age_hours = max(0.0, (now_utc() - self.published).total_seconds() / 3600)
            score += max(0.0, 1.4 - age_hours / 48)
        else:
            score += 0.5
        score += min(2.0, (self.heat ** 0.5) / 15)
        score += min(1.5, keyword_score(self.title + " " + self.snippet) / 10)
        if self.source_type == "github_repo":
            delta = float(self.metrics.get("stars_delta_24h") or 0)
            score += min(2.2, delta / 40)
            score += min(0.4, float(self.metrics.get("stars") or 0) / 30000)
            if delta <= 0 and self.source.startswith("GitHub Search"):
                score -= 1.2
        return round(min(10.0, score), 2)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def fetch_text(url: str, timeout: int, user_agent: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)


def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_timestamp(value: int | float | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)


def keyword_score(text: str) -> float:
    lowered = text.lower()
    strong = [
        "openai",
        "anthropic",
        "deepmind",
        "llama",
        "qwen",
        "deepseek",
        "mistral",
        "hugging face",
        "agent",
        "agents",
        "llm",
        "inference",
        "benchmark",
        "multimodal",
        "reasoning",
        "rag",
        "mcp",
    ]
    return sum(4.0 for word in strong if word in lowered)


def is_ai_related(candidate: Candidate, keywords: list[str]) -> bool:
    text = f"{candidate.title} {candidate.snippet}".lower()
    if is_low_information(candidate):
        return False
    return any(keyword_matches(text, keyword) for keyword in keywords)


def keyword_matches(text: str, keyword: str) -> bool:
    keyword = keyword.lower()
    if not keyword:
        return False
    if re.search(r"[^a-z0-9 ]", keyword):
        return keyword in text
    pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def is_low_information(candidate: Candidate) -> bool:
    title = candidate.title.strip()
    normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    words = re.findall(r"[A-Za-z0-9.+-]+", title)
    low_context_url = re.search(r"\.(png|jpg|jpeg|gif|webp)$|i\.redd\.it|v\.redd\.it|reddit\.com/gallery", candidate.url)
    generic_titles = {
        "thats a good news",
        "that s a good news",
        "good news",
        "finally",
        "this is huge",
        "wow",
    }
    strong_title_markers = [
        "llm",
        "model",
        "agent",
        "qwen",
        "llama",
        "deepseek",
        "mistral",
        "gemma",
        "claude",
        "gemini",
        "openai",
        "anthropic",
        "mtp",
        "llama.cpp",
    ]
    has_strong_title_marker = any(marker in title.lower() for marker in strong_title_markers)
    if normalized_title in generic_titles:
        return True
    return bool(low_context_url and len(words) <= 5 and not has_strong_title_marker)


def hn_candidates(config: dict[str, Any]) -> list[Candidate]:
    source_config = config["sources"].get("hacker_news", {})
    if not source_config.get("enabled"):
        return []
    timeout = config["timeout_seconds"]
    user_agent = config["user_agent"]
    candidates: list[Candidate] = []
    seen_ids: set[int] = set()
    item_ids: list[int] = []
    max_items_total = int(source_config.get("max_items_total", 60))
    for story_list in source_config.get("story_lists", []):
        if len(item_ids) >= max_items_total:
            break
        ids_url = f"https://hacker-news.firebaseio.com/v0/{story_list}.json"
        try:
            ids = json.loads(fetch_text(ids_url, timeout, user_agent))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        for item_id in ids[: source_config.get("limit_per_list", 50)]:
            if len(item_ids) >= max_items_total:
                break
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            item_ids.append(item_id)

    def fetch_hn_item(item_id: int) -> Candidate | None:
        item_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
        try:
            item = json.loads(fetch_text(item_url, timeout, user_agent))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None
        if item.get("type") != "story" or not item.get("title"):
            return None
        points = float(item.get("score") or 0)
        comments = float(item.get("descendants") or 0)
        url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
        heat = points + comments * 1.5
        return Candidate(
            title=clean_text(item["title"]),
            url=url,
            source="Hacker News",
            published=parse_timestamp(item.get("time")),
            heat=heat,
            heat_label=f"{int(points)} points, {int(comments)} comments",
            priority=1.2,
        )

    with ThreadPoolExecutor(max_workers=int(source_config.get("workers", 12))) as pool:
        for result in pool.map(fetch_hn_item, item_ids):
            if result is not None:
                candidates.append(result)
    return candidates


def reddit_candidates(config: dict[str, Any]) -> list[Candidate]:
    source_config = config["sources"].get("reddit", {})
    if not source_config.get("enabled"):
        return []
    timeout = config["timeout_seconds"]
    user_agent = config["user_agent"]
    candidates: list[Candidate] = []
    feeds = [
        (subreddit, sort)
        for subreddit in source_config.get("subreddits", [])
        for sort in source_config.get("sorts", ["hot"])
    ]

    def fetch_reddit_feed(feed: tuple[str, str]) -> list[Candidate]:
        subreddit, sort = feed
        limit = source_config.get("limit_per_feed", 30)
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"
        try:
            payload = json.loads(fetch_text(url, timeout, user_agent))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return []
        results: list[Candidate] = []
        for child in payload.get("data", {}).get("children", []):
            data = child.get("data", {})
            title = data.get("title")
            if not title or data.get("stickied"):
                continue
            score = float(data.get("score") or 0)
            comments = float(data.get("num_comments") or 0)
            permalink = "https://www.reddit.com" + data.get("permalink", "")
            results.append(
                Candidate(
                    title=clean_text(title),
                    url=data.get("url_overridden_by_dest") or permalink,
                    source=f"r/{subreddit}/{sort}",
                    published=parse_timestamp(data.get("created_utc")),
                    heat=score + comments * 1.5,
                    heat_label=f"{int(score)} upvotes, {int(comments)} comments",
                    priority=1.3 if subreddit == "LocalLLaMA" else 1.1,
                    snippet=clean_text(data.get("selftext", ""))[:500],
                )
            )
        return results

    with ThreadPoolExecutor(max_workers=int(source_config.get("workers", 4))) as pool:
        for result in pool.map(fetch_reddit_feed, feeds):
            candidates.extend(result)
    return candidates


def rss_candidates(config: dict[str, Any]) -> list[Candidate]:
    source_config = config["sources"].get("rss", {})
    if not source_config.get("enabled"):
        return []
    timeout = config["timeout_seconds"]
    user_agent = config["user_agent"]
    candidates: list[Candidate] = []

    def fetch_rss_feed(feed: dict[str, Any]) -> list[Candidate]:
        try:
            xml = fetch_text(feed["url"], timeout, user_agent)
            root = ET.fromstring(xml)
        except (urllib.error.URLError, TimeoutError, ET.ParseError):
            return []
        results: list[Candidate] = []
        entries = root.findall(".//item") or root.findall("{http://www.w3.org/2005/Atom}entry")
        for entry in entries[:30]:
            title = entry.findtext("title") or entry.findtext("{http://www.w3.org/2005/Atom}title")
            if not title:
                continue
            link = entry.findtext("link")
            if link is None:
                link_node = entry.find("{http://www.w3.org/2005/Atom}link")
                link = link_node.attrib.get("href") if link_node is not None else ""
            published = (
                entry.findtext("pubDate")
                or entry.findtext("published")
                or entry.findtext("{http://www.w3.org/2005/Atom}published")
                or entry.findtext("{http://www.w3.org/2005/Atom}updated")
            )
            summary = (
                entry.findtext("description")
                or entry.findtext("summary")
                or entry.findtext("{http://www.w3.org/2005/Atom}summary")
                or ""
            )
            results.append(
                Candidate(
                    title=clean_text(title),
                    url=link or feed["url"],
                    source=feed["name"],
                    published=parse_date(published),
                    heat=15.0,
                    heat_label="feed item",
                    priority=float(feed.get("priority", 1.0)),
                    snippet=clean_text(strip_tags(summary))[:500],
                )
            )
        return results

    with ThreadPoolExecutor(max_workers=int(source_config.get("workers", 8))) as pool:
        for result in pool.map(fetch_rss_feed, source_config.get("feeds", [])):
            candidates.extend(result)
    return candidates


def github_trending_candidates(config: dict[str, Any]) -> list[Candidate]:
    source_config = config["sources"].get("github", {})
    if not source_config.get("enabled"):
        return []
    candidates: list[Candidate] = []
    repo_records: dict[str, dict[str, Any]] = {}
    try:
        page = fetch_text(source_config["trending_url"], config["timeout_seconds"], config["user_agent"])
    except (urllib.error.URLError, TimeoutError):
        page = ""
    article_pattern = re.compile(r"<article.*?</article>", re.S)
    repo_pattern = re.compile(r'<h2 class="h3 lh-condensed">\s*<a href="([^"]+)">\s*(.*?)\s*</a>', re.S)
    desc_pattern = re.compile(r'<p class="col-9 color-fg-muted my-1 pr-4">(.*?)</p>', re.S)
    stars_today_pattern = re.compile(r"([0-9,]+)\s+stars?\s+today")
    stars_pattern = re.compile(r'<a[^>]+stargazers[^>]*>\s*([0-9,]+)\s*</a>', re.S)
    for article in article_pattern.findall(page)[: source_config.get("limit", 50)]:
        repo_match = repo_pattern.search(article)
        if not repo_match:
            continue
        href, raw_title = repo_match.groups()
        full_name = clean_text(strip_tags(raw_title)).replace(" / ", "/")
        if not full_name or "/" not in full_name:
            continue
        desc_match = desc_pattern.search(article)
        description = clean_text(strip_tags(desc_match.group(1))) if desc_match else ""
        stars_today_match = stars_today_pattern.search(clean_text(strip_tags(article)))
        stars_match = stars_pattern.search(article)
        stars = parse_int(stars_match.group(1)) if stars_match else 0
        stars_delta = parse_int(stars_today_match.group(1)) if stars_today_match else 0
        repo_url = urllib.parse.urljoin("https://github.com", href.strip())
        repo_records[full_name] = {
            "full_name": full_name,
            "url": repo_url,
            "description": description,
            "stars": stars,
            "stars_delta_24h": stars_delta,
            "source": "GitHub Trending",
        }

    if source_config.get("search_enabled", True):
        for record in github_search_records(config, source_config):
            repo_records.setdefault(record["full_name"], record)

    enrich_github_growth(repo_records, source_config)
    save_github_snapshot(repo_records, source_config)

    for record in repo_records.values():
        if not is_ai_repo_record(record, config.get("keywords", [])):
            continue
        stars = int(record.get("stars") or 0)
        delta = int(record.get("stars_delta_24h") or 0)
        description = clean_text(record.get("description") or "")
        heat = float(delta * 4 + min(stars, 50000) / 2000)
        label_bits = []
        if stars:
            label_bits.append(f"{stars} stars")
        if delta:
            label_bits.append(f"+{delta} stars/24h")
        heat_label = ", ".join(label_bits) if label_bits else "GitHub AI repo"
        candidates.append(
            Candidate(
                title=f"GitHub AI Repo: {record['full_name']}",
                url=record["url"],
                source=record.get("source", "GitHub Search"),
                source_type="github_repo",
                published=parse_date(record.get("pushed_at")),
                heat=heat,
                heat_label=heat_label,
                priority=1.45,
                snippet=description,
                metrics={
                    "stars": stars,
                    "stars_delta_24h": delta,
                    "forks": int(record.get("forks") or 0),
                    "language": record.get("language") or "",
                    "topics": record.get("topics") or [],
                },
            )
        )
    return candidates


def github_search_records(config: dict[str, Any], source_config: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    pushed_after = (dt.datetime.now().date() - dt.timedelta(days=14)).isoformat()
    created_after = (dt.datetime.now().date() - dt.timedelta(days=int(source_config.get("created_within_days", 180)))).isoformat()
    limit = int(source_config.get("search_limit_per_topic", 10))
    headers_user_agent = config["user_agent"]
    for topic in source_config.get("topics", []):
        query = f'topic:{topic} pushed:>={pushed_after} created:>={created_after} stars:>10'
        params = urllib.parse.urlencode({"q": query, "sort": "stars", "order": "desc", "per_page": limit})
        url = f"https://api.github.com/search/repositories?{params}"
        try:
            payload = json.loads(fetch_text(url, config["timeout_seconds"], headers_user_agent))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        for item in payload.get("items", []):
            full_name = item.get("full_name")
            if not full_name:
                continue
            records.append(
                {
                    "full_name": full_name,
                    "url": item.get("html_url") or f"https://github.com/{full_name}",
                    "description": item.get("description") or "",
                    "stars": int(item.get("stargazers_count") or 0),
                    "forks": int(item.get("forks_count") or 0),
                    "language": item.get("language") or "",
                    "topics": item.get("topics") or [],
                    "pushed_at": item.get("pushed_at") or "",
                    "source": f"GitHub Search/new-topic:{topic}",
                }
            )
    return records


def enrich_github_growth(repo_records: dict[str, dict[str, Any]], source_config: dict[str, Any]) -> None:
    snapshot = load_github_snapshot(source_config)
    previous = snapshot.get("repos", {})
    for full_name, record in repo_records.items():
        current_stars = int(record.get("stars") or 0)
        if record.get("stars_delta_24h"):
            continue
        previous_stars = int(previous.get(full_name, {}).get("stars") or 0)
        record["stars_delta_24h"] = max(0, current_stars - previous_stars) if previous_stars else 0


def load_github_snapshot(source_config: dict[str, Any]) -> dict[str, Any]:
    return load_json_file(ROOT / source_config.get("snapshot_file", "outputs/github_repo_snapshots.json"))


def save_github_snapshot(repo_records: dict[str, dict[str, Any]], source_config: dict[str, Any]) -> None:
    path = ROOT / source_config.get("snapshot_file", "outputs/github_repo_snapshots.json")
    snapshot = {
        "date": dt.datetime.now().date().isoformat(),
        "repos": {
            full_name: {
                "stars": int(record.get("stars") or 0),
                "url": record.get("url") or "",
                "description": record.get("description") or "",
            }
            for full_name, record in sorted(repo_records.items())
        },
    }
    write_json_file(path, snapshot)


def is_ai_repo_record(record: dict[str, Any], keywords: list[str]) -> bool:
    text = " ".join(
        [
            record.get("full_name") or "",
            record.get("description") or "",
            record.get("language") or "",
            " ".join(record.get("topics") or []),
        ]
    ).lower()
    return any(keyword_matches(text, keyword) for keyword in keywords)


def parse_int(value: str) -> int:
    try:
        return int(value.replace(",", "").strip())
    except (AttributeError, ValueError):
        return 0


def hugging_face_papers_candidates(config: dict[str, Any]) -> list[Candidate]:
    source_config = config["sources"].get("hugging_face_papers", {})
    if not source_config.get("enabled"):
        return []
    try:
        page = fetch_text(source_config["url"], config["timeout_seconds"], config["user_agent"])
    except (urllib.error.URLError, TimeoutError):
        return []
    candidates: list[Candidate] = []
    pattern = re.compile(r'href="(/papers/[^"]+)".{0,800}?<h3[^>]*>(.*?)</h3>', re.S)
    for href, raw_title in pattern.findall(page)[: source_config.get("limit", 30)]:
        title = clean_text(strip_tags(raw_title))
        if not title:
            continue
        candidates.append(
            Candidate(
                title=title,
                url=urllib.parse.urljoin("https://huggingface.co", href),
                source="Hugging Face Daily Papers",
                published=None,
                heat=22.0,
                heat_label="HF daily paper",
                priority=1.2,
            )
        )
    return candidates


def clean_text(text: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]+", " ", candidate.title.lower()).strip()
        key = " ".join(key.split()[:12])
        current = best.get(key)
        if current is None or candidate.score > current.score:
            best[key] = candidate
    return list(best.values())


def assign_score_reasons(candidates: list[Candidate]) -> None:
    for candidate in candidates:
        reasons: list[str] = []
        if candidate.source_type == "github_repo":
            delta = int(candidate.metrics.get("stars_delta_24h") or 0)
            stars = int(candidate.metrics.get("stars") or 0)
            if delta:
                reasons.append(f"GitHub star 增长较快：24h +{delta}")
            if stars:
                reasons.append(f"已有基础关注度：{stars} stars")
            topics = candidate.metrics.get("topics") or []
            if topics:
                reasons.append("AI topic 命中：" + ", ".join(str(topic) for topic in topics[:4]))
        if candidate.published:
            age_hours = max(0.0, (now_utc() - candidate.published).total_seconds() / 3600)
            if age_hours <= 24:
                reasons.append("24 小时内新内容")
            elif age_hours <= 48:
                reasons.append("48 小时内新内容")
        if candidate.heat > 100:
            reasons.append(f"社区热度高：{candidate.heat_label}")
        elif candidate.heat_label:
            reasons.append(candidate.heat_label)
        matched = matched_keywords(candidate)
        if matched:
            reasons.append("AI 相关信号：" + ", ".join(matched[:5]))
        if candidate.source in {"OpenAI News", "Anthropic News", "Google DeepMind Blog"}:
            reasons.append("官方来源")
        candidate.score_reasons = reasons[:5]


def matched_keywords(candidate: Candidate) -> list[str]:
    text = f"{candidate.title} {candidate.snippet}".lower()
    keywords = [
        "agent",
        "llm",
        "model",
        "qwen",
        "deepseek",
        "claude",
        "openai",
        "anthropic",
        "mcp",
        "rag",
        "inference",
        "benchmark",
        "llama.cpp",
        "vllm",
        "github",
    ]
    return [keyword for keyword in keywords if keyword_matches(text, keyword)]


def translate_titles(candidates: list[Candidate], config: dict[str, Any]) -> None:
    translation_config = config.get("title_translation", {})
    if not translation_config.get("enabled", False):
        return

    cache_path = ROOT / translation_config.get("cache_file", "outputs/title_translation_cache.json")
    cache = load_json_file(cache_path)
    missing = [candidate.title for candidate in candidates if candidate.title not in cache]

    def translate(title: str) -> tuple[str, str]:
        try:
            return title, translate_title_google(title, translation_config, config)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, KeyError, IndexError):
            return title, ""

    if missing:
        with ThreadPoolExecutor(max_workers=int(translation_config.get("workers", 5))) as pool:
            for title, translated in pool.map(translate, missing):
                if translated:
                    cache[title] = translated
        write_json_file(cache_path, cache)

    for candidate in candidates:
        candidate.title_zh = str(cache.get(candidate.title, "")).strip()


def translate_title_google(title: str, translation_config: dict[str, Any], config: dict[str, Any]) -> str:
    return translate_text_google(
        title,
        translation_config.get("source_language", "en"),
        translation_config.get("target_language", "zh-CN"),
        config,
    )


def translate_text_google(text: str, source_language: str, target_language: str, config: dict[str, Any]) -> str:
    params = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": source_language,
            "tl": target_language,
            "dt": "t",
            "q": text,
        }
    )
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    payload = json.loads(fetch_text(url, int(config.get("timeout_seconds", 8)), config["user_agent"]))
    translated = "".join(segment[0] for segment in payload[0] if segment and segment[0])
    return clean_text(translated)


def summarize_items(candidates: list[Candidate], config: dict[str, Any]) -> None:
    summary_config = config.get("content_summary", {})
    if not summary_config.get("enabled", True):
        return

    cache_path = ROOT / summary_config.get("cache_file", "outputs/content_summary_cache.json")
    cache = load_json_file(cache_path)
    missing = [candidate for candidate in candidates if summary_cache_key(candidate, summary_config) not in cache]

    def summarize(candidate: Candidate) -> tuple[str, str]:
        key = summary_cache_key(candidate, summary_config)
        if os.environ.get("OPENAI_API_KEY") and summary_config.get("provider") == "openai":
            try:
                return key, summarize_with_openai(candidate, summary_config, config)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, KeyError, IndexError):
                return key, fallback_summary(candidate, config)
        return key, fallback_summary(candidate, config)

    if missing:
        with ThreadPoolExecutor(max_workers=int(summary_config.get("workers", 4))) as pool:
            for key, summary in pool.map(summarize, missing):
                if summary:
                    cache[key] = summary
        write_json_file(cache_path, cache)

    for candidate in candidates:
        candidate.summary_zh = str(cache.get(summary_cache_key(candidate, summary_config), "")).strip()


def summary_cache_key(candidate: Candidate, summary_config: dict[str, Any]) -> str:
    style_version = summary_config.get("style_version", "plain_summary_v4")
    key_source = f"{style_version} {candidate.title} {candidate.url}"
    return re.sub(r"\s+", " ", key_source).strip()


def summarize_with_openai(candidate: Candidate, summary_config: dict[str, Any], config: dict[str, Any]) -> str:
    prompt = (
        "请用中文为一条 AI 资讯写一段给技术开发者看的摘要。"
        "要求：2-3 句，直接说明内容本身，不要重复标题，不要使用“精髓”“核心信息是”“这条来自”等标签或套路化开头。"
        "如果标题或片段里有不常见名词、缩写或项目名，请在句中用括号简短解释，例如 TTFT、MTP、llama.cpp、Jetson、Terminal-Bench。"
        "只基于给定材料，不要编造没有出现的信息。\n\n"
        f"英文标题：{candidate.title}\n"
        f"中文标题：{candidate.title_zh or '无'}\n"
        f"来源：{candidate.source}\n"
        f"热度：{candidate.heat_label}\n"
        f"内容片段：{candidate.snippet or '无'}\n"
    )
    body = json.dumps(
        {
            "model": summary_config.get("model", "gpt-4.1-mini"),
            "messages": [
                {"role": "system", "content": "你是一个面向 AI 开发者的信息分析助手，只基于给定材料写中文摘要。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": config["user_agent"],
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=int(config.get("timeout_seconds", 8))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return clean_text(payload["choices"][0]["message"]["content"])


def fallback_summary(candidate: Candidate, config: dict[str, Any] | None = None) -> str:
    snippet = clean_text(candidate.snippet)
    terms = explain_terms(candidate)
    term_text = f"\n\n名词解释：{terms}。" if terms else ""
    if snippet:
        return f"{humanize_snippet(snippet, config)}{term_text}"
    return f"{infer_essence_from_title(candidate)}{term_text}"


def humanize_snippet(snippet: str, config: dict[str, Any] | None = None) -> str:
    snippet = truncate_text(snippet, 220)
    snippet = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", snippet)
    snippet = snippet.replace("\\_", "_")
    translated = ""
    if config is not None:
        try:
            translated = translate_text_google(snippet, "auto", "zh-CN", config)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, KeyError, IndexError):
            translated = ""
    if translated:
        return translated
    return "公开片段暂时无法稳定转成中文；建议点开原文看具体上下文，重点确认实际能力、适用场景和社区反馈。"


def infer_essence_from_title(candidate: Candidate) -> str:
    text = f"{candidate.title} {candidate.title_zh}".lower()
    if any(term in text for term in ["benchmark", "leaderboard", "bench"]):
        return "这主要是在看某个模型或工具的实际成绩，重点是它是否证明了性能、成本或可用性真的变好了。"
    if any(term in text for term in ["merged", "pr ", "pull request"]):
        return "这表示某个能力已经被合入项目主线，通常意味着开发者很快可以在正式版本或源码里直接用到它。"
    if any(term in text for term in ["open-source", "open source", "github", "written in"]):
        return "这是一条开源工具或模型信号，值得看它解决了什么开发痛点、是否容易部署、社区是否真的开始使用。"
    if any(term in text for term in ["partner", "government", "roll out", "citizens"]):
        return "这不是纯技术发布，而是 AI 服务进入公共部门或大规模人群的信号，重点在普及路径、政策影响和商业模式。"
    if any(term in text for term in ["ban", "backlash", "lawsuit", "policy"]):
        return "这类消息说明 AI 正在影响研究、政策或合规边界，值得看争议背后的规则变化。"
    return "公开片段有限；先把它当作一个待核实的 AI 社区信号，点开原文看细节后再判断价值。"


def explain_terms(candidate: Candidate) -> str:
    text = f"{candidate.title} {candidate.title_zh} {candidate.snippet}".lower()
    glossary = {
        "mtp": "MTP 是多 token 预测，用来一次预测多个后续 token，目标是加速生成",
        "ttft": "TTFT 是首个 token 延迟，衡量模型开始输出前要等多久",
        "jetson": "Jetson 是 NVIDIA 的边缘 AI 计算板，常用于机器人和本地推理",
        "orin": "Orin 是 Jetson 系列里的高性能边缘 AI 芯片平台",
        "llama.cpp": "llama.cpp 是常用的本地 LLM 推理框架，适合 CPU/消费级硬件部署",
        "qwen": "Qwen 是阿里通义千问系列模型",
        "terminal-bench": "Terminal-Bench 是评测模型在终端环境中完成真实任务能力的 benchmark",
        "benchmark": "benchmark 是评测基准，用来比较模型或系统表现",
        "world model": "world model 指能学习和预测环境变化的模型，常用于视频、机器人或仿真",
        "ctf": "CTF 是安全竞赛形式，常用来测试攻防和解题能力",
        "arxiv": "arXiv 是研究论文预印本平台，很多 AI 论文会先发在这里",
        "agent": "Agent 指能调用工具、分步骤执行任务的 AI 程序",
        "rag": "RAG 是检索增强生成，让模型先查资料再回答",
        "mcp": "MCP 是模型上下文协议，用来连接模型和外部工具/数据源",
        "gguf": "GGUF 是 llama.cpp 常用的模型文件格式",
        "vllm": "vLLM 是高吞吐 LLM 推理服务框架",
    }
    explanations: list[str] = []
    for term, explanation in glossary.items():
        if term in text:
            explanations.append(explanation)
    return "；".join(explanations[:3])


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def category_for(candidate: Candidate) -> str:
    text = f"{candidate.title} {candidate.snippet}".lower()
    if any(word in text for word in ["paper", "arxiv", "benchmark", "research", "training"]):
        return "研究论文、评测或 benchmark 信号"
    if any(word in text for word in ["github", "open source", "repo", "library", "framework"]):
        return "开源项目或开发者工具"
    if any(word in text for word in ["agent", "rag", "mcp", "tool calling", "workflow"]):
        return "Agent 工具链或应用架构"
    if any(word in text for word in ["model", "llm", "llama", "qwen", "claude", "gemini", "deepseek", "mistral"]):
        return "模型能力、推理或部署"
    if any(word in text for word in ["regulation", "copyright", "safety", "policy", "lawsuit"]):
        return "安全监管、政策或商业风险"
    return "AI 生态或技术趋势"


def write_report(candidates: list[Candidate], config: dict[str, Any]) -> Path:
    output_dir = ROOT / config.get("output_dir", "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now().date().isoformat()
    output_path = output_dir / f"{today}-ai-daily-radar.md"
    lines = [f"# AI Daily Radar - {today}", ""]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"## {index}. {candidate.title}",
                "",
                f"中文标题：{candidate.title_zh or '翻译暂不可用'}",
                "",
                f"来源：{candidate.source}",
                f"链接：{candidate.url}",
                f"推荐分：{candidate.score:.1f}/10",
                f"热度：{candidate.heat_label}",
                f"推荐理由：{'；'.join(candidate.score_reasons) if candidate.score_reasons else '综合热度、时效和 AI 相关性排序'}",
                "",
                "### 内容摘要",
                candidate.summary_zh or fallback_summary(candidate, config),
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def send_email_report(output_path: Path, config: dict[str, Any], force: bool = False) -> bool:
    email_config = config.get("email_delivery", {})
    enabled = force or email_config.get("enabled", False) or env_truthy("AI_DAILY_RADAR_SEND_EMAIL")
    if not enabled:
        return False
    load_private_email_env()

    sender = os.environ.get("AI_DAILY_RADAR_QQ_USER", "").strip()
    auth_code = os.environ.get("AI_DAILY_RADAR_QQ_AUTH_CODE", "").strip()
    recipient = os.environ.get("AI_DAILY_RADAR_EMAIL_TO", sender).strip()
    if not sender or not auth_code or not recipient:
        print(
            "email skipped: set AI_DAILY_RADAR_QQ_USER, AI_DAILY_RADAR_QQ_AUTH_CODE, and AI_DAILY_RADAR_EMAIL_TO",
            file=sys.stderr,
        )
        return False

    subject_prefix = email_config.get("subject_prefix", "AI Daily Radar")
    date_text = dt.datetime.now().date().isoformat()
    body = output_path.read_text(encoding="utf-8")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"{subject_prefix} - {date_text}"
    message.set_content(body, subtype="plain", charset="utf-8")

    smtp_host = email_config.get("smtp_host", "smtp.qq.com")
    smtp_port = int(email_config.get("smtp_port", 465))
    if email_config.get("use_ssl", True):
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as smtp:
            smtp.login(sender, auth_code)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(sender, auth_code)
            smtp.send_message(message)
    return True


def env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_private_email_env() -> None:
    env_path = Path.home() / ".codex" / "ai-daily-radar-email.env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def collect(config: dict[str, Any]) -> tuple[list[Candidate], list[dict[str, Any]]]:
    collectors = [
        hn_candidates,
        reddit_candidates,
        rss_candidates,
        github_trending_candidates,
        hugging_face_papers_candidates,
    ]
    all_candidates: list[Candidate] = []
    health: list[dict[str, Any]] = []

    def run_collector(collector: Any) -> tuple[str, list[Candidate], dict[str, Any]]:
        started = time.time()
        name = collector.__name__
        try:
            results = collector(config)
            return (
                name,
                results,
                {
                    "source": name,
                    "status": "ok",
                    "candidates": len(results),
                    "elapsed_seconds": round(time.time() - started, 2),
                },
            )
        except Exception as error:
            return (
                name,
                [],
                {
                    "source": name,
                    "status": "error",
                    "error": str(error),
                    "candidates": 0,
                    "elapsed_seconds": round(time.time() - started, 2),
                },
            )

    with ThreadPoolExecutor(max_workers=len(collectors)) as pool:
        futures = [pool.submit(run_collector, collector) for collector in collectors]
        for future in as_completed(futures):
            name, results, health_item = future.result()
            if health_item["status"] == "error":
                print(f"collector skipped: {name}: {health_item.get('error')}", file=sys.stderr)
            all_candidates.extend(results)
            health.append(health_item)
    filtered = [item for item in all_candidates if is_ai_related(item, config["keywords"])]
    lookback = dt.timedelta(hours=float(config.get("lookback_hours", 48)))
    cutoff = now_utc() - lookback
    recent = [item for item in filtered if item.published is None or item.published >= cutoff]
    deduped = sorted(dedupe(recent), key=lambda item: item.score, reverse=True)
    assign_score_reasons(deduped)
    health.append(
        {
            "source": "pipeline",
            "status": "ok",
            "raw_candidates": len(all_candidates),
            "ai_related": len(filtered),
            "recent": len(recent),
            "deduped": len(deduped),
        }
    )
    return deduped, health


def write_source_health(health: list[dict[str, Any]], config: dict[str, Any]) -> Path:
    output_dir = ROOT / config.get("output_dir", "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now().date().isoformat()
    path = output_dir / f"{today}-source-health.json"
    write_json_file(path, {"date": today, "sources": health})
    return path


def select_output_candidates(candidates: list[Candidate], config: dict[str, Any], max_candidates: int, max_items: int) -> list[Candidate]:
    pool = candidates[:max_candidates]
    caps = config.get("diversity_caps", {})
    if not caps.get("enabled", True):
        return pool[:max_items]

    selected: list[Candidate] = []
    counts: dict[str, int] = {}
    skipped: list[Candidate] = []
    for candidate in pool:
        group = source_group(candidate)
        cap = int(caps.get(group, caps.get("other", max_items)))
        if counts.get(group, 0) < cap:
            selected.append(candidate)
            counts[group] = counts.get(group, 0) + 1
        else:
            skipped.append(candidate)
        if len(selected) >= max_items:
            break

    if len(selected) < max_items:
        selected_urls = {candidate.url for candidate in selected}
        for candidate in skipped:
            if candidate.url in selected_urls:
                continue
            selected.append(candidate)
            if len(selected) >= max_items:
                break
    return selected[:max_items]


def source_group(candidate: Candidate) -> str:
    source = candidate.source.lower()
    if candidate.source_type == "github_repo":
        return "github_repo"
    if "arxiv" in source or "hugging face daily papers" in source:
        return "research"
    if "hacker news" in source:
        return "hacker_news"
    if source.startswith("r/"):
        return "reddit"
    if any(name in source for name in ["openai", "anthropic", "deepmind", "hugging face blog"]):
        return "official"
    if any(name in source for name in ["rundown", "tldr", "ben"]):
        return "news"
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI Daily Radar Markdown.")
    parser.add_argument("--config", default=str(ROOT / "templates" / "config.example.json"))
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--send-email", action="store_true", help="Send the generated report by SMTP when email env vars are set.")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    max_candidates = int(config.get("max_candidates", 100))
    max_items = args.max_items or int(config.get("max_items", 50))
    candidates, health = collect(config)
    candidates = select_output_candidates(candidates, config, max_candidates, max_items)
    if not candidates:
        print("No AI-related candidates found.", file=sys.stderr)
        return 1
    translate_titles(candidates, config)
    summarize_items(candidates, config)
    output_path = write_report(candidates, config)
    health_path = write_source_health(health, config)
    email_sent = send_email_report(output_path, config, force=args.send_email)
    print(f"Report: {output_path}")
    print(f"Source health: {health_path}")
    if email_sent:
        print("Email: sent")
    for index, candidate in enumerate(candidates, start=1):
        print(f"{index}. {candidate.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
