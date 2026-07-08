#!/usr/bin/env python3
"""Test suite for the Emoji Icon Generator."""

import io
import json
import os
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:4599"
PASS = 0
FAIL = 0

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  —  {detail}")

def api_get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read(), r.headers

def api_post(path, data):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers

# ── Tests ──────────────────────────────────────────────────────────

print("=" * 60)
print("TEST SUITE — Emoji Icon Generator")
print("=" * 60)

# 1. GET /
print("\n📄 Route: GET /")
status, body, headers = api_get("/")
test("HTTP 200", status == 200, f"got {status}")
test("Content-Type is text/html", "text/html" in headers.get("Content-Type", ""))
test("Contains <h1>", b"<h1>" in body)
test("Contains lang=it", b'lang="it"' in body)
test("Contains canonical", b"cristianporco.it/app/emojiicon/" in body)
test("Contains JSON-LD", b"application/ld+json" in body)
test("Contains viewport meta", b'name="viewport"' in body)

# 2. GET /api/emojis
print("\n📄 Route: GET /api/emojis")
status, body, headers = api_get("/api/emojis")
data = json.loads(body)
test("HTTP 200", status == 200)
test("Returns array", isinstance(data, list))
test("Has 64 emojis", len(data) == 64, f"got {len(data)}")
test("Contains 😀", "😀" in data)
test("Contains 🚀", "🚀" in data)
test("Content-Type JSON", "application/json" in headers.get("Content-Type", ""))

# 3. POST /api/generate
print("\n📄 Route: POST /api/generate — valid requests")

# 3a: Standard
status, body, headers = api_post("/api/generate", {"emoji": "😀", "bgColor": "#FFD23F", "size": 64})
test("HTTP 200", status == 200, f"got {status}")
test("Content-Type image/png", "image/png" in headers.get("Content-Type", ""))
test("Body is not empty", len(body) > 100, f"got {len(body)} bytes")
# Verify it's a valid PNG
from PIL import Image
try:
    img = Image.open(io.BytesIO(body))
    test("Valid PNG image", True)
    test(f"Dimensions {64}×{64}", img.size == (64, 64), f"got {img.size}")
    test("RGBA mode", img.mode == "RGBA", f"got {img.mode}")
except Exception as e:
    test("Valid PNG image", False, str(e))

# 3b: All sizes
for size in [16, 32, 64, 128]:
    status, body, headers = api_post("/api/generate", {"emoji": "⭐", "bgColor": "#6C5CE7", "size": size})
    img = Image.open(io.BytesIO(body))
    test(f"Size {size}×{size}", img.size == (size, size), f"got {img.size}")

# 3c: Transparent background
status, body, headers = api_post("/api/generate", {"emoji": "🔥", "bgColor": "transparent", "size": 64})
img = Image.open(io.BytesIO(body))
test("Transparent BG", img.mode == "RGBA")

# 3d: Various emojis
for emoji in ["😂", "💻", "🌈", "👍", "🎨"]:
    status, body, headers = api_post("/api/generate", {"emoji": emoji, "bgColor": "#FFFFFF", "size": 48})
    test(f"Emoji {emoji}", status == 200, f"got {status}")

# 4. POST /api/generate — error cases
print("\n📄 Route: POST /api/generate — error cases")
status, body, headers = api_post("/api/generate", {"size": 64})
test("Missing emoji → 400", status == 400, f"got {status}")
err = json.loads(body)
test("Error message present", "error" in err)

status, body, headers = api_post("/api/generate", {"emoji": "", "size": 64})
test("Empty emoji → 400", status == 400, f"got {status}")

# 5. POST /api/download
print("\n📄 Route: POST /api/download")
status, body, headers = api_post("/api/download", {"emoji": "🚀", "bgColor": "#FF5E8A", "size": 128})
test("HTTP 200", status == 200, f"got {status}")
test("Content-Type image/png", "image/png" in headers.get("Content-Type", ""))
test("Content-Disposition attachment", "attachment" in headers.get("Content-Disposition", ""))
img = Image.open(io.BytesIO(body))
test("Dimensions 128×128", img.size == (128, 128), f"got {img.size}")

# 6. SEO files
print("\n📄 SEO files")
status, body, headers = api_get("/robots.txt")
test("robots.txt HTTP 200", status == 200)
test("Contains Sitemap", b"Sitemap" in body)
test("Contains Allow", b"Allow" in body)

status, body, headers = api_get("/sitemap.xml")
test("sitemap.xml HTTP 200", status == 200)
test("Contains canonical URL", b"cristianporco.it/app/emojiicon/" in body)
test("Content-Type XML", "xml" in headers.get("Content-Type", ""))

# 7. Size clamping
print("\n📄 Input validation — size clamping")
status, body, headers = api_post("/api/generate", {"emoji": "😀", "size": 8})
test("Size 8 clamped to >=16", status == 200)
img = Image.open(io.BytesIO(body))
test(f"Clamped dimensions >=16", img.size[0] >= 16, f"got {img.size}")

status, body, headers = api_post("/api/generate", {"emoji": "😀", "size": 1024})
test("Size 1024 clamped to <=512", status == 200)
img = Image.open(io.BytesIO(body))
test(f"Clamped dimensions <=512", img.size[0] <= 512, f"got {img.size}")

# 8. Accessibility checks on HTML
print("\n📄 Accessibility (HTML structure)")
status, body, _ = api_get("/")
html = body.decode("utf-8")
test("Has <main> landmark", "<main>" in html)
test("Has <header> landmark", "<header>" in html)
test("Has <footer> landmark", "<footer>" in html)
test("Has aria-label attributes", 'aria-label' in html)
test("Has role attributes", 'role=' in html)
test("Has aria-live region", 'aria-live' in html)
test("Has <label> for hex input", 'for="hex-input"' in html)

# ── Summary ────────────────────────────────────────────────────────
print()
print("=" * 60)
print(f"RESULTS:  {PASS} passed, {FAIL} failed  ({(PASS + FAIL)} total)")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
