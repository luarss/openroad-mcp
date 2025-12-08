#!/usr/bin/env python3
"""
Generate subtitles for long videos by processing in chunks.

This script splits the video into time-based chunks and generates subtitles
for each chunk separately, then merges them into a complete subtitle file.

Usage:
    python generate_subtitles_chunked.py video.mp4 --chunk-duration 60
"""

import argparse
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai

load_dotenv()


@dataclass
class SubtitleEntry:
    """Represents a single subtitle entry."""

    index: int
    start_time: str  # Format: HH:MM:SS,mmm
    end_time: str
    text: str


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS,mmm format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def timestamp_to_seconds(timestamp: str) -> float:
    """Convert HH:MM:SS,mmm timestamp to seconds."""
    timestamp = timestamp.replace(",", ".")
    parts = timestamp.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def generate_chunk_subtitles(
    client: genai.Client, video_file: Any, start_time: float, end_time: float, language: str = "English"
) -> list[SubtitleEntry]:
    """Generate subtitles for a specific time chunk of the video."""
    start_ts = seconds_to_timestamp(start_time)
    end_ts = seconds_to_timestamp(end_time)

    prompt = f"""Analyze this video from timestamp {start_ts} to {end_ts} and generate concise \
narration-style subtitles in {language}.

CRITICAL: Only generate subtitles for the time range {start_ts} to {end_ts}.

For each subtitle:
1. Start timestamp (HH:MM:SS.mmm format, must be between {start_ts} and {end_ts})
2. End timestamp (HH:MM:SS.mmm format, must be between {start_ts} and {end_ts})
3. Concise narration (10-15 words max)

Guidelines:
- Active voice, present tense
- 3-5 second subtitle duration
- Specific UI elements and actions
- Keep it concise

Format:

[1]
{start_ts} --> HH:MM:SS.mmm
Brief description of what happens.

[2]
HH:MM:SS.mmm --> HH:MM:SS.mmm
Next action description.

Generate subtitles ONLY for the specified time range {start_ts} to {end_ts}.
"""

    response = client.models.generate_content(model="gemini-2.0-flash", contents=[video_file, prompt])

    if not response.text:
        return []

    # Parse subtitles
    return parse_subtitle_response(response.text, start_time)


def parse_subtitle_response(response_text: str, offset_seconds: float = 0) -> list[SubtitleEntry]:
    """Parse Gemini's response into subtitle entries."""
    subtitles = []

    pattern = (
        r"\[(\d+)\]\s*\n\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*"
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*\n\s*(.+?)(?=\n\n|\n\[|\Z)"
    )
    matches = re.finditer(pattern, response_text, re.DOTALL | re.MULTILINE)

    for match in matches:
        start_time = match.group(2).replace(".", ",")
        end_time = match.group(3).replace(".", ",")
        text = match.group(4).strip()

        # Only include subtitles that are reasonably within the expected time range
        start_secs = timestamp_to_seconds(start_time)
        if abs(start_secs - offset_seconds) < 120:  # Within 2 minutes of expected offset
            subtitles.append(
                SubtitleEntry(index=0, start_time=start_time, end_time=end_time, text=text)  # Will renumber later
            )

    # Fallback parsing if numbered format fails
    if not subtitles:
        timestamp_pattern = (
            r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*\n\s*(.+?)(?=\n\d{2}:|\Z)"
        )
        matches = re.finditer(timestamp_pattern, response_text, re.DOTALL | re.MULTILINE)

        for match in matches:
            start_time = match.group(1).replace(".", ",")
            end_time = match.group(2).replace(".", ",")
            text = match.group(3).strip()

            start_secs = timestamp_to_seconds(start_time)
            if abs(start_secs - offset_seconds) < 120:
                subtitles.append(SubtitleEntry(index=0, start_time=start_time, end_time=end_time, text=text))

    return subtitles


def save_srt(subtitles: list[SubtitleEntry], output_path: str) -> None:
    """Save subtitles in SRT format."""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, sub in enumerate(subtitles, 1):
            f.write(f"{i}\n")
            f.write(f"{sub.start_time} --> {sub.end_time}\n")
            f.write(f"{sub.text}\n\n")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate subtitles for long videos by processing in chunks")
    parser.add_argument("video_path", help="Path to video file")
    parser.add_argument(
        "--chunk-duration", "-c", type=int, default=60, help="Duration of each chunk in seconds (default: 60)"
    )
    parser.add_argument("--output", "-o", help="Output SRT file path")
    parser.add_argument("--language", "-l", default="English", help="Subtitle language (default: English)")

    args = parser.parse_args()

    video_path = Path(args.video_path)
    if not video_path.exists():
        print(f"Error: Video not found: {args.video_path}")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set")
        return

    # Get video duration
    print(f"📹 Analyzing video: {video_path}")
    duration = get_video_duration(str(video_path))
    print(f"✓ Video duration: {duration:.1f} seconds ({duration / 60:.1f} minutes)")

    # Calculate chunks
    chunk_duration = args.chunk_duration
    num_chunks = int(duration // chunk_duration) + (1 if duration % chunk_duration > 0 else 0)
    print(f"📊 Processing in {num_chunks} chunks of {chunk_duration}s each")

    # Upload video once
    client = genai.Client(api_key=api_key)
    print("\n⬆️  Uploading video...")
    video_file = client.files.upload(file=str(video_path))
    print(f"✓ Upload complete: {video_file.uri}")

    # Wait for processing
    if video_file.name:
        print("⏳ Processing video...")
        while video_file.state and video_file.state.name != "ACTIVE":
            time.sleep(2)
            video_file = client.files.get(name=video_file.name)
        print("✓ Video ready")

    # Generate subtitles for each chunk
    all_subtitles = []

    for i in range(num_chunks):
        start_time = i * chunk_duration
        end_time = min((i + 1) * chunk_duration, duration)

        print(f"\n🎬 Chunk {i + 1}/{num_chunks}: {seconds_to_timestamp(start_time)} → {seconds_to_timestamp(end_time)}")

        chunk_subs = generate_chunk_subtitles(client, video_file, start_time, end_time, args.language)

        if chunk_subs:
            print(f"   ✓ Generated {len(chunk_subs)} subtitles")
            all_subtitles.extend(chunk_subs)
        else:
            print("   ⚠ No subtitles generated for this chunk")

        # Small delay to avoid rate limits
        if i < num_chunks - 1:
            time.sleep(1)

    # Sort and renumber subtitles
    all_subtitles.sort(key=lambda s: timestamp_to_seconds(s.start_time))
    for i, sub in enumerate(all_subtitles, 1):
        sub.index = i

    # Save output
    output_path = args.output or f"{video_path.stem}_subtitles.srt"
    save_srt(all_subtitles, output_path)

    print(f"\n{'=' * 60}")
    print("✅ Complete!")
    print(f"📝 Generated {len(all_subtitles)} total subtitles")
    print(f"💾 Saved to: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
