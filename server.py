#!/usr/bin/env python3
"""Emoji Icon Generator — server-side PNG generation with Pillow."""

import io
import os
import hashlib
import urllib.request
from flask import Flask, request, jsonify, send_file, render_template

app = Flask(__name__)

# ── Emoji font paths (tried in order) ──────────────────────────────────────
EMOJI_FONT_PATHS = [
    "/System/Library/Fonts/Apple Color Emoji.ttc",  # macOS
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",  # Linux
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "C:\\Windows\\Fonts\\seguiemj.ttf",  # Windows
]

# Cache for CDN-fetched emoji images (keyed by codepoint)
_emoji_cache: dict[str, "Image.Image"] = {}

# Predefined emoji catalog
EMOJI_CATALOG = [
    # Smileys
    "😀", "😂", "🤣", "😍", "🥰", "😎", "🤩", "😇",
    "🤔", "😴", "🤗", "😋", "🫠", "🥳", "😤", "🤯",
    # Gestures
    "👍", "👎", "👏", "🙌", "🤝", "💪", "✌️", "🤞",
    # Symbols
    "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍",
    "⭐", "🌟", "🔥", "💯", "✨", "💎", "🎉", "🎈",
    # Objects
    "📱", "💻", "🖥️", "🎨", "📷", "🎵", "📚", "✏️",
    "🚀", "🏠", "🔑", "💡", "🛡️", "🏆", "🎯", "🧲",
    # Nature
    "🌞", "🌈", "🌸", "🌺", "🍀", "🌙", "⚡", "💧",
]

# ── Helpers ─────────────────────────────────────────────────────────────────


def _get_emoji_font(size: int):
    """Return a Pillow ImageFont for emoji rendering, or None."""
    from PIL import ImageFont

    clamped = min(size, 64)  # Apple Color Emoji maxes at <72
    for path in EMOJI_FONT_PATHS:
        if not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, clamped, index=0)
        except Exception:
            try:
                return ImageFont.truetype(path, clamped)
            except Exception:
                continue
    return None


def _render_emoji_pillow(char: str, size: int):
    """Render emoji directly via Pillow + system emoji font."""
    from PIL import Image, ImageDraw

    font = _get_emoji_font(size)
    if font is None:
        return None

    render_size = min(size, 64)
    img = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), char, font=font, embedded_color=True)

    # Crop to actual content
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    # Scale to requested size
    if img.width != size or img.height != size:
        # Scale preserving aspect ratio to fit within target
        scale = size / max(img.width, img.height)
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img


def _render_emoji_cdn(char: str, size: int):
    """Fallback: fetch emoji PNG from twemoji CDN."""
    from PIL import Image

    codepoint = "-".join(f"{ord(c):x}" for c in char)
    if codepoint in _emoji_cache:
        img = _emoji_cache[codepoint].copy()
    else:
        url = (
            "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest"
            f"/assets/72x72/{codepoint}.png"
        )
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "EmojiIconGenerator/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            _emoji_cache[codepoint] = img.copy()
        except Exception:
            return None

    if img.width != size:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def _render_emoji(char: str, size: int):
    """Render a single emoji character at the given pixel size."""
    # Strip variation selectors that can confuse font rendering
    import re
    clean = re.sub(r"[\ufe00-\ufe0f]", "", char)
    if not clean:
        clean = char

    img = _render_emoji_pillow(clean, size)
    if img is None:
        img = _render_emoji_cdn(clean, size)
    return img


def _parse_color(raw: str | None):
    """Parse a hex color string to (R, G, B) or None for transparent."""
    if not raw or raw.strip().lower() in ("", "transparent", "none"):
        return None
    h = raw.strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return None


def _generate_icon(emoji: str, bg_color: str | None, size: int):
    """Create a PNG icon: background + centered emoji."""
    from PIL import Image, ImageDraw

    # Clamp size
    size = max(16, min(512, size))

    # Create canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Background fill
    rgb = _parse_color(bg_color)
    if rgb is not None:
        draw = ImageDraw.Draw(img)
        r = max(2, size // 8)  # corner radius
        draw.rounded_rectangle(
            [(0, 0), (size - 1, size - 1)], radius=r, fill=(*rgb, 255)
        )

    # Render emoji at ~75% of canvas size
    emoji_size = max(16, int(size * 0.72))
    emoji_img = _render_emoji(emoji, emoji_size)

    if emoji_img is not None:
        # Center on canvas
        ox = (size - emoji_img.width) // 2
        oy = (size - emoji_img.height) // 2
        img.paste(emoji_img, (ox, oy), emoji_img)

    return img


# ── Routes ──────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Serve the main HTML page."""
    return render_template("index.html")


@app.route("/api/emojis")
def api_emojis():
    """Return the predefined emoji catalog."""
    return jsonify(EMOJI_CATALOG)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate a PNG icon and return it."""
    data = request.get_json(silent=True) or {}

    emoji = (data.get("emoji") or "").strip()
    if not emoji:
        return jsonify({"error": "Nessuna emoji fornita"}), 400

    bg = data.get("bgColor") or "transparent"
    try:
        size = int(data.get("size", 64))
    except (TypeError, ValueError):
        size = 64
    size = max(16, min(512, size))

    try:
        icon = _generate_icon(emoji, bg, size)
    except Exception as exc:
        return jsonify({"error": f"Generazione fallita: {exc}"}), 500

    buf = io.BytesIO()
    icon.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    # Derive a short filename from emoji codepoint
    cp = "-".join(f"{ord(c):x}" for c in emoji)
    filename = f"icon-{cp}-{size}px.png"

    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=False,  # preview in browser; download via ?download=1
        download_name=filename,
    )


@app.route("/api/download", methods=["POST"])
def api_download():
    """Same as generate but forces Content-Disposition: attachment."""
    data = request.get_json(silent=True) or {}

    emoji = (data.get("emoji") or "").strip()
    if not emoji:
        return jsonify({"error": "Nessuna emoji fornita"}), 400

    bg = data.get("bgColor") or "transparent"
    try:
        size = int(data.get("size", 64))
    except (TypeError, ValueError):
        size = 64
    size = max(16, min(512, size))

    try:
        icon = _generate_icon(emoji, bg, size)
    except Exception as exc:
        return jsonify({"error": f"Generazione fallita: {exc}"}), 500

    buf = io.BytesIO()
    icon.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    cp = "-".join(f"{ord(c):x}" for c in emoji)
    filename = f"icon-{cp}-{size}px.png"

    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/robots.txt")
def robots():
    """Serve robots.txt."""
    return send_file(
        io.BytesIO(
            b"Sitemap: https://github.com/bonciarello/emojiicon/sitemap.xml\n\n"
            b"User-agent: *\nAllow: /\n"
        ),
        mimetype="text/plain",
    )


@app.route("/sitemap.xml")
def sitemap():
    """Serve sitemap.xml."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        "    <loc>https://github.com/bonciarello/emojiicon/</loc>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "</urlset>\n"
    )
    return app.response_class(xml, mimetype="application/xml")


# ── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4599))
    app.run(host="0.0.0.0", port=port, debug=False)
