# GNews Worker

Python worker that fetches news articles from GNews, enriches them with full text using `newspaper3k`, and publishes the results to a RabbitMQ exchange.

## Setup

1. Install Python 3.9+.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Environment variables (optional overrides):
- `GNEWS_API_URL` (default `https://gnewsapi.net/api`)
- `GNEWS_API_KEY` (default `60165e0fa0db3f16334fe9ddadc8334a`)
- `RABBITMQ_URL` (default `amqp://breaking-bad:breakingBad1@35.225.79.109:5672/my-host`)
- `RABBITMQ_EXCHANGE` (default `articles`)
- `FETCH_LIMIT` (default `10`)
- `FETCH_INTERVAL_MINUTES` (default `20`)

## Running

```bash
python worker.py
```
The worker runs once immediately, then every 20 minutes, fetching 10 articles for each query (`political`, `health`, `technology`, `sports`, `education`). Each article is enriched with `full_content` and the batch for each query is published as JSON to the `articles` exchange.

## Notes

- GNews requests use `lang=he`.
- RabbitMQ messages are sent as JSON to a durable `fanout` exchange named `articles`.
- `newspaper3k` downloads each article URL to extract full text; failures are logged and `full_content` is set to `null` for that item.
