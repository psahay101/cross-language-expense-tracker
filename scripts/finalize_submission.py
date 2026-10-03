"""Insert a verified GitHub URL into the editable documentation sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve(value, url):
    if isinstance(value, str):
        return value.replace("REPOSITORY_URL_PENDING", url).replace(r"\u0027", "'")
    if isinstance(value, list):
        return [resolve(item, url) for item in value]
    if isinstance(value, dict):
        return {key: resolve(item, url) for key, item in value.items()}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_url")
    args = parser.parse_args()
    if not args.repository_url.startswith("https://github.com/"):
        parser.error("Expected a verified HTTPS GitHub repository URL.")
    for name in ("report_content.json", "comparison_content.json", "presentation_content.json"):
        path = ROOT / "docs" / name
        content = resolve(json.loads(path.read_text(encoding="utf-8-sig")), args.repository_url)
        if name == "report_content.json":
            for report in content:
                for section in report["sections"]:
                    section["paragraphs"] = [
                        paragraph.replace(
                            "The link will be replaced with the actual GitHub URL once repository creation is verified. ",
                            "Repository creation has been verified. ",
                        ) for paragraph in section.get("paragraphs", [])
                    ]
        if name == "presentation_content.json":
            content["slides"][4]["bullets"] = [
                "Live demo: three new expenses totaling $5.30",
                "Show listing, inclusive filters, and search",
                "Screenshot: five-record sample totaling $61.08",
                "Reuse the live CSV for the C++ walkthrough",
            ]
            content["slides"][4]["notes"] = content["slides"][4]["notes"].replace(
                "The screenshot is captured application output; use it as evidence or as a fallback if the live terminal is unavailable.",
                "The screenshot shows the five-record sample ($61.08), separate from the three-record live demo below ($5.30). Use it as genuine captured evidence if the terminal is unavailable.",
            )
            content["slides"][5]["bullets"] = [
                "Read Python's live CSV with C++",
                "Add a Books expense; expected total $25.29",
                "Delete it, reject an invalid date, and verify $5.30",
                "Screenshot: recorded five-expense sample ($61.08)",
            ]
            content["slides"][5]["notes"] = content["slides"][5]["notes"].replace(
                "Show the genuine C++ output screenshot if live output is unavailable.",
                "The screenshot shows the five-record sample ($61.08); the separate live interoperability demonstration below uses the three-record file created on slide 5.",
            )
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme = ROOT / "README.md"
    text = resolve(readme.read_text(encoding="utf-8"), args.repository_url)
    text = text.replace(
        "Publishing status and the real GitHub URL will be filled in after account authentication.",
        "The verified public repository URL is included above and in the reports.",
    )
    readme.write_text(text, encoding="utf-8")
    deck = json.loads((ROOT / "docs" / "presentation_content.json").read_text(encoding="utf-8"))
    notes_lines = [
        deck["title"],
        "Prateek Sahay and Venkata Sai Makani",
        "17 slides; 18 minutes total; 9 minutes planned per presenter.",
        args.repository_url,
        "",
    ]
    elapsed = 0
    for number, slide in enumerate(deck["slides"], 1):
        finish = elapsed + slide["duration_seconds"]
        interval = f"{elapsed // 60}:{elapsed % 60:02d}-{finish // 60}:{finish % 60:02d}"
        notes_lines.extend([
            f"Slide {number}: {slide['title']} ({interval})",
            f"Speaker: {slide['speaker']}",
            *[f"- {bullet}" for bullet in slide["bullets"]],
            "",
            slide["notes"],
            "",
        ])
        elapsed = finish
    (ROOT / "docs" / "presentation_notes.txt").write_text("\n".join(notes_lines), encoding="utf-8")
    print(f"Inserted verified repository URL: {args.repository_url}")


if __name__ == "__main__":
    main()
