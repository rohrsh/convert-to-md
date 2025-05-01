#!/usr/bin/env python3
import os, pathlib, email, subprocess, re
from email.policy import default
from email.utils import parsedate_to_datetime
from datetime import datetime
import sys
from collections import defaultdict

INPUT_DIR = pathlib.Path(sys.argv[1])
OUTPUT_DIR = pathlib.Path(sys.argv[2])
OUTPUT_DIR.mkdir(exist_ok=True)

untitled_counters = defaultdict(int)

def clean_filename(name):
    cleaned = "".join(c for c in name if c.isalnum() or c in " -").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80]

def set_file_time(path, dt):
    mac_time = dt.strftime("%m/%d/%Y %H:%M:%S")
    try:
        subprocess.run(["SetFile", "-d", mac_time, "-m", mac_time, str(path)], check=True)
    except Exception:
        ts = dt.timestamp()
        os.utime(path, (ts, ts))

def safe_decode(payload, charset_hint):
    charset = charset_hint or "utf-8"
    try:
        text = payload.decode(charset).strip()
        # Check for garbage (too many nulls -> wrong decode)
        if text.count("\x00") > len(text) // 4:
            raise UnicodeDecodeError(charset, b"", 0, 1, "Suspicious decode result")
        return text
    except Exception:
        # Fallbacks
        try:
            return payload.decode("utf-8").strip()
        except:
            return payload.decode("latin1", errors="replace").strip()

for eml_path in sorted(INPUT_DIR.glob("*.eml")):
    with eml_path.open("rb") as f:
        msg = email.message_from_binary_file(f, policy=default)

    subject = msg.get("Subject")
    title = subject.strip() if subject else None

    raw_date = msg.get("Date")
    email_dt = None
    if raw_date:
        try:
            email_dt = parsedate_to_datetime(raw_date)
        except Exception:
            pass

    if not email_dt:
        ts = eml_path.stat().st_birthtime if hasattr(eml_path.stat(), 'st_birthtime') else eml_path.stat().st_mtime
        email_dt = datetime.fromtimestamp(ts)

    created_iso = email_dt.isoformat()
    date_str = email_dt.strftime("%Y-%m-%d")

    if title:
        base_filename = clean_filename(title)
    else:
        untitled_counters[date_str] += 1
        base_filename = f"EmailSelf {date_str} {untitled_counters[date_str]}"

    filename = base_filename + ".md"
    out_path = OUTPUT_DIR / filename

    suffix = 1
    while out_path.exists():
        filename = f"{base_filename}-{suffix}.md"
        out_path = OUTPUT_DIR / filename
        suffix += 1

    body = ""
    attachments = []

    def process_part(part):
        content_type = part.get_content_type()
        content_disposition = part.get_content_disposition()

        if (content_type.startswith("image/") or (content_disposition in ["attachment", "inline"] and part.get_filename() and part.get_filename().lower().endswith(('.jpg', '.jpeg', '.png', '.gif')))):

            ext = content_type.split("/")[1]
            filename = part.get_filename()
            if filename:
                name_part, ext_part = os.path.splitext(filename)
                if not ext_part:
                    ext_part = f".{ext}"
                filename = clean_filename(name_part) + ext_part
            else:
                filename = f"image_{len(attachments)+1}.{ext}"
            resources_dir = OUTPUT_DIR / "resources"
            resources_dir.mkdir(exist_ok=True)
            image_path = resources_dir / filename
            with image_path.open("wb") as img_file:
                img_file.write(part.get_payload(decode=True))
            attachments.append(f"![{filename}](resources/{filename})")
        elif content_type == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                return safe_decode(payload, part.get_content_charset())
        return None

    if msg.is_multipart():
        for part in msg.walk():
            result = process_part(part)
            if result:
                body = result
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = safe_decode(payload, msg.get_content_charset())

    out_path.write_text(f"---\ntitle: \"{title or filename[:-3]}\"\ncreated: {created_iso}\n---\n\n{body}\n\n", encoding="utf-8")

    if attachments:
        with out_path.open("a", encoding="utf-8") as out:
            out.write("\n".join(attachments) + "\n")

    set_file_time(out_path, email_dt)

    print(f"✓ {filename}")
