#!/usr/bin/env python3
"""Fetch one public web page and extract only query-relevant main-content blocks.

Worker input is one JSON object on stdin:
  {"task_id":"...","parameters":{"url":"https://...","query":"saturn moons total"}}

Set ``whole_page: true`` only when a complete main-content extraction is wanted.
The worker is dependency-free and emits RESULT:/ERROR: JSON lines for the local
orchestrator protocol.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

MAX_BYTES = 4 * 1024 * 1024
MAX_CHARS = 32_000
MAX_SECTIONS = 5
TIMEOUT_SECONDS = 15
USER_AGENT = "KuhulResearchBot/1.0 (+local query-focused page extraction)"
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from",
    "has", "have", "how", "in", "is", "it", "of", "on", "or", "the", "to", "was",
    "were", "what", "when", "where", "which", "who", "why", "with",
}
SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "form"}
BLOCK_TAGS = {"p", "li", "blockquote", "pre", "dt", "dd"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _terms(value: str) -> list[str]:
    words = re.findall(r"[\w'-]+", str(value).casefold(), flags=re.UNICODE)
    return list(dict.fromkeys(word for word in words if word not in STOP_WORDS and len(word) > 1))


def _public_https_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("url must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    if parsed.port not in (None, 443):
        raise ValueError("only the standard HTTPS port is allowed")
    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("local and private network hosts are not allowed")
    try:
        addresses = {item[4][0].split("%", 1)[0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError(f"could not resolve URL host: {exc}") from exc
    if not addresses:
        raise ValueError("URL host has no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("local, private, and reserved network addresses are not allowed")
    return parsed


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str) -> tuple[str, str, str]:
    parsed = _public_https_url(url)
    request = urllib.request.Request(
        urllib.parse.urlunsplit(parsed),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9"},
    )
    opener = urllib.request.build_opener(_SafeRedirect())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError(f"URL returned {content_type}; only HTML pages are supported")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError(f"page exceeds the {MAX_BYTES}-byte retrieval limit")
            charset = response.headers.get_content_charset() or "utf-8"
            return response.geturl(), body.decode(charset, errors="replace"), content_type
    except urllib.error.HTTPError as exc:
        raise ValueError(f"page request returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"page request failed: {exc.reason}") from exc


class _PageParser(HTMLParser):
    """Collect title and text blocks, retaining only the best content container."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.tag_stack: list[tuple[str, int, bool]] = []
        self.container_stack: list[int] = []
        self.best_rank = 0
        self.title = ""
        self.in_title = False
        self.title_parts: list[str] = []
        self.current_heading = "Page content"
        self.heading_tag: str | None = None
        self.heading_parts: list[str] = []
        self.block_tag: str | None = None
        self.block_parts: list[str] = []
        self.blocks: list[dict] = []
        self.fallback_blocks: list[dict] = []

    @staticmethod
    def _rank(tag: str, attrs: dict[str, str | None]) -> int:
        classes = (attrs.get("class") or "").casefold().split()
        element_id = (attrs.get("id") or "").casefold()
        if tag == "main" or tag == "article":
            return 3
        if element_id in {"content", "main-content", "article-content"} or any(
            word in cls for cls in classes for word in ("entry-content", "post-content", "article-content", "main-content")
        ):
            return 2
        return 1 if tag == "body" else 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = "hidden" in attrs or (attrs.get("aria-hidden") or "").casefold() == "true"
        if self.skip_depth:
            self.tag_stack.append((tag, 0, False))
            return
        if tag in SKIP_TAGS or hidden:
            self.skip_depth += 1
            self.tag_stack.append((tag, 0, True))
            return
        rank = self._rank(tag, attrs)
        self.tag_stack.append((tag, rank, False))
        if rank:
            self.container_stack.append(rank)
            self.best_rank = max(self.best_rank, rank)
        if tag == "title":
            self.in_title = True
        if tag in HEADING_TAGS:
            self.heading_tag = tag
            self.heading_parts = []
        elif tag in BLOCK_TAGS:
            self.block_tag = tag
            self.block_parts = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.tag_stack) - 1, -1, -1):
            open_tag, rank, skipped = self.tag_stack[index]
            if open_tag == tag:
                del self.tag_stack[index:]
                if rank and rank in self.container_stack:
                    self.container_stack.remove(rank)
                if skipped and self.skip_depth:
                    self.skip_depth = max(0, self.skip_depth - 1)
                break
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title = False
            self.title = " ".join(self.title_parts).strip()
        if tag in HEADING_TAGS and self.heading_tag == tag:
            text = self._clean(self.heading_parts)
            if text:
                self.current_heading = text
            self.heading_tag = None
            self.heading_parts = []
        elif tag in BLOCK_TAGS and self.block_tag == tag:
            text = self._clean(self.block_parts)
            if text:
                block = {"heading": self.current_heading, "text": text, "container_rank": max(self.container_stack, default=0)}
                if block["container_rank"]:
                    self.blocks.append(block)
                else:
                    self.fallback_blocks.append(block)
            self.block_tag = None
            self.block_parts = []

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self.heading_tag:
            self.heading_parts.append(data)
        if self.block_tag:
            self.block_parts.append(data)

    @staticmethod
    def _clean(parts):
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def selected_blocks(self):
        if self.best_rank:
            return [block for block in self.blocks if block["container_rank"] == self.best_rank]
        return self.fallback_blocks


def _relevant_sections(blocks: list[dict], query: str, max_sections: int = MAX_SECTIONS) -> list[dict]:
    query_terms = _terms(query)
    if not query_terms:
        raise ValueError("query must contain at least one searchable term")
    asks_quantity = bool(re.search(r"\b(?:how many|how much|total|count|number|quantity)\b", query, re.I))
    groups: dict[str, list[dict]] = {}
    for block in blocks:
        groups.setdefault(block["heading"], []).append(block)

    minimum = 1 if len(query_terms) < 3 else 2
    ranked = []
    for heading, section_blocks in groups.items():
        heading_matches = set(query_terms) & set(_terms(heading))
        relevant_blocks = []
        matches = set(heading_matches)
        for block in section_blocks:
            block_matches = set(query_terms) & set(_terms(block["text"]))
            has_quantity = bool(re.search(r"\b\d[\d,]*(?:\.\d+)?\b", block["text"]))
            if block_matches and (not asks_quantity or has_quantity):
                relevant_blocks.append(block)
                matches.update(block_matches)
        if len(matches) < minimum or not relevant_blocks:
            continue
        score = round((len(matches) + 0.5 * len(heading_matches)) / len(query_terms), 4)
        ranked.append((score, heading, relevant_blocks, sorted(matches)))
    ranked.sort(key=lambda row: (-row[0], row[1].casefold()))
    return [
        {"heading": heading, "score": score, "matched_terms": matches,
         "content": "\n".join(block["text"] for block in section_blocks)}
        for score, heading, section_blocks, matches in ranked[:max_sections]
    ]


def scrape_website(parameters: dict) -> dict:
    """Fetch a page and return relevant main-content sections or explicit full content."""
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be a JSON object")
    url = str(parameters.get("url") or "").strip()
    whole_page = parameters.get("whole_page", False) is True
    query = str(parameters.get("query") or parameters.get("search_query") or parameters.get("terms") or "").strip()
    if not url:
        raise ValueError("parameters.url is required")
    if not whole_page and not query:
        raise ValueError("parameters.query is required unless whole_page is true")

    final_url, html, content_type = _fetch(url)
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    blocks = parser.selected_blocks()
    if not blocks:
        raise ValueError("page contains no extractable main-content text blocks")

    if whole_page:
        sections_map: dict[str, list[str]] = {}
        for block in blocks:
            sections_map.setdefault(block["heading"], []).append(block["text"])
        sections = [{"heading": heading, "score": None, "matched_terms": [], "content": "\n".join(texts)}
                    for heading, texts in sections_map.items()]
    else:
        sections = _relevant_sections(blocks, query)
        if not sections:
            raise ValueError("no main-content section matched the query terms")

    full_content = "\n\n".join(f"{section['heading']}\n{section['content']}" for section in sections)
    truncated = len(full_content) > MAX_CHARS
    remaining = MAX_CHARS
    bounded_sections = []
    for section in sections:
        if remaining <= 0:
            break
        bounded = dict(section)
        bounded["content"] = section["content"][:remaining]
        remaining -= len(bounded["content"])
        bounded_sections.append(bounded)
    content = "\n\n".join(f"{section['heading']}\n{section['content']}" for section in bounded_sections)[:MAX_CHARS]
    return {
        "schema": "kuhul.scrape.result.v1",
        "url": final_url,
        "title": parser.title or final_url,
        "query": query or None,
        "query_terms": _terms(query),
        "whole_page": whole_page,
        "content_type": content_type,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sections": bounded_sections,
        "content": content,
        "section_count": len(bounded_sections),
        "matched_block_count": sum(len(section["content"].splitlines()) for section in bounded_sections),
        "truncated": truncated,
        "authority": "retrieved_page_evidence_only; not_verified_fact",
    }


def main() -> int:
    task = {}
    try:
        line = sys.stdin.readline()
        if not line:
            raise ValueError("expected one JSON task on stdin")
        task = json.loads(line)
        task_id = task.get("task_id", "unknown")
        result = scrape_website(task.get("parameters", {}))
        print(f"RESULT:{json.dumps({'task_id': task_id, 'result': result, 'status': 'completed'}, ensure_ascii=False)}", flush=True)
        return 0
    except Exception as exc:
        print(f"ERROR:{json.dumps({'task_id': task.get('task_id', 'unknown'), 'error': str(exc)}, ensure_ascii=False)}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
