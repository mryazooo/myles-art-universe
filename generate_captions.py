#!/usr/bin/env python3
"""
generate_captions.py

Scans the NAS art folders for images that do NOT yet have .txt captions,
uses OpenAI vision to generate a title + caption, and writes them back
to the NAS as sidecar .txt files.

It NEVER overwrites existing non-empty .txt caption files.

Run this BEFORE build_art_site.py, e.g.:

    python generate_captions.py
    python build_art_site.py
"""

import base64
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
# CONFIGURATION
# --------------------

# Your NAS folders (same as in build_art_site.py)
NAS_FINISHED_DIR = Path(r"\\192.168.2.132\art-site\finished")
NAS_SKETCHBOOK_DIR = Path(r"\\192.168.2.132\art-site\sketchbook")

# Model to use for vision + captioning.
# You can change this later if you prefer a different one.
OPENAI_MODEL = "gpt-4o-mini"

# Safety: limit how many images to caption per run so you don’t
# accidentally blast through a huge backlog in one go.
MAX_IMAGES_PER_RUN = 20

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


def encode_image_to_base64(path: Path) -> str:
    with path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def list_images_without_captions(folder: Path) -> List[Path]:
    """
    Returns a list of image files in 'folder' that do NOT have a non-empty .txt
    caption file with the same stem.
    """
    if not folder.exists():
        print(f"[WARN] Folder does not exist: {folder}")
        return []

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    missing: List[Path] = []

    for entry in folder.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in IMAGE_EXTS:
            continue

        caption_file = folder / (entry.stem + ".txt")
        if caption_file.exists():
            try:
                text = caption_file.read_text(encoding="utf-8").strip()
            except Exception:
                text = ""
            if text:
                # Already has a caption, skip
                continue

        # No caption file or empty caption
        missing.append(entry)

    # Sort newest-first to caption recent uploads first
    missing.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return missing


def build_prompt(kind: str) -> str:
    """
    kind: "finished" or "sketchbook"
    Returns a text prompt describing how the model should caption the image.
    """
    if kind == "finished":
        role = (
            "You are describing a young artist's FINISHED comic and pop-culture fan art "
            "for an online portfolio."
        )
    else:
        role = (
            "You are describing a young artist's SKETCHBOOK STUDY or work-in-progress "
            "for an online portfolio."
        )

    instructions = (
        f"{role}\n"
        "The artwork often depicts well-known comic, superhero, and pop-culture characters.\n"
        "If the character is clearly recognisable (e.g. Batman, Deadpool, Spider-Man, "
        "Teenage Mutant Ninja Turtles like Leonardo/Donatello/Raphael/Michelangelo, etc.), "
        "YOU SHOULD NAME THE CHARACTER EXPLICITLY in both the title and caption.\n"
        "If you are not confident who it is, describe them generically (e.g. 'armoured hero', "
        "'masked vigilante', 'turtle warrior') without guessing.\n"
        "\n"
        "Respond in STRICT JSON with exactly two keys: 'title' and 'caption'.\n"
        "\n"
        "TITLE RULES:\n"
        "- 3–9 words.\n"
        "- Include the character's name if known (e.g. 'Batman Profile Illustration', "
        "'Leonardo Close-Up', 'Deadpool Pose Study').\n"
        "- No quotes, no trailing full stop.\n"
        "\n"
        "CAPTION RULES:\n"
        "- 1 sentence, ideally 18–30 words.\n"
        "- Start with the character's name if known (e.g. 'Batman is shown...', "
        "'Leonardo appears...', 'This sketch of Deadpool...').\n"
        "- Mention drawing medium (pencil, ink, markers) and key stylistic notes "
        "(dynamic pose, bold shadows, expressive linework, moody lighting, etc.).\n"
        "- Focus on what is visible in the artwork: subject, pose, mood, style.\n"
        "- Do NOT invent backstory or storylines.\n"
        "- Do NOT mention AI, the prompt, or that this is by a child.\n"
    )
    return instructions



def call_openai_caption(
    client: "OpenAI",
    image_path: Path,
    kind: str
) -> Tuple[str, str]:
    """
    Sends the image to OpenAI and returns (title, caption).
    """
    prompt = build_prompt(kind)
    image_b64 = encode_image_to_base64(image_path)

    # Compose a chat completion with image + text instructions
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_path.suffix.lstrip('.').lower()};base64,{image_b64}"
                        },
                    },
                ],
            }
        ],
        temperature=0.4,
    )

    # We asked for JSON; parse it
    content = response.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: try to extract JSON chunk if wrapped in text
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            data = json.loads(content[start:end])
        except Exception:
            raise RuntimeError(f"Could not parse JSON from model response:\n{content}")

    title = str(data.get("title", "")).strip()
    caption = str(data.get("caption", "")).strip()

    if not title:
        title = image_path.stem.replace("_", " ").replace("-", " ").title()
    if not caption:
        caption = f"{title} — illustration by Myles."

    return title, caption


def write_caption_file(image_path: Path, title: str, caption: str) -> None:
    """
    Writes a single .txt file next to the image with 'title — caption' format.
    """
    caption_file = image_path.with_suffix(".txt")
    combined = f"{title} — {caption}"
    caption_file.write_text(combined, encoding="utf-8")
    print(f"[OK] Wrote caption: {caption_file.name}")


def process_folder(client: "OpenAI", folder: Path, kind: str, remaining_budget: int) -> int:
    """
    Captions up to 'remaining_budget' images in the given folder.
    Returns the remaining budget after processing.
    """
    if remaining_budget <= 0:
        return 0

    missing = list_images_without_captions(folder)
    if not missing:
        print(f"[INFO] No unc captioned images in: {folder}")
        return remaining_budget

    print(f"[INFO] Found {len(missing)} unc captioned images in: {folder}")

    to_process = missing[:remaining_budget]

    for img_path in to_process:
        print(f"[CAPTION] {img_path.name} ({kind}) ...")
        try:
            title, caption = call_openai_caption(client, img_path, kind)
            write_caption_file(img_path, title, caption)
        except Exception as e:
            print(f"[ERROR] Failed to caption {img_path.name}: {e}")

    return remaining_budget - len(to_process)


# --------------------
# MAIN
# --------------------

def main():
    api_key = get_api_key()
    client = OpenAI(api_key=api_key)

    budget = MAX_IMAGES_PER_RUN
    print(f"[START] Caption generation with budget: {budget} images")

    # 1) Finished pieces
    if budget > 0:
        budget = process_folder(client, NAS_FINISHED_DIR, kind="finished", remaining_budget=budget)

    # 2) Sketchbook
    if budget > 0:
        budget = process_folder(client, NAS_SKETCHBOOK_DIR, kind="sketchbook", remaining_budget=budget)

    print(f"[DONE] Remaining caption budget after this run: {budget}")


if __name__ == "__main__":
    main()
