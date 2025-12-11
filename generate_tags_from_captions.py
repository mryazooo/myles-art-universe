#!/usr/bin/env python3
"""
generate_tags_from_captions.py

Reads existing .txt caption sidecars created by generate_captions.py,
derives tags + character names using a text-only OpenAI call, and writes
JSON metadata sidecars (one .json per image) next to the artwork.

It NEVER:
- recaptions images
- overwrites existing .json files

Run this AFTER generate_captions.py and BEFORE build_art_site.py, e.g.:

    python generate_captions.py
    python generate_tags_from_captions.py
    python build_art_site.py
"""

import json
import os
from pathlib import Path
from typing import List, Tuple

try:
    from openai import OpenAI
except ImportError:
    raise SystemExit(
        "The 'openai' package is not installed. "
        "Run: pip install openai"
    )
# --------------------
# SLUG HELPER
# --------------------
import re

def make_slug(title: str) -> str:
    """
    Converts a title like 'Young Hellboy Illustration'
    into a clean slug: 'young-hellboy-illustration'.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)   # replace non-alphanumerics with hyphens
    slug = re.sub(r"-{2,}", "-", slug)        # collapse multiple hyphens
    slug = slug.strip("-")                    # trim leading/trailing hyphens
    return slug

# --------------------
# CONFIGURATION
# --------------------

# Match your caption script paths 1:1
NAS_FINISHED_DIR = Path(r"\\192.168.2.132\art-site\finished")
NAS_SKETCHBOOK_DIR = Path(r"\\192.168.2.132\art-site\sketchbook")

# Text-only model to use for tag + character generation
TAG_MODEL = "gpt-4o-mini"

# Safety: limit how many images to tag per run
MAX_IMAGES_PER_RUN = 40  # can be higher/cheaper than captioning

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# --------------------
# HELPER FUNCTIONS
# --------------------

def get_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise SystemExit(
            "OPENAI_API_KEY is not set. "
            "Make sure you ran setx OPENAI_API_KEY \"sk-...\" "
            "and opened a NEW PowerShell window."
        )
    return key


def list_captioned_images_without_json(folder: Path) -> List[Path]:
    """
    Returns a list of image files in 'folder' that:
      - have a non-empty .txt caption sidecar
      - do NOT yet have a .json metadata sidecar
    """
    if not folder.exists():
        print(f"[WARN] Folder does not exist: {folder}")
        return []

    result: List[Path] = []

    for entry in folder.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in IMAGE_EXTS:
            continue

        caption_file = entry.with_suffix(".txt")
        json_file = entry.with_suffix(".json")

        # Require a non-empty caption file
        if not caption_file.exists():
            continue
        try:
            caption_text = caption_file.read_text(encoding="utf-8").strip()
        except Exception:
            caption_text = ""
        if not caption_text:
            continue

        # Skip if JSON already exists
        if json_file.exists():
            continue

        result.append(entry)

    # Newest-first (same idea as captioning)
    result.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return result


def parse_caption_file(caption_path: Path) -> Tuple[str, str]:
    """
    Your caption format is: 'title — caption'
    (title, space, EM DASH, space, caption).

    This parses that. If it can't find the separator, it falls back to:
      title   = stem-based title
      caption = full text
    """
    raw = caption_path.read_text(encoding="utf-8").strip()
    separator = " — "  # space + em dash + space

    if separator in raw:
        title_part, caption_part = raw.split(separator, 1)
        title = title_part.strip()
        caption = caption_part.strip()
    else:
        # Fallback – shouldn't happen often, but keeps things robust.
        title = caption_path.stem.replace("_", " ").replace("-", " ").title()
        caption = raw

    if not title:
        title = caption_path.stem.replace("_", " ").replace("-", " ").title()
    if not caption:
        caption = f"{title} — illustration by Myles."

    return title, caption


def call_openai_tags_and_characters(
    client: "OpenAI",
    title: str,
    caption: str,
    kind: str,
    max_tags: int = 10,
) -> Tuple[list, list]:
    """
    Text-only call: generate tags + character names from existing title + caption.
    kind: 'finished' or 'sketchbook' (for flavour only)

    Returns:
      (tags, characters)

    'characters' should only include clearly named characters like:
      ["Batman", "Deadpool", "Spider-Man", "Leonardo", ...]
    or be an empty list [] if none are confidently identified.
    """
    role = (
        "You are tagging a young artist's FINISHED comic and pop-culture artwork "
        "for an online portfolio."
        if kind == "finished"
        else
        "You are tagging a young artist's SKETCHBOOK STUDIES and work-in-progress "
        "comic and pop-culture artwork for an online portfolio."
    )

    prompt = f"""
{role}

You are given the TITLE and CAPTION that already describe a piece of artwork.

Do NOT change the title or caption. Your job is ONLY to create useful tags
and extract clearly named characters.

TITLE:
\"\"\"{title}\"\"\"

CAPTION:
\"\"\"{caption}\"\"\"

RULES FOR TAGS:
- Generate 5 to {max_tags} tags.
- Tags should be simple, lowercase words or short phrases.
- No '#' prefix, no trailing punctuation.
- Focus on what is clearly implied by the title + caption:
  - characters (e.g. batman, deadpool, spider-man, ninja turtle)
  - type of art (comic art, fan art, sketch, marker drawing, inked line art)
  - pose (dynamic pose, close-up, profile, action pose)
  - mood (dramatic, moody, playful)
  - visual elements (bold shadows, expressive linework, cross-hatching, strong contrast)
- Prefer concise phrases like:
  - "comic art", "fan art", "marker drawing", "dynamic pose", "profile view",
    "close-up", "inked line art", "turtle warrior", "masked vigilante"
- Do NOT invent storylines or backstory.
- Do NOT mention AI, prompts, or the artist's age.

RULES FOR CHARACTERS:
- The "characters" field must be a list of PROPER NAMES ONLY, e.g.:
  ["Batman", "Deadpool", "Spider-Man", "Leonardo", "Michelangelo"]
- Include a character ONLY if you are confident the title+caption clearly name them.
- If an alias and real name both appear, choose the better-known name (e.g. "Spider-Man" instead of "Peter Parker").
- If NO clear named characters appear, return an empty list: [].

Respond in STRICT JSON with exactly two keys: "tags" and "characters".

Example format:
{{
  "tags": [
    "comic art",
    "dynamic pose",
    "inked line art",
    "batman"
  ],
  "characters": [
    "Batman"
  ]
}}
"""

    response = client.chat.completions.create(
        model=TAG_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: try to pull out JSON chunk
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            data = json.loads(content[start:end])
        except Exception:
            raise RuntimeError(f"Could not parse JSON from model response:\n{content}")

    raw_tags = data.get("tags", [])
    raw_chars = data.get("characters", [])

    if not isinstance(raw_tags, list):
        raise RuntimeError(f"Model returned invalid 'tags' field:\n{data}")
    if not isinstance(raw_chars, list):
        # Normalise to list if model replied incorrectly
        raw_chars = []

    # Clean + dedupe tags
    cleaned_tags = []
    seen_tags = set()
    for t in raw_tags:
        if not isinstance(t, str):
            continue
        tag = t.strip()
        if not tag:
            continue
        low = tag.lower()
        if low not in seen_tags:
            seen_tags.add(low)
            cleaned_tags.append(tag)

    # Clean + dedupe characters (preserve case)
    cleaned_chars = []
    seen_chars = set()
    for c in raw_chars:
        if not isinstance(c, str):
            continue
        name = c.strip()
        if not name:
            continue
        if name.lower() not in seen_chars:
            seen_chars.add(name.lower())
            cleaned_chars.append(name)

    return cleaned_tags[:max_tags], cleaned_chars


def write_json_sidecar(
    image_path: Path,
    title: str,
    caption: str,
    tags: list,
    characters: list,
    kind: str,
) -> None:
    """
    Writes a JSON sidecar file next to the image with:
      {
        "file", "title", "caption",
        "tags", "characters", "kind", "slug"
      }
    """
    json_path = image_path.with_suffix(".json")

    slug = make_slug(title)

    data = {
        "file": image_path.name,
        "title": title,
        "caption": caption,
        "tags": tags,
        "characters": characters,
        "kind": kind,  # "finished" or "sketchbook"
        "slug": slug,
    }

    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] Wrote metadata: {json_path.name}")


def process_folder(
    client: "OpenAI",
    folder: Path,
    kind: str,
    remaining_budget: int,
) -> int:
    """
    Creates JSON sidecars for up to 'remaining_budget' images
    in 'folder' that already have .txt captions but no .json.
    Returns updated remaining_budget.
    """
    if remaining_budget <= 0:
        return 0

    candidates = list_captioned_images_without_json(folder)
    if not candidates:
        print(f"[INFO] No captioned images needing JSON in: {folder}")
        return remaining_budget

    print(f"[INFO] Found {len(candidates)} images needing JSON in: {folder}")

    to_process = candidates[:remaining_budget]

    for img_path in to_process:
        caption_path = img_path.with_suffix(".txt")
        print(f"[TAGS] {img_path.name} ({kind}) ...")
        try:
            title, caption = parse_caption_file(caption_path)
            tags, characters = call_openai_tags_and_characters(
                client,
                title,
                caption,
                kind=kind,
                max_tags=10,
            )
            write_json_sidecar(
                image_path=img_path,
                title=title,
                caption=caption,
                tags=tags,
                characters=characters,
                kind=kind,
            )
        except Exception as e:
            print(f"[ERROR] Failed to generate tags for {img_path.name}: {e}")

    return remaining_budget - len(to_process)


# --------------------
# MAIN
# --------------------

def main():
    api_key = get_api_key()
    client = OpenAI(api_key=api_key)

    budget = MAX_IMAGES_PER_RUN
    print(f"[START] Tag + character generation with budget: {budget} images")

    # 1) Finished pieces
    if budget > 0:
        budget = process_folder(
            client,
            NAS_FINISHED_DIR,
            kind="finished",
            remaining_budget=budget,
        )

    # 2) Sketchbook
    if budget > 0:
        budget = process_folder(
            client,
            NAS_SKETCHBOOK_DIR,
            kind="sketchbook",
            remaining_budget=budget,
        )

    print(f"[DONE] Remaining tag budget after this run: {budget}")


if __name__ == "__main__":
    main()
