# EZnote

Turn any YouTube video into structured Markdown notes — automatically.

Paste a YouTube URL, click **Generate Notes**, and EZnote fetches the transcript, cleans it up, and uses an AI model (via [OpenRouter](https://openrouter.ai)) to produce detailed, well-formatted notes in Obsidian-compatible Markdown. Notes are saved locally as `.md` files.

## Features

- Fetches auto-generated or manual captions from any YouTube video via `yt-dlp`
- Cleans raw caption text (fixes punctuation, capitalization, filler words)
- Generates structured Markdown notes with:
  - YAML frontmatter (title, date, source, tags)
  - Chapter headings (`##` / `###`)
  - Timestamped links back to the video
  - Obsidian callout blocks (`[!info]`, `[!tip]`, `[!warning]`, `[!note]`)
  - Key takeaways section
- Streams progress chunk-by-chunk so you see notes as they are generated
- Resumes interrupted jobs automatically
- Supports multiple OpenRouter API keys with automatic rotation on rate limits
- Saves notes to a local `notes/` folder as `.md` files

## Requirements

- Python 3.9+
- An [OpenRouter](https://openrouter.ai) account and API key (free tier works)

## Setup

**1. Clone the repo**

```bash
git clone https://github.com/your-username/EZnote.git
cd EZnote
```

**2. Install dependencies**

```bash
pip install yt-dlp flask flask-cors python-dotenv requests
```

**3. Configure your API key**

Copy the example env file and add your key:

```bash
cp .env.example .env
```

Then edit `.env`:

```
OPENROUTER_API_KEY=your_openrouter_api_key
```

You can optionally add multiple keys for rotation if you hit rate limits:

```
OPENROUTER_API_KEY_1=your_first_key
OPENROUTER_API_KEY_2=your_second_key
```

## Running

```bash
python server.py
```

The server starts on `http://localhost:5001`. Open that URL in your browser to use the app.

> Keep the terminal open while using EZnote — the server must be running.

## Usage

1. Paste a YouTube video URL into the input field
2. Choose your note options (frontmatter, chapters, timestamps, callouts)
3. Click **Generate Notes**
4. Watch notes stream in as each chunk of the transcript is processed
5. Click **Save** to write the note to the `notes/` folder as a `.md` file

## Project Structure

```
EZnote/
├── server.py        # Flask backend — transcript fetching, AI summarization
├── notes.html       # Frontend UI (served by the Flask app)
├── notes/           # Generated notes are saved here (gitignored)
├── .progress/       # Resumable job state (gitignored)
├── .env             # Your API keys (gitignored)
└── .env.example     # Template for .env
```

## Notes

- The API key is never exposed to the browser — all AI calls go through `server.py`.
- Generated notes are Obsidian-compatible and can be dropped directly into a vault.
- The model used is `openrouter/free` by default; you can change `OPENROUTER_MODEL` in `server.py` to any model available on OpenRouter.
