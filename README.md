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

## Using Notes as an AI Knowledge Base (RAG)

Each saved `.md` file is a dense, structured summary of a single video — which makes the `notes/` folder a personal knowledge base you can query with AI.

**With Obsidian:**

1. Point an Obsidian vault at the `notes/` folder (or copy files into an existing vault)
2. Enable **vault QA / RAG mode** in a plugin
3. Ask questions in natural language — the plugin retrieves the most relevant note files and feeds them as context to the AI

Because every note has YAML frontmatter with tags, a source URL, and a date, Obsidian can filter and link notes automatically. Over time you build a searchable library where each video becomes a retrievable chunk of knowledge.

**Example workflow:**

- Watch 20 lectures on distributed systems → generate a note for each → ask "How do these videos explain consensus algorithms?" and get a synthesized answer grounded in your own notes.

The structured format EZnote produces (headings, bold terms, callout blocks, key takeaways) is intentionally designed to be both human-readable and high-signal for retrieval — short, dense chunks that give an LLM precise context without noise.

## Notes

- The API key is never exposed to the browser — all AI calls go through `server.py`.
- The model used is `openrouter/free` by default; you can change `OPENROUTER_MODEL` in `server.py` to any model available on OpenRouter.

