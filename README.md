# METECHS Affiliate Reel Bot

A Discord bot that downloads YouTube Shorts, publishes them as Instagram Reels, generates AI affiliate captions via Groq, and syncs products to the Metechs website — all triggered by a single Discord command.

---

## Command

```
!post <youtube_shorts_url> [amazon_affiliate_url]
```

**Examples:**
```
!post https://www.youtube.com/shorts/abc123
!post https://www.youtube.com/shorts/abc123 https://amzn.to/xyz
```

**Full workflow (with Amazon URL):**
1. Download YouTube Short via yt-dlp
2. Scrape Amazon product title
3. Generate AI caption (Groq — hook + benefits + CTA + affiliate link + 10 hashtags)
4. Create Instagram Reel container (resumable upload)
5. Upload video binary to Instagram
6. Poll processing status
7. Publish Reel
8. Fetch Instagram permalink
9. Post product to Metechs website API
10. Save record to local SQLite history

---

## Local Development

### Prerequisites
- Python 3.11+
- ffmpeg (`sudo apt install ffmpeg` or `brew install ffmpeg`)

### Setup

```bash
git clone <your-repo-url>
cd METECHS_BOT

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Fill in .env with your credentials
```

### Run
```bash
python main.py
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token from [Discord Developer Portal](https://discord.com/developers/applications) |
| `INSTAGRAM_ACCESS_TOKEN` | ✅ | Long-lived Page access token with `instagram_content_publish` scope |
| `INSTAGRAM_BUSINESS_ID` | ✅ | Instagram Professional account user ID |
| `GROQ_API_KEY` | ✅ | API key from [Groq Console](https://console.groq.com/keys) |
| `AMAZON_AFFILIATE_TAG` | ✅ | Amazon Associates store ID (default: `metechs-21`) |
| `WEBSITE_API_URL` | ✅ | Metechs product API endpoint |
| `WEBSITE_API_KEY` | ⬜ | Reserved for future authenticated endpoints |

---

## Deploy on Render (Free Tier Background Worker)

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/METECHS_BOT.git
git push -u origin main
```

### 2. Create a Render Background Worker

1. Go to [render.com](https://render.com) → **New +** → **Background Worker**
2. Connect your GitHub repository
3. Render detects the `Dockerfile` automatically — no changes needed
4. Set **Runtime** to **Docker**

### 3. Add Environment Variables

In the Render dashboard under **Environment**, add:

| Key | Value |
|---|---|
| `DISCORD_TOKEN` | your bot token |
| `INSTAGRAM_ACCESS_TOKEN` | your IG token |
| `INSTAGRAM_BUSINESS_ID` | your IG user ID |
| `GROQ_API_KEY` | your Groq key |
| `AMAZON_AFFILIATE_TAG` | `metechs-21` |
| `WEBSITE_API_URL` | `https://metechs-store.vercel.app/api/products/public` |

### 4. Deploy

Click **Create Background Worker**. Render will:
- Pull the repo
- Build the Docker image (installs ffmpeg + Python deps)
- Start `python main.py`

Every push to `main` triggers an automatic redeploy.

### Render Free Tier Notes

- ✅ Background workers do **not** spin down on inactivity (unlike web services)
- ✅ 750 free hours/month — enough for one 24/7 worker
- ⚠️ Filesystem is **ephemeral** — `temp/` and `logs/history.db` reset on each deploy
  - Video temp files are deleted after every post anyway (no impact)
  - SQLite history is session-only on free tier; upgrade to a Render Disk ($1/month) for persistence

---

## Project Structure

```
METECHS_BOT/
├── Dockerfile              ← Docker build (Python 3.11 + ffmpeg)
├── render.yaml             ← Render service definition
├── main.py                 ← Entry point
├── requirements.txt
├── .env.example
├── bot/
│   ├── client.py           ← MetechsBot (discord.py)
│   └── cogs/
│       └── post_command.py ← !post command pipeline
├── services/
│   ├── downloader.py       ← yt-dlp wrapper
│   ├── instagram.py        ← Graph API client
│   ├── caption.py          ← Amazon scraper + Groq AI
│   ├── website.py          ← Metechs website API client
│   ├── uploader.py         ← URL-based upload stub
│   └── history.py          ← SQLite post history
├── utils/
│   ├── validators.py       ← URL validation + affiliate tag injection
│   └── cleanup.py          ← Temp file management
└── temp/                   ← Runtime video staging (gitignored)
```
