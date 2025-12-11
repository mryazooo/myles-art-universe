#!/usr/bin/env python3
"""
build_art_site.py

- Reads curated images from NAS share (finished + sketchbook)
- Copies them into the local repo images folders
- Updates:
    * Home page (index.html) hero + featured cards (from finished)
    * Home page sketch preview (latest sketches)
    * Gallery page (characters.html) full finished gallery
    * Sketchbook page (sketchbook.html) full sketchbook gallery
based on NAS images and sidecar .txt captions + .json metadata.
"""

import shutil
import re
import json
from pathlib import Path
from typing import List, Tuple

# --------------------
# CONFIGURATION
# --------------------

# NAS source folders (adjust IP/hostname as needed)
NAS_FINISHED_DIR = r"\\192.168.2.132\art-site\finished"
NAS_SKETCHBOOK_DIR = r"\\192.168.2.132\art-site\sketchbook"

# Local repo folders where images are stored
REPO_ROOT = Path(__file__).resolve().parent
LOCAL_FINISHED_DIR = REPO_ROOT / "images" / "finished"
LOCAL_SKETCHBOOK_DIR = REPO_ROOT / "images" / "sketchbook"

# HTML files to update
HOME_HTML_FILE = REPO_ROOT / "index.html"
HOME_HTML_BACKUP_FILE = REPO_ROOT / "index.backup.html"

GALLERY_HTML_FILE = REPO_ROOT / "characters.html"
GALLERY_HTML_BACKUP_FILE = REPO_ROOT / "characters.backup.html"

SKETCHBOOK_HTML_FILE = REPO_ROOT / "sketchbook.html"
SKETCHBOOK_HTML_BACKUP_FILE = REPO_ROOT / "sketchbook.backup.html"

# Markers in the HTML files
MARKERS_HOME = {
    "hero": ("<!-- START HERO -->", "<!-- END HERO -->"),
    "featured": ("<!-- START FEATURED -->", "<!-- END FEATURED -->"),
    "sketch_preview": ("<!-- START HOME_SKETCHES -->", "<!-- END HOME_SKETCHES -->"),
}

MARKERS_GALLERY = {
    "gallery_finished": ("<!-- START GALLERY_FINISHED -->", "<!-- END GALLERY_FINISHED -->"),
}

MARKERS_SKETCHBOOK = {
    "gallery_sketchbook": ("<!-- START GALLERY_SKETCHBOOK -->", "<!-- END GALLERY_SKETCHBOOK -->"),
}

# How many featured images to show on the home page (after hero)
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

    images.sort(key=lambda t: t[0].stat().st_mtime, reverse=True)
    return images


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_images(src_items: List[Tuple[Path, str]], dest_folder: Path) -> List[Tuple[str, str]]:
    """
    Copies images to dest_folder.
    Returns list of (file_name, caption) relative to dest_folder.
    Keeps order the same as src_items (which is already newest-first).
    """
    ensure_dir(dest_folder)
    # clear existing images so it stays in sync
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
    """Minimal HTML escaping for captions/titles."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _derive_title_and_body(file_name: str, caption: str) -> Tuple[str, str]:
    """
    Helper to derive a nice title + body from filename + caption.
    - Title = first part of caption (split on '—') or filename-based
    - Body  = full caption, or fallback sentence
    """
    if caption:
        raw_title = caption.split("—")[0].strip()
        if raw_title:
            title = raw_title
        else:
            stem = Path(file_name).stem.replace("_", " ")
            title = stem.title()
        body = caption
    else:
        stem = Path(file_name).stem.replace("_", " ")
        title = stem.title()
        body = "New artwork from Myles."

    return escape_html(title), escape_html(body)


# ---------- METADATA HELPERS (JSON from NAS) ----------

def _get_nas_folder_for_kind(kind: str) -> Path:
    if kind == "sketchbook":
        return Path(NAS_SKETCHBOOK_DIR)
    return Path(NAS_FINISHED_DIR)


def get_metadata_for_image(file_name: str, kind: str) -> dict:
    """
    Load JSON metadata for an image from the NAS if available.

    Returns a dict with at least:
      { "slug": str, "tags": List[str], "characters": List[str], "kind": str }

    Falls back gracefully if JSON is missing or malformed.
    """
    nas_folder = _get_nas_folder_for_kind(kind)
    json_path = nas_folder / (Path(file_name).stem + ".json")

    meta = {
        "slug": "",
        "tags": [],
        "characters": [],
        "kind": kind,
    }

    if not json_path.exists():
        return meta

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return meta

    # Normalise fields
    slug = str(data.get("slug") or "").strip()
    tags = data.get("tags") or []
    characters = data.get("characters") or []
    kind_val = str(data.get("kind") or kind).strip() or kind

    # Clean lists
    clean_tags = [str(t).strip() for t in tags if str(t).strip()]
    clean_chars = [str(c).strip() for c in characters if str(c).strip()]

    meta["slug"] = slug
    meta["tags"] = clean_tags
    meta["characters"] = clean_chars
    meta["kind"] = kind_val

    return meta


def build_data_attributes(meta: dict) -> str:
    """
    Build a string of data-* attributes from metadata, e.g.
      data-slug="leonardo-action-pose"
      data-kind="finished"
      data-tags="comic art,fan art"
      data-characters="Leonardo"
    """
    parts = []

    if meta.get("slug"):
        parts.append(f' data-slug="{escape_html(meta["slug"])}"')

    if meta.get("kind"):
        parts.append(f' data-kind="{escape_html(meta["kind"])}"')

    if meta.get("tags"):
        tags_val = ",".join(meta["tags"])
        parts.append(f' data-tags="{escape_html(tags_val)}"')

    if meta.get("characters"):
        chars_val = ",".join(meta["characters"])
        parts.append(f' data-characters="{escape_html(chars_val)}"')

    return "".join(parts)


# ---------- HTML BUILDERS ----------

def build_hero_html(file_name: str, caption: str) -> str:
    """
    Builds the hero-image block for index.html.
    Uses caption as alt text if available; otherwise falls back to filename-based title.
    Attaches JSON metadata as data-* attributes on the <img>.
    """
    img_src = f"images/finished/{file_name}"

    if caption:
        alt = escape_html(caption)
    else:
        stem = Path(file_name).stem.replace("_", " ")
        alt = stem.title()

    meta = get_metadata_for_image(file_name, kind="finished")
    data_attrs = build_data_attributes(meta)

    return (
        '<div class="hero-image">\n'
        f'  <img src="{img_src}" alt="{alt}" class="hero-art"{data_attrs} />\n'
        '</div>'
    )


def build_featured_html(items: List[Tuple[str, str]]) -> str:
    """
    Builds the Featured Pieces card grid for the home page.
    Uses caption as the title where possible.
    Attaches JSON metadata as data-* attributes on each <article>.
    """
    if not items:
        return '<div class="card-grid"></div>'

    cards = []
    for file_name, caption in items:
        img_src = f"images/finished/{file_name}"
        title, body = _derive_title_and_body(file_name, caption)

        meta = get_metadata_for_image(file_name, kind="finished")
        data_attrs = build_data_attributes(meta)

        card = (
            f'  <article class="card"{data_attrs}>\n'
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


def build_gallery_html(items: List[Tuple[str, str]], subfolder: str) -> str:
    """
    Builds a full gallery grid (.card layout) for either finished or sketchbook.
    subfolder is "finished" or "sketchbook" to build the correct image src paths.
    Attaches JSON metadata as data-* attributes on each <article>.
    """
    if not items:
        return '<div class="card-grid gallery-grid"></div>'

    kind = subfolder  # "finished" or "sketchbook"
    cards = []
    for file_name, caption in items:
        img_src = f"images/{subfolder}/{file_name}"
        title, body = _derive_title_and_body(file_name, caption)

        meta = get_metadata_for_image(file_name, kind=kind)
        data_attrs = build_data_attributes(meta)

        card = (
            f'  <article class="card gallery-card"{data_attrs}>\n'
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

    return "<div class=\"card-grid gallery-grid\">\n" + "\n\n".join(cards) + "\n</div>"


def build_home_sketches_html(items: List[Tuple[str, str]]) -> str:
    """
    Builds the small 2x2 sketch preview grid for the home page.
    - Uses up to 4 latest sketches with images.
    - Fills remaining slots (to 4) with 'Future sketch' placeholders.
    Attaches JSON metadata as data-* attributes on each sketch <div>.
    """
    cells = []
    max_sketches = 4
    used = items[:max_sketches]

    for file_name, caption in used:
        img_src = f"images/sketchbook/{file_name}"
        title, _ = _derive_title_and_body(file_name, caption)

        meta = get_metadata_for_image(file_name, kind="sketchbook")
        data_attrs = build_data_attributes(meta)

        cell = (
            f'  <div class="sketch"{data_attrs}>\n'
            f'    <img src="{img_src}" alt="{title}" />\n'
            '  </div>'
        )
        cells.append(cell)

    # Fill remaining cells up to 4 with placeholders (only if you have < 4 sketches)
    while len(cells) < 4:
        cells.append('  <div class="sketch placeholder"><span>Future sketch</span></div>')

    return "<div class=\"sketch-preview-grid\">\n" + "\n".join(cells) + "\n</div>"


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
    # ----- FINISHED -----
    nas_finished = Path(NAS_FINISHED_DIR)
    if not nas_finished.exists():
        raise SystemExit(f"NAS finished folder does not exist: {nas_finished}")

    finished_items = list_images_with_captions(nas_finished)
    if not finished_items:
        print("Warning: no images found in finished folder.")

    copied_finished = copy_images(finished_items, LOCAL_FINISHED_DIR)
    print(f"Copied {len(copied_finished)} finished images to {LOCAL_FINISHED_DIR}")

    # hero + featured (newest-first behaviour)
    hero = copied_finished[0] if copied_finished else None
    featured = copied_finished[1:1 + NUM_FEATURED] if len(copied_finished) > 1 else []

    hero_html = build_hero_html(hero[0], hero[1]) if hero else '<div class="hero-image"></div>'
    featured_html = build_featured_html(featured)
    gallery_finished_html = build_gallery_html(copied_finished, "finished")

    # ----- SKETCHBOOK -----
    nas_sketchbook = Path(NAS_SKETCHBOOK_DIR)
    sketchbook_items: List[Tuple[Path, str]] = []
    copied_sketchbook: List[Tuple[str, str]] = []

    if nas_sketchbook.exists():
        sketchbook_items = list_images_with_captions(nas_sketchbook)
        copied_sketchbook = copy_images(sketchbook_items, LOCAL_SKETCHBOOK_DIR)
        print(f"Copied {len(copied_sketchbook)} sketchbook images to {LOCAL_SKETCHBOOK_DIR}")
    else:
        print(f"Sketchbook folder does not exist on NAS: {nas_sketchbook}")

    gallery_sketchbook_html = build_gallery_html(copied_sketchbook, "sketchbook")
    home_sketches_html = build_home_sketches_html(copied_sketchbook)

    # --------------------
    # Update HOME page
    # --------------------
    if not HOME_HTML_FILE.exists():
        raise SystemExit(f"Home HTML file not found: {HOME_HTML_FILE}")

    original_home = HOME_HTML_FILE.read_text(encoding="utf-8")
    HOME_HTML_BACKUP_FILE.write_text(original_home, encoding="utf-8")
    print(f"Home backup created: {HOME_HTML_BACKUP_FILE}")

    new_home = original_home
    new_home = replace_section(new_home, *MARKERS_HOME["hero"], hero_html)
    new_home = replace_section(new_home, *MARKERS_HOME["featured"], featured_html)
    new_home = replace_section(new_home, *MARKERS_HOME["sketch_preview"], home_sketches_html)
    HOME_HTML_FILE.write_text(new_home, encoding="utf-8")
    print(f"Updated home HTML written to: {HOME_HTML_FILE}")

    # --------------------
    # Update GALLERY page
    # --------------------
    if GALLERY_HTML_FILE.exists():
        original_gallery = GALLERY_HTML_FILE.read_text(encoding="utf-8")
        GALLERY_HTML_BACKUP_FILE.write_text(original_gallery, encoding="utf-8")
        print(f"Gallery backup created: {GALLERY_HTML_BACKUP_FILE}")

        new_gallery = replace_section(
            original_gallery,
            *MARKERS_GALLERY["gallery_finished"],
            gallery_finished_html,
        )
        GALLERY_HTML_FILE.write_text(new_gallery, encoding="utf-8")
        print(f"Updated gallery HTML written to: {GALLERY_HTML_FILE}")
    else:
        print(f"Warning: Gallery HTML file not found: {GALLERY_HTML_FILE}")

    # --------------------
    # Update SKETCHBOOK page
    # --------------------
    if SKETCHBOOK_HTML_FILE.exists():
        original_sketchbook = SKETCHBOOK_HTML_FILE.read_text(encoding="utf-8")
        SKETCHBOOK_HTML_BACKUP_FILE.write_text(original_sketchbook, encoding="utf-8")
        print(f"Sketchbook backup created: {SKETCHBOOK_HTML_BACKUP_FILE}")

        new_sketchbook = replace_section(
            original_sketchbook,
            *MARKERS_SKETCHBOOK["gallery_sketchbook"],
            gallery_sketchbook_html,
        )
        SKETCHBOOK_HTML_FILE.write_text(new_sketchbook, encoding="utf-8")
        print(f"Updated sketchbook HTML written to: {SKETCHBOOK_HTML_FILE}")
    else:
        print(f"Warning: Sketchbook HTML file not found: {SKETCHBOOK_HTML_FILE}")


if __name__ == "__main__":
    main()
