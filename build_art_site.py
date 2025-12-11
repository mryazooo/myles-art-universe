#!/usr/bin/env python3
"""
build_art_site.py

- Reads curated images from NAS share (finished)
- Copies them into the local repo images folder
- Updates the Home page (index.html) hero + featured cards
  based on NAS 'finished' images and sidecar .txt captions.
"""

import shutil
import re
from pathlib import Path
from typing import List, Tuple

# --------------------
# CONFIGURATION
# --------------------

# NAS source folders (adjust IP/hostname as needed)
NAS_FINISHED_DIR = r"\\192.168.2.132\art-site\finished"   # <-- update to match your NAS
NAS_SKETCHBOOK_DIR = r"\\192.168.2.132\art-site\sketchbook"  # not used yet, but left for future

# Local repo folders where images are stored
REPO_ROOT = Path(__file__).resolve().parent
LOCAL_FINISHED_DIR = REPO_ROOT / "images" / "finished"
LOCAL_SKETCHBOOK_DIR = REPO_ROOT / "images" / "sketchbook"  # for future

# HTML file to update (home page)
HTML_FILE = REPO_ROOT / "index.html"
HTML_BACKUP_FILE = REPO_ROOT / "index.backup.html"

# Markers in the HTML file
MARKERS = {
    "hero": ("<!-- START HERO -->", "<!-- END HERO -->"),
    "featured": ("<!-- START FEATURED -->", "<!-- END FEATURED -->"),
}

# How many featured images to show (after hero)
NUM_FEATURED = 3

# File extensions considered as images
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# --------------------
# HELPER FUNCTIONS
# --------------------

def list_images_with_captions(folder: Path) -> List[Tuple[Path, str]]:
    """
    Returns a list of (image_path, caption) sorted by modification time (newest first).
    If a .txt file with the same stem exists, its contents are used as caption.
    Otherwise, caption is empty.
    """
    if not folder.exists():
        return []

    images = []
    for entry in folder.iterdir():
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTS:
            caption_file = folder / (entry.stem + ".txt")
            caption = ""
            if caption_file.exists():
                try:
                    caption = caption_file.read_text(encoding="utf-8").strip()
                except Exception:
                    caption = ""
            images.append((entry, caption))

    # Newest first
    images.sort(key=lambda t: t[0].stat().st_mtime, reverse=True)
    return images


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_images(src_items: List[Tuple[Path, str]], dest_folder: Path) -> List[Tuple[str, str]]:
    """
    Copies images to dest_folder.
    Returns list of (file_name, caption) relative to dest_folder.
    """
    ensure_dir(dest_folder)
    # clear existing finished images so it stays in sync
    for f in dest_folder.glob("*"):
        if f.is_file():
            f.unlink()
    result = []
    for src_path, caption in src_items:
        dest_path = dest_folder / src_path.name
        shutil.copy2(src_path, dest_path)
        result.append((dest_path.name, caption))
    return result


def escape_html(text: str) -> str:
    """Very small HTML escape helper for captions/titles."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def build_hero_html(file_name: str, caption: str) -> str:
    """
    Builds the hero-image block.
    - Uses caption as alt text if available.
    - Falls back to a cleaned version of the filename.
    """
    img_src = f"images/finished/{file_name}"

    if caption:
        alt = escape_html(caption)
    else:
        alt = Path(file_name).stem.replace("_", " ").title()

    return (
        '<div class="hero-image">\n'
        f'  <img src="{img_src}" alt="{alt}" class="hero-art" />\n'
        '</div>'
    )


def build_featured_html(items: List[Tuple[str, str]]) -> str:
    """
    Builds the Featured Pieces card grid.
    Uses caption as the title if available,
    otherwise uses a cleaned filename.
    """
    if not items:
        return '<div class="card-grid"></div>'

    cards = []
    for file_name, caption in items:
        img_src = f"images/finished/{file_name}"

        if caption:
            title = caption.split("—")[0].strip().title()  # First part of caption
            body = caption
        else:
            # fallback to filename-derived title
            stem = Path(file_name).stem.replace("_", " ")
            title = stem.title()
            body = "New featured artwork from Myles."

        title = escape_html(title)
        body = escape_html(body)

        card = (
            '  <article class="card">\n'
            '    <div class="card-image">\n'
            f'      <img src="{img_src}" alt="{title}" />\n'
            '    </div>\n'
            '    <div class="card-body">\n'
            f'      <h3>{title}</h3>\n'
            f'      <p>{body}</p>\n'
            '    </div>\n'
            '  </article>'
        )
        cards.append(card)

    return "<div class=\"card-grid\">\n" + "\n\n".join(cards) + "\n</div>"


def replace_section(html: str, start_marker: str, end_marker: str, new_content: str) -> str:
    """
    Replaces the content between start_marker and end_marker (inclusive) with:
    start_marker + newline + new_content + newline + end_marker
    """
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL
    )
    replacement = f"{start_marker}\n{new_content}\n{end_marker}"
    new_html, count = pattern.subn(replacement, html, count=1)
    if count == 0:
        raise ValueError(f"Markers not found: {start_marker} .. {end_marker}")
    return new_html

# --------------------
# MAIN
# --------------------

def main():
    nas_finished = Path(NAS_FINISHED_DIR)
    if not nas_finished.exists():
        raise SystemExit(f"NAS finished folder does not exist: {nas_finished}")

    finished_items = list_images_with_captions(nas_finished)
    if not finished_items:
        print("Warning: no images found in finished folder.")

    # Copy images into local repo
    copied_finished = copy_images(finished_items, LOCAL_FINISHED_DIR)
    print(f"Copied {len(copied_finished)} finished images to {LOCAL_FINISHED_DIR}")

    if not HTML_FILE.exists():
        raise SystemExit(f"HTML file not found: {HTML_FILE}")

    # Decide hero + featured
    hero = copied_finished[0] if copied_finished else None
    featured = copied_finished[1:1 + NUM_FEATURED] if len(copied_finished) > 1 else []

    hero_html = build_hero_html(hero[0], hero[1]) if hero else '<div class="hero-image"></div>'
    featured_html = build_featured_html(featured)

    # Read HTML
    original_html = HTML_FILE.read_text(encoding="utf-8")
    HTML_BACKUP_FILE.write_text(original_html, encoding="utf-8")
    print(f"Backup created: {HTML_BACKUP_FILE}")

    # Replace sections
    new_html = original_html
    new_html = replace_section(new_html, *MARKERS["hero"], hero_html)
    new_html = replace_section(new_html, *MARKERS["featured"], featured_html)

    HTML_FILE.write_text(new_html, encoding="utf-8")
    print(f"Updated HTML written to: {HTML_FILE}")


if __name__ == "__main__":
    main()
