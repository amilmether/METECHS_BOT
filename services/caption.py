import os
import logging
import re

import requests
from bs4 import BeautifulSoup
from groq import Groq

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Amazon scraper
# ──────────────────────────────────────────────────────────────────────────────

_HEADERS = {
    # Mimic a real browser so Amazon serves the full product page
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _scrape_product_title(amazon_url: str) -> str:
    """Fetch the Amazon product page and extract the product title.

    Parameters
    ----------
    amazon_url:
        Full Amazon product URL or amzn.to short link.

    Returns
    -------
    str
        Product title, or a generic fallback string if extraction fails.
    """
    try:
        resp = requests.get(amazon_url, headers=_HEADERS, timeout=10, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning(f"[Caption] Could not fetch Amazon page: {exc}")
        return "this amazing product"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Amazon product title is reliably in #productTitle
    title_tag = soup.find(id="productTitle")
    if title_tag:
        title = title_tag.get_text(strip=True)
        log.info(f"[Caption] Scraped product title: {title!r}")
        return title

    # Fallback: <title> tag (less reliable, may include "Amazon.com: " prefix)
    page_title = soup.find("title")
    if page_title:
        raw = page_title.get_text(strip=True)
        # Strip "Amazon.com: " or "Amazon.co.uk: " prefix
        cleaned = re.sub(r"^Amazon[^:]*:\s*", "", raw, flags=re.IGNORECASE)
        if cleaned:
            log.info(f"[Caption] Fell back to page title: {cleaned!r}")
            return cleaned

    log.warning("[Caption] Could not extract product title from Amazon page.")
    return "this amazing product"


# ──────────────────────────────────────────────────────────────────────────────
# Groq caption generator
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert Instagram affiliate marketer who writes viral short-form captions for Instagram Reels.

Your captions MUST follow this exact structure:

Hook line — one punchy curiosity-driven sentence.
The phrase “Product link in bio” must appear in this first line.

Product benefit — 1–2 short sentences explaining the key benefit or transformation the product provides.

Call to action — one clear sentence encouraging the viewer to check the link in bio.

Affiliate link placeholder — output exactly:
AFFILIATE_LINK_HERE

Hashtags — exactly 10 highly relevant, trending Instagram hashtags on a single line.

Rules:

Keep the full caption under 220 words

Use emojis naturally but sparingly

Do NOT include the product URL anywhere

Do NOT wrap the caption in quotes or markdown

Do NOT add explanations

Output only the final caption

Hashtags must appear only at the end

The caption should feel viral, simple, and optimized for Instagram affiliate marketing.
"""

_USER_TEMPLATE = (
    "Write an Instagram Reel caption for the following Amazon affiliate product.\n\n"
    "Product: {product_title}\n"
    "Affiliate link: {affiliate_link}\n\n"
    "Replace the placeholder AFFILIATE_LINK_HERE in your output with the actual affiliate link."
)


def generate_caption(amazon_url: str) -> str:
    """Scrape the Amazon product title and generate an AI caption via Groq.

    Parameters
    ----------
    amazon_url:
        Amazon product URL or amzn.to short link (used both for scraping and
        as the affiliate link embedded in the caption).

    Returns
    -------
    str
        Formatted Instagram Reel caption including hook, benefits, CTA,
        the affiliate link, and 10 hashtags.

    Raises
    ------
    RuntimeError
        If GROQ_API_KEY is not set or the Groq API call fails.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to your .env file."
        )

    # 1. Scrape the product title
    product_title = _scrape_product_title(amazon_url)

    # 2. Build the user prompt
    user_prompt = _USER_TEMPLATE.format(
        product_title=product_title,
        affiliate_link=amazon_url,
    )

    # 3. Call Groq
    client = Groq(api_key=api_key)
    log.info(f"[Caption] Calling Groq for product: {product_title!r}")

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.85,
            max_tokens=512,
        )
    except Exception as exc:
        raise RuntimeError(f"Groq API error: {exc}") from exc

    caption = response.choices[0].message.content.strip()
    log.info(f"[Caption] Generated caption ({len(caption)} chars).")
    return caption
