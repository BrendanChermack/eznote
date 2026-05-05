"""
EZnote - Backend Server
-------------------------------------------
Handles transcript fetching and all AI summarization via Gemini.
The API key never leaves the server.

Install dependencies:
    pip install yt-dlp flask flask-cors python-dotenv requests

Setup:
    Copy .env.example to .env and add your OPENROUTER_API_KEY.

Run:
    python server.py
"""

import subprocess
import sys
import os
import re
import tempfile
import json
import hashlib
from datetime import date
import requests
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

app = Flask(__name__)
CORS(app)

OPENROUTER_MODEL = "openrouter/free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CHUNK_SIZE = 12000
PROGRESS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".progress")
os.makedirs(PROGRESS_DIR, exist_ok=True)
NOTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes")
os.makedirs(NOTES_DIR, exist_ok=True)

# Key rotation state
_key_index = 0

def get_all_keys():
    keys = []
    i = 1
    while True:
        key = os.environ.get(f"OPENROUTER_API_KEY_{i}", "")
        if not key:
            break
        keys.append(key)
        i += 1
    # Also support single key for backwards compat
    single = os.environ.get("OPENROUTER_API_KEY", "")
    if single and single not in keys:
        keys.insert(0, single)
    return keys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_api_key():
    global _key_index
    keys = get_all_keys()
    if not keys:
        raise ValueError("No API keys found. Set OPENROUTER_API_KEY or OPENROUTER_API_KEY_1, _2, etc. in .env")
    return keys[_key_index % len(keys)]

def rotate_key():
    global _key_index
    keys = get_all_keys()
    _key_index = (_key_index + 1) % max(len(keys), 1)
    print(f"Rotated to key {_key_index + 1} of {len(keys)}")
    return _key_index


def call_openrouter(system, user_content):
    keys = get_all_keys()
    attempts = len(keys) if keys else 1

    for attempt in range(attempts):
        key = get_api_key()
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content}
            ],
            "max_tokens": 4000,
            "temperature": 0.3
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5001",
            "X-Title": "EZnote"
        }
        resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)

        if resp.status_code == 429:
            error_body = resp.text
            if attempt < attempts - 1:
                print(f"Key {_key_index + 1} hit rate limit, rotating...")
                rotate_key()
                continue
            raise requests.HTTPError(f"All keys exhausted: {error_body}", response=resp)

        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def parse_vtt(vtt_text):
    lines = vtt_text.splitlines()
    texts = []
    seen = set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE") or "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            seen.add(clean)
            texts.append(clean)
    return " ".join(texts)


def chunk_text(text, size):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            chunks.append(text[start:])
            break
        boundary = text.rfind(". ", start, end)
        if boundary <= start:
            boundary = end
        chunks.append(text[start:boundary + 1])
        start = boundary + 1
    return [c.strip() for c in chunks if len(c.strip()) > 50]


def clean_chunk(raw):
    system = """You are a transcript editor. Clean up raw auto-generated YouTube captions.

Rules:
- Fix punctuation: add periods, commas, and paragraph breaks where natural
- Fix capitalization
- Correct mishearings of financial and trading terms: orderflow, order flow, liquidity, delta, \
volume profile, futures, macro, sentiment, central bank, bond, forex, hedging, auction, intraday, \
swing trading, prop firm, market microstructure, price action, bid/ask, depth of market, imbalance, absorption
- Remove filler words (um, uh, you know) only when they carry no meaning
- Preserve all content — do not summarize, shorten, or cut anything
- Output only the cleaned transcript text"""
    return call_openrouter(system, raw)


def notes_from_chunk(chunk, chunk_index, total_chunks, video_url, video_id, opts):
    is_first = chunk_index == 0
    is_last = chunk_index == total_chunks - 1
    ts_base = f"https://www.youtube.com/watch?v={video_id}&t="
    estimated_start_sec = round((chunk_index / max(total_chunks, 1)) * 18000)
    today = date.today().isoformat()

    frontmatter_rule = (
        f"- Start with YAML frontmatter: title (inferred), date ({today}), "
        f"source ({video_url}), tags (3-6 trading/finance tags as a YAML list)"
        if is_first and opts.get("frontmatter") else "- Do NOT include frontmatter"
    )
    chapters_rule = "- Use ## for major topic sections and ### for subtopics" if opts.get("chapters") else ""
    timestamps_rule = (
        f"- At major section changes add a timestamped link: [▶ view section]({ts_base}SECONDS) "
        f"— estimate seconds, starting around {estimated_start_sec}s for this chunk"
        if opts.get("timestamps") else ""
    )
    callouts_rule = (
        "- Use Obsidian callout blocks:\n"
        "  > [!info] Concept\n  > Explanation\n"
        "  Use [!tip] for actionable insights, [!warning] for mistakes/pitfalls, [!note] for background"
        if opts.get("callouts") else ""
    )
    position_note = (
        "This is the FIRST chunk." if is_first
        else "This is a MIDDLE chunk — do not repeat any intro or frontmatter."
    )
    ending_note = (
        "This is the LAST chunk — end with a ## Key takeaways section with the 6-10 most important points."
        if is_last else "Do NOT add a summary or conclusion — more chunks follow."
    )

    system = f"""You are an expert note-taker specializing in finance and trading content.

You are processing chunk {chunk_index + 1} of {total_chunks} from a YouTube video transcript.
{position_note}
{ending_note}

Output ONLY Markdown. No preamble, no explanation, no code fences.

Rules:
{frontmatter_rule}
{chapters_rule}
{timestamps_rule}
{callouts_rule}
- Write detailed bullet points that expand concepts — include definitions, frameworks, examples, and analogies
- Bold key terms with **term** on first mention
- Preserve the logical flow and progression of ideas"""

    return call_openrouter(system, f"Transcript segment:\n\n{chunk}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def job_id(video_id, opts):
    key = video_id + json.dumps(opts, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()[:12]

def save_progress(jid, chunk_index, notes_so_far, total):
    path = os.path.join(PROGRESS_DIR, f"{jid}.json")
    with open(path, "w") as f:
        json.dump({"chunk_index": chunk_index, "notes": notes_so_far, "total": total}, f)

def load_progress(jid):
    path = os.path.join(PROGRESS_DIR, f"{jid}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def clear_progress(jid):
    path = os.path.join(PROGRESS_DIR, f"{jid}.json")
    if os.path.exists(path):
        os.remove(path)

@app.route("/")
def index():
    here = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(here, "notes.html")



@app.route("/transcript", methods=["GET"])
def get_transcript():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "Missing url parameter"}), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "%(id)s.%(ext)s")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--skip-download",
            "--write-auto-subs",
            "--write-subs",
            "--sub-lang", "en",
            "--sub-format", "vtt",
            "--output", output_template,
            "--no-playlist",
            url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        vtt_file = next(
            (os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".vtt")),
            None
        )
        if not vtt_file:
            detail = result.stderr[-400:] if result.stderr else "No captions found."
            return jsonify({"error": f"No captions found. yt-dlp output: {detail}"}), 404

        with open(vtt_file, "r", encoding="utf-8") as f:
            raw_vtt = f.read()

        transcript = parse_vtt(raw_vtt)
        if not transcript or len(transcript) < 100:
            return jsonify({"error": "Transcript was empty after parsing."}), 404

        title_result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--skip-download", "--print", "title", "--no-playlist", url],
            capture_output=True, text=True, timeout=30
        )
        title = title_result.stdout.strip() if title_result.returncode == 0 else ""

        return jsonify({"transcript": transcript, "title": title, "length": len(transcript)})


@app.route("/save", methods=["POST"])
def save_note():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    filename = data.get("filename", "note.md")
    notes = data.get("notes", "")
    jid = data.get("jid", "")

    # Sanitize filename
    filename = re.sub(r'[^a-zA-Z0-9 \-_.]', '', filename).strip()
    if not filename.endswith(".md"):
        filename += ".md"

    path = os.path.join(NOTES_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(notes)

    # Clear progress file now that the note is saved
    if jid:
        clear_progress(jid)

    return jsonify({"saved": True, "path": path})


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    transcript = data.get("transcript", "")
    video_id = data.get("video_id", "")
    video_url = data.get("video_url", "")
    opts = data.get("opts", {})

    if not transcript or not video_id:
        return jsonify({"error": "Missing transcript or video_id"}), 400

    def stream():
        try:
            raw_chunks = chunk_text(transcript, CHUNK_SIZE)
            total = len(raw_chunks)
            jid = job_id(video_id, opts)

            # Resume from saved progress if available
            saved = load_progress(jid)
            if saved and saved.get("total") == total:
                note_parts = saved["notes"]
                start_index = saved["chunk_index"]
                yield json.dumps({"type": "start", "total": total, "resuming": start_index, "jid": jid}) + "\n"
                print(f"Resuming job {jid} from chunk {start_index + 1}/{total}")
            else:
                note_parts = []
                start_index = 0
                yield json.dumps({"type": "start", "total": total, "resuming": 0, "jid": jid}) + "\n"

            for i in range(start_index, total):
                raw = raw_chunks[i]
                yield json.dumps({"type": "progress", "stage": "cleaning", "chunk": i + 1, "total": total}) + "\n"
                try:
                    cleaned = clean_chunk(raw)
                except Exception:
                    cleaned = raw

                yield json.dumps({"type": "progress", "stage": "notes", "chunk": i + 1, "total": total}) + "\n"
                notes = notes_from_chunk(cleaned, i, total, video_url, video_id, opts)
                if notes:
                    note_parts.append(notes)
                else:
                    note_parts.append(f"<!-- chunk {i+1} returned no content -->" )

                # Save progress after every chunk
                save_progress(jid, i + 1, note_parts, total)

            final = "\n\n---\n\n".join(p for p in note_parts if p)
            yield json.dumps({"type": "done", "notes": final, "chunks": total}) + "\n"

        except ValueError as e:
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"
        except requests.HTTPError as e:
            yield json.dumps({"type": "error", "error": f"API error: {e.response.text}"}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"

    return Response(stream_with_context(stream()), mimetype="application/x-ndjson")


if __name__ == "__main__":
    print("EZnote server running on http://localhost:5001")
    print("Open http://localhost:5001 in your browser")
    keys = get_all_keys()
    print(f"API keys loaded: {len(keys)} key(s) available for rotation")
    if not keys:
        print("WARNING: No API keys found. Set OPENROUTER_API_KEY in your .env file.")
    print("Keep this terminal open while using notes.html")
    app.run(port=5001, debug=False)