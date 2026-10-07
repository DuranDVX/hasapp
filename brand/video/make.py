"""SiteBakkie app video: 1080x1920, silent, the same style as the QuoteBakkie one
(~/quotebot/brand/video/compose.py) in SiteBakkie orange. Uses shots/ from capture.py.

    .venv/bin/python brand/video/make.py
"""
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
SHOTS, SLIDES, OUT = HERE / "shots", HERE / "slides", HERE / "out"
SLIDES.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
DELIVER = Path("/Users/duranx/DuranX/Claude Code Projects/Bakkie/SiteBakkie/Video")
W, H, FPS, FADE = 1080, 1920, 30, 0.45
NAVY, ORANGE, WHITE, SOFT = (18, 36, 51), (242, 107, 29), (255, 255, 255), (200, 214, 226)
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
LOGO = Image.open(HERE.parents[1] / "web" / "logo.png").convert("RGBA")


def font(path, size):
    return ImageFont.truetype(path, size)


def fit(d, text, path, size, max_w=980):
    """The largest font up to `size` that keeps the line inside the frame."""
    while size > 30 and d.textlength(text, font=font(path, size)) > max_w:
        size -= 2
    return font(path, size)


def background():
    """Navy with a warm orange glow at the bottom."""
    y = np.linspace(0, 1, H)[:, None]
    base, glow = np.array(NAVY, float), np.array((84, 44, 22), float)
    arr = base + (glow - base) * (y ** 2.2)
    return Image.fromarray(np.repeat(arr[:, None, :], W, axis=1).reshape(H, W, 3).astype(np.uint8), "RGB").convert("RGBA")


def centered(d, y, text, f, fill):
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)


def caption(img, title, sub):
    d = ImageDraw.Draw(img)
    centered(d, 120, title, fit(d, title, BLACK, 74), WHITE)
    if sub:
        centered(d, 225, sub, fit(d, sub, BOLD, 42), ORANGE)


def logo_pill(img, y=1800, h=70):
    lw = int(LOGO.width * h / LOGO.height)
    lg = LOGO.resize((lw, h), Image.LANCZOS)
    pad = 30
    pill = Image.new("RGBA", (lw + 2 * pad, h + 30), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle((0, 0, pill.width - 1, pill.height - 1), 42, fill=WHITE)
    pill.alpha_composite(lg, (pad, 15))
    img.alpha_composite(pill, ((W - pill.width) // 2, y - pill.height // 2))


def phone(img, shot, top=330, height=1380):
    s = Image.open(shot).convert("RGBA")
    sh = height - 40
    sw = int(s.width * sh / s.height)
    s = s.resize((sw, sh), Image.LANCZOS)
    mask = Image.new("L", s.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw - 1, sh - 1), 46, fill=255)
    fw, fh = sw + 40, height
    frame = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (fw + 120, fh + 120), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((60, 80, fw + 60, fh + 60), 70, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(30))
    x = (W - fw) // 2
    img.alpha_composite(shadow, (x - 60, top - 60))
    ImageDraw.Draw(frame).rounded_rectangle((0, 0, fw - 1, fh - 1), 66, fill=(10, 14, 20, 255))
    frame.paste(s, (20, 20), mask)
    img.alpha_composite(frame, (x, top))


def slide(title, sub, shot):
    img = background()
    caption(img, title, sub)
    phone(img, SHOTS / shot)
    logo_pill(img)
    return img


def logo_card(img, y, card_w=900):
    lw = card_w - 120
    lh = int(LOGO.height * lw / LOGO.width)
    card = Image.new("RGBA", (card_w, lh + 120), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), 50, fill=WHITE)
    card.alpha_composite(LOGO.resize((lw, lh), Image.LANCZOS), (60, 60))
    img.alpha_composite(card, ((W - card_w) // 2, y))


def title_card():
    img = background()
    logo_card(img, 500)
    d = ImageDraw.Draw(img)
    centered(d, 820, "Hours of safety", font(BLACK, 88), WHITE)
    centered(d, 930, "paperwork?", font(BLACK, 88), WHITE)
    centered(d, 1110, "Say the day instead.", fit(d, "Say the day instead.", BLACK, 80), ORANGE)
    centered(d, 1270, "AI-powered site safety from a voice note", fit(d, "AI-powered site safety from a voice note", BOLD, 44), SOFT)
    return img


def end_card():
    img = background()
    d = ImageDraw.Draw(img)
    logo_pill(img, y=500, h=110)
    centered(d, 680, "Say the day.", font(BLACK, 92), WHITE)
    centered(d, 795, "The safety file", font(BLACK, 92), ORANGE)
    centered(d, 905, "keeps itself.", font(BLACK, 92), ORANGE)
    y = 1100
    for line in ("14 days free · no card needed", "Task sheets, talks & incidents by voice", "Any phone · works offline"):
        centered(d, y, line, fit(d, line, BOLD, 50), WHITE)
        y += 88
    bw, bh = 780, 130
    bx, by = (W - bw) // 2, 1420
    d.rounded_rectangle((bx, by, bx + bw, by + bh), 65, fill=ORANGE)
    centered(d, by + 34, "sitebakkie.co.za", font(BLACK, 58), WHITE)
    centered(d, 1660, "For builders, civil contractors & site managers", fit(d, "For builders, civil contractors & site managers", REG, 38), (170, 186, 200))
    return img


def main():
    scenes = [  # (image, seconds)
        (title_card(), 3.2),
        (slide("Green or red at a glance", "See what's missing before the inspector does", "1_board.png"), 3.4),
        (slide("Say the day", "Who does what, where, with which machines", "2_record.png"), 3.0),
        (slide("A task sheet in seconds", "Hazards, controls & PPE from your risk assessment", "3_task.png"), 3.4),
        (slide("Workers sign on the phone", "Dated, located and sealed", "4_sign.png"), 3.2),
        (slide("Toolbox talks in 7 languages", "Written for today's work", "5_talk.png"), 3.2),
        (slide("Incident? Say what happened", "Flash report & Annexure 1, filled in", "6_incident.png"), 3.4),
        (slide("The H&S plan, drafted for you", "Your safety officer checks and signs", "7_plan.png"), 3.4),
        (slide("The safety file, always ready", "One PDF · works offline · print on demand", "8_file.png"), 3.2),
        (end_card(), 4.2),
    ]
    for i, (im, _) in enumerate(scenes):
        im.convert("RGB").save(SLIDES / f"s{i:02d}.png")

    # each slide gets a slow zoom, then a crossfade into the next (as in the QuoteBakkie video)
    inputs, filters = [], []
    for i, (_, dur) in enumerate(scenes):
        inputs += ["-i", str(SLIDES / f"s{i:02d}.png")]
        frames = int((dur + FADE) * FPS)
        filters.append(f"[{i}:v]scale=2160:3840,zoompan=z='min(1+0.00035*on,1.06)':d={frames}:"
                       f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},format=yuv420p[v{i}]")
    prev, t = "v0", scenes[0][1]
    for i in range(1, len(scenes)):
        filters.append(f"[{prev}][v{i}]xfade=transition=fade:duration={FADE}:offset={t:.2f}[x{i}]")
        prev, t = f"x{i}", t + scenes[i][1]
    out = OUT / "SiteBakkie-app-video.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
                    "-map", f"[{prev}]", "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-pix_fmt", "yuv420p",
                    "-r", str(FPS), "-movflags", "+faststart", str(out)], check=True)
    DELIVER.mkdir(parents=True, exist_ok=True)
    shutil.copy(out, DELIVER / "sitebakkie.mp4")
    for i in range(len(scenes)):   # the stills too, for editing
        (DELIVER / "slides").mkdir(exist_ok=True)
        shutil.copy(SLIDES / f"s{i:02d}.png", DELIVER / "slides" / f"s{i:02d}.png")
    print("video:", DELIVER / "sitebakkie.mp4", f"{t + FADE:.1f}s", round(out.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
