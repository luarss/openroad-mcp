#!/usr/bin/env python3
"""
Scrape OpenROAD error patterns from documentation and source code.

This script extracts error message patterns from:
1. OpenROAD Messages Glossary (documentation) - via web scraping
2. OpenROAD source code (logger calls) - via git clone or local repo

Usage:
    python scripts/update_error_patterns.py --source github [--clone-dir /tmp/openroad]
    python scripts/update_error_patterns.py --source local --repo-path /path/to/OpenROAD
    python scripts/update_error_patterns.py --source docs  # scrape documentation only

Requirements:
    pip install beautifulsoup4 requests gitpython
"""

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: Missing dependencies. Install with:")
    print("  pip install beautifulsoup4 requests")
    exit(1)


def scrape_openroad_docs() -> list[tuple[str, str, str]]:
    """Scrape error patterns from OpenROAD documentation."""
    print("Scraping OpenROAD documentation...")
    url = "https://openroad.readthedocs.io/en/latest/user/MessagesFinal.html"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch documentation: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    patterns = []

    tables = soup.find_all("table")
    print(f"Found {len(tables)} tables in documentation")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            tool = cells[0].get_text(strip=True)
            code = cells[1].get_text(strip=True)
            msg_type = cells[3].get_text(strip=True).upper()

            if msg_type in ["ERROR", "CRITICAL", "FATAL"]:
                pattern = rf"\[{tool}-{code}\]\s*{msg_type}:\s*(.+?)(?:\r?\n|$)"
                message = f"[{tool}-{code}] {msg_type.title()}: {{0}}"
                patterns.append((pattern, message, "docs"))

    print(f"Extracted {len(patterns)} error patterns from docs")
    return patterns


def clone_openroad_repo(clone_dir: Path) -> bool:
    """Clone OpenROAD repository."""
    if clone_dir.exists():
        print(f"Repository already exists at {clone_dir}")
        return True

    print(f"Cloning OpenROAD repository to {clone_dir}...")
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", "https://github.com/The-OpenROAD-Project/OpenROAD.git", str(clone_dir)],
            check=True,
            capture_output=True,
        )
        print("Clone successful")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Clone failed: {e}")
        return False


def scrape_source_code(repo_path: Path) -> list[tuple[str, str, str]]:
    """Scrape error patterns from OpenROAD source code."""
    print(f"Scanning source code at {repo_path}...")
    patterns = []

    logger_error_pattern = re.compile(
        r'logger[_\-]?>(?:error|warn|critical)\s*\(\s*(\w+)\s*,\s*(\d+)\s*,\s*["\']([^"\']+)["\']', re.IGNORECASE
    )

    ord_error_pattern = re.compile(r'ord::(?:error|warn)\s*\(["\']([^"\']+)["\']', re.IGNORECASE)

    src_dirs = [repo_path / "src", repo_path / "include"]

    for src_dir in src_dirs:
        if not src_dir.exists():
            continue

        cpp_files = list(src_dir.rglob("*.cpp")) + list(src_dir.rglob("*.cc")) + list(src_dir.rglob("*.h"))
        print(f"Scanning {len(cpp_files)} files in {src_dir.name}...")

        for cpp_file in cpp_files:
            try:
                with open(cpp_file, encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                    for match in logger_error_pattern.finditer(content):
                        tool, code, msg = match.groups()
                        regex = rf"\[{tool}-{code.zfill(4)}\].*?{re.escape(msg[:30])}"
                        message_template = f"[{tool}-{code.zfill(4)}] Error: {{0}}"
                        patterns.append((regex, message_template, "source"))

                    for match in ord_error_pattern.finditer(content):
                        msg = match.group(1)
                        if "error" in msg.lower() or "fail" in msg.lower():
                            regex = rf"{re.escape(msg[:40])}"
                            patterns.append((regex, msg, "source"))

            except Exception as e:
                print(f"Error reading {cpp_file}: {e}")

    print(f"Extracted {len(patterns)} patterns from source code")
    return patterns


def extract_patterns_from_tcl_source(repo_path: Path) -> list[tuple[str, str, str]]:
    """Extract TCL error patterns by analyzing TCL command implementations."""
    print(f"Extracting TCL error patterns from {repo_path}...")
    patterns = []

    tcl_files = list(repo_path.rglob("*.tcl"))
    cpp_files_with_tcl = []

    for src_dir in [repo_path / "src"]:
        if src_dir.exists():
            cpp_files_with_tcl.extend(src_dir.rglob("*.cpp"))

    print(f"Scanning {len(tcl_files)} TCL files and {len(cpp_files_with_tcl)} C++ files for TCL errors...")

    tcl_error_calls = re.compile(r'(?:error|return\s+-code\s+error)\s+["\']([^"\']+)["\']')

    seen_messages = set()

    for file in tcl_files + cpp_files_with_tcl:
        try:
            with open(file, encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for match in tcl_error_calls.finditer(content):
                    msg = match.group(1)
                    if msg and len(msg) > 5 and msg not in seen_messages:
                        regex = re.escape(msg[:50])
                        patterns.append((regex, msg, "tcl"))
                        seen_messages.add(msg)
        except Exception:
            pass

    print(f"Extracted {len(patterns)} TCL error patterns")
    return patterns


def deduplicate_patterns(patterns: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Remove duplicate patterns based on regex."""
    seen = set()
    unique = []
    for regex, message, category in patterns:
        if regex not in seen:
            seen.add(regex)
            unique.append((regex, message, category))
    return unique


def write_patterns_file(patterns: list[tuple[str, str, str]], output_file: Path) -> None:
    """Write patterns to output file with nice formatting."""
    with open(output_file, "w") as f:
        f.write("# OpenROAD Error Patterns\n")
        f.write("# Auto-generated by scripts/update_error_patterns.py\n")
        f.write("# Format: regex_pattern|message_template\n")
        f.write("# Lines starting with # are comments\n")
        f.write("#\n")
        f.write("# Message templates use {0}, {1}, etc. for regex capture groups\n")
        f.write("# Patterns are checked in order, so put specific patterns before generic ones\n")
        f.write("\n")

        by_category = {}
        for regex, message, category in patterns:
            if category not in by_category:
                by_category[category] = []
            by_category[category].append((regex, message))

        for category in sorted(by_category.keys()):
            f.write(f"# {category.upper()} ERRORS\n")
            for regex, message in by_category[category]:
                f.write(f"{regex}|{message}\n")
            f.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Update OpenROAD error patterns")
    parser.add_argument(
        "--source",
        choices=["github", "local", "docs", "tcl"],
        default="docs",
        help="Source to extract patterns from (default: docs)",
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        help="Path to local OpenROAD repository (for --source local)",
    )
    parser.add_argument(
        "--clone-dir",
        type=Path,
        help="Directory to clone OpenROAD repo (for --source github)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "src/openroad_mcp/config/openroad_error_patterns.txt",
        help="Output file path",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print patterns without writing file")
    parser.add_argument("--keep-clone", action="store_true", help="Keep cloned repository after extraction")

    args = parser.parse_args()

    print(f"Extracting error patterns from source: {args.source}")

    all_patterns = []
    temp_dir = None

    try:
        if args.source == "docs":
            all_patterns.extend(scrape_openroad_docs())

        elif args.source == "github":
            if args.clone_dir:
                clone_dir = args.clone_dir
            else:
                temp_dir = tempfile.mkdtemp(prefix="openroad_")
                clone_dir = Path(temp_dir)

            if clone_openroad_repo(clone_dir):
                all_patterns.extend(scrape_openroad_docs())
                all_patterns.extend(scrape_source_code(clone_dir))
                all_patterns.extend(extract_patterns_from_tcl_source(clone_dir))

        elif args.source == "local":
            if not args.repo_path:
                print("Error: --repo-path required for --source local")
                return 1

            if not args.repo_path.exists():
                print(f"Error: Repository path does not exist: {args.repo_path}")
                return 1

            all_patterns.extend(scrape_openroad_docs())
            all_patterns.extend(scrape_source_code(args.repo_path))
            all_patterns.extend(extract_patterns_from_tcl_source(args.repo_path))

        all_patterns = deduplicate_patterns(all_patterns)

        print(f"Extracted {len(all_patterns)} unique patterns")

        if args.dry_run:
            print("\n=== Pattern Preview ===")
            for regex, message, category in all_patterns[:50]:
                print(f"[{category:10}] {regex[:60]:60} -> {message[:40]}")
            if len(all_patterns) > 50:
                print(f"... and {len(all_patterns) - 50} more patterns")
        else:
            write_patterns_file(all_patterns, args.output)
            print(f"✓ Written to: {args.output}")

        print("\nPattern distribution:")
        categories = {}
        for _, _, category in all_patterns:
            categories[category] = categories.get(category, 0) + 1
        for cat, count in sorted(categories.items()):
            print(f"  {cat:12}: {count:3} patterns")

    finally:
        if temp_dir and not args.keep_clone:
            print(f"\nCleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    exit(main())
