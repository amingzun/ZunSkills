#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional


STYLES = ["保守稳重", "清爽专业", "高级设计感"]

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
CHROME_WAIT_SECONDS = 20
CHROME_GRACE_SECONDS = 2


def safe_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "", name.strip())
    return cleaned or "未命名"


def file_names(name: str) -> dict[str, str]:
    n = safe_name(name)
    return {
        "markdown": f"简历_{n}.md",
        "pdf": f"简历_{n}.pdf",
        "photo": f"照片_{n}.jpg",
        "stable_html": f"resume_{n}_保守稳重.html",
        "clean_html": f"resume_{n}_清爽专业.html",
        "premium_html": f"resume_{n}_高级设计感.html",
    }


def render_markdown(data: dict) -> str:
    name = data.get("name", "未命名")
    lines = [f"# {name}", ""]
    contact = []
    if data.get("phone"):
        contact.append(f"电话：{data['phone']}")
    if data.get("email"):
        contact.append(f"邮箱：{data['email']}")
    if data.get("location"):
        contact.append(f"现居：{data['location']}")
    if contact:
        lines.extend(["## 个人信息", "", *[f"- {item}" for item in contact], ""])
    if data.get("target_role"):
        lines.extend(["## 求职目标", "", data["target_role"], ""])
    if data.get("education"):
        lines.extend(["## 教育背景", ""])
        for item in data["education"]:
            title = "，".join(
                part
                for part in [
                    item.get("school"),
                    item.get("major"),
                    item.get("degree"),
                    item.get("date"),
                ]
                if part
            )
            lines.append(f"- {title}")
        lines.append("")
    if data.get("experience"):
        lines.extend(["## 工作经历", ""])
        for item in data["experience"]:
            title = " ｜ ".join(
                part
                for part in [item.get("company"), item.get("role"), item.get("date")]
                if part
            )
            lines.append(f"### {title}")
            for bullet in item.get("bullets", []):
                lines.append(f"- {bullet}")
            lines.append("")
    if data.get("skills"):
        lines.extend(["## 专业技能", "", *[f"- {skill}" for skill in data["skills"]], ""])
    if data.get("certificates"):
        lines.extend(
            ["## 技能证书", "", *[f"- {cert}" for cert in data["certificates"]], ""]
        )
    if data.get("summary"):
        lines.extend(["## 自我评价", "", data["summary"], ""])
    return "\n".join(lines).strip() + "\n"


def validate_html_document(html: str) -> None:
    lower = html.lower()
    required = ["<!doctype html", "<html", "<style", "@page", 'class="page"', 'class="portrait"']
    missing = [item for item in required if item not in lower]
    if missing:
        raise ValueError("HTML is missing required resume structure: " + ", ".join(missing))


def photo_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def ensure_workdir(base: Path, name: str) -> Path:
    workdir = base / safe_name(name)
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_html(path: Path, html: str) -> None:
    validate_html_document(html)
    write_text(path, html)


def expected_output_path(args: list[str]) -> Optional[Path]:
    for arg in args:
        if arg.startswith("--print-to-pdf="):
            return Path(arg.split("=", 1)[1])
    return None


def cleanup_old_chrome_profiles(tmp_root: Path) -> None:
    now = time.time()
    for path in tmp_root.glob("resume-pdf-maker-chrome-*"):
        try:
            if path.is_dir() and now - path.stat().st_mtime > 24 * 60 * 60:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


def run_chrome(args: list[str]) -> None:
    if not CHROME.exists():
        raise SystemExit(f"Chrome not found: {CHROME}")
    expected_output = expected_output_path(args)
    tmp_root = Path(tempfile.gettempdir())
    cleanup_old_chrome_profiles(tmp_root)
    profile = tempfile.mkdtemp(prefix="resume-pdf-maker-chrome-")
    command = [
        str(CHROME),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--noerrdialogs",
        "--disable-crash-reporter",
        "--disable-breakpad",
        "--disable-session-crashed-bubble",
        "--disable-extensions",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-features=Translate,OptimizationHints",
        "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=1000",
        *args,
    ]
    proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cleanup_profile = False
    deadline = time.time() + CHROME_WAIT_SECONDS
    while time.time() < deadline:
        code = proc.poll()
        if code == 0:
            cleanup_profile = True
            break
        if code is not None:
            if expected_output and expected_output.exists() and expected_output.stat().st_size > 0:
                cleanup_profile = True
                break
            raise subprocess.CalledProcessError(code, command)
        if expected_output and expected_output.exists() and expected_output.stat().st_size > 0:
            try:
                code = proc.wait(timeout=CHROME_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                # Do not terminate the macOS Chrome app here: forced shutdowns can
                # trigger the system "Google Chrome unexpectedly quit" dialog.
                return
            cleanup_profile = True
            if code == 0:
                break
            break
        time.sleep(0.2)
    else:
        if expected_output and expected_output.exists() and expected_output.stat().st_size > 0:
            return
        raise TimeoutError("Chrome did not produce the expected output before timeout")

    if cleanup_profile:
        shutil.rmtree(profile, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="resume_pdf_maker.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--base", required=True)
    p_init.add_argument("--name", required=True)

    p_md = sub.add_parser("write-md")
    p_md.add_argument("--base", required=True)
    p_md.add_argument("--data", required=True)

    p_write_html = sub.add_parser("write-html")
    p_write_html.add_argument("--out", required=True)

    p_photo = sub.add_parser("embed-photo")
    p_photo.add_argument("--html", required=True)
    p_photo.add_argument("--photo", required=True)
    p_photo.add_argument("--out", required=True)

    p_pdf = sub.add_parser("pdf")
    p_pdf.add_argument("--html", required=True)
    p_pdf.add_argument("--out", required=True)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--pdf", required=True)

    args = parser.parse_args()
    if args.command == "init":
        print(ensure_workdir(Path(args.base), args.name))
    elif args.command == "write-md":
        data = load_json(Path(args.data))
        workdir = ensure_workdir(Path(args.base), data.get("name", "未命名"))
        out = workdir / file_names(data.get("name", "未命名"))["markdown"]
        write_text(out, render_markdown(data))
        print(out)
    elif args.command == "write-html":
        html = sys.stdin.read()
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_html(out, html)
        print(out)
    elif args.command == "embed-photo":
        html_path = Path(args.html)
        html = html_path.read_text(encoding="utf-8")
        uri = photo_data_uri(Path(args.photo))
        portrait_body = ""
        if 'class="portrait"' in html:
            portrait_body = html.split('class="portrait"', 1)[1].split("</div>", 1)[0]
        if 'class="portrait"' in html and "<img" not in portrait_body:
            html = html.replace(
                'aria-label="证件照">',
                f'aria-label="证件照"><img src="{uri}" alt="证件照">',
                1,
            )
        Path(args.out).write_text(html, encoding="utf-8")
        print(args.out)
    elif args.command == "pdf":
        run_chrome([f"--print-to-pdf={args.out}", f"file://{Path(args.html).resolve()}"])
        print(args.out)
    elif args.command == "verify":
        pdf = Path(args.pdf)
        data = pdf.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise SystemExit("Invalid PDF header")
        print(f"valid pdf: {pdf} bytes={len(data)}")


if __name__ == "__main__":
    main()
