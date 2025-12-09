"""News worker that fetches, enriches, and publishes articles."""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import pika
import requests
import schedule
from newspaper import Article


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


GNEWS_API_URL = os.getenv("GNEWS_API_URL", "https://gnews.io/api/v4")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "60165e0fa0db3f16334fe9ddadc8334a")
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://breaking-bad:breakingBad1@35.225.79.109:5672/my-host",
)
RABBITMQ_EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", "articles")
FETCH_QUERIES = ["political", "health", "technology", "sports", "education"]
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", "10"))
FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "20"))


def fetch_articles(query: str, limit: int) -> List[Dict[str, Any]]:
    """Fetch articles for a given query from GNews."""
    url = f"https://gnews.io/api/v4/search?q={query}&apikey={GNEWS_API_KEY}&Lang=he&max={limit}"
    logging.info("Fetching %s articles for query='%s'", limit, query)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    articles = payload.get("articles") or payload.get("data") or []
    if not isinstance(articles, list):
        raise ValueError("Unexpected articles payload shape")
    return articles


def enrich_article(url: str) -> str:
    """Download and parse the article content via newspaper3k."""
    article = Article(url=url, language="he")
    article.download()
    article.parse()
    return article.text


def enrich_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach full_content to each article when possible."""
    enriched: List[Dict[str, Any]] = []
    for item in articles:
        url = item.get("url")
        if not url:
            logging.warning("Skipping article without URL: %s", item)
            continue
        try:
            full_content = enrich_article(url)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to enrich %s: %s", url, exc)
            full_content = None
        new_item = dict(item)
        new_item["full_content"] = full_content
        enriched.append(new_item)
    return enriched


def publish_articles(query: str, articles: List[Dict[str, Any]]) -> None:
    """Publish enriched articles to RabbitMQ."""
    message = {
        "query": query,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "articles": articles,
    }
    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.exchange_declare(exchange=RABBITMQ_EXCHANGE, exchange_type="fanout", durable=True)
    channel.basic_publish(
        exchange=RABBITMQ_EXCHANGE,
        routing_key="",
        body=json.dumps(message, ensure_ascii=False).encode("utf-8"),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )
    connection.close()
    logging.info("Published %s articles for query='%s'", len(articles), query)


def process_query(query: str) -> None:
    articles = fetch_articles(query, FETCH_LIMIT)
    enriched = enrich_articles(articles)
    publish_articles(query, enriched)


def run_cycle() -> None:
    logging.info("Starting fetch cycle for %s queries", len(FETCH_QUERIES))
    for query in FETCH_QUERIES:
        try:
            process_query(query)
        except Exception as exc:  # noqa: BLE001
            logging.error("Query '%s' failed: %s", query, exc)
    logging.info("Cycle finished")


def main() -> None:
    run_cycle()
    schedule.every(FETCH_INTERVAL_MINUTES).minutes.do(run_cycle)
    logging.info("Worker started; interval=%s minutes", FETCH_INTERVAL_MINUTES)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()