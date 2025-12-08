#!/usr/bin/env python3
"""
Burn subtitles into video using ffmpeg

This script uses ffmpeg to permanently embed subtitles into a video file.
The subtitles will be rendered as part of the video (hardcoded).

Requirements:
- ffmpeg installed and available in PATH
- SRT subtitle file

Usage:
    python burn_subtitles.py video.mkv subtitles.srt
    python burn_subtitles.py video.mkv subtitles.srt --output output.mp4
    python burn_subtitles.py video.mkv subtitles.srt --font-size 24 --font-color yellow
"""

import argparse
import shutil
import subprocess
from pathlib import Path


def check_ffmpeg() -> bool:
    """Check if ffmpeg is installed."""
    return shutil.which("ffmpeg") is not None


def burn_subtitles(
    video_path: str,
    subtitle_path: str,
    output_path: str | None = None,
    font_size: int = 20,
    font_color: str = "white",
    font_name: str = "Arial",
    position: str = "bottom",
) -> str:
    """
    Burn subtitles into video using ffmpeg.

    Args:
        video_path: Path to input video
        subtitle_path: Path to SRT subtitle file
        output_path: Path to output video (optional)
        font_size: Subtitle font size
        font_color: Subtitle font color
        font_name: Font name
        position: Subtitle position ('bottom', 'top', 'center')

    Returns:
        Path to output video
    """
    video = Path(video_path)
    subtitle = Path(subtitle_path)

    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not subtitle.exists():
        raise FileNotFoundError(f"Subtitle not found: {subtitle_path}")

    # Generate output path if not provided
    if output_path is None:
        output_path = f"{video.stem}_with_subs{video.suffix}"

    output = Path(output_path)

    # Build ffmpeg command
    # Use subtitles filter to burn in the SRT
    subtitle_filter = (
        f"subtitles='{subtitle.absolute()}':force_style='FontName={font_name},"
        f"FontSize={font_size},PrimaryColour=&H{_color_to_hex(font_color)}"
    )

    # Add position
    if position == "top":
        subtitle_filter += ",Alignment=8"  # Top center
    elif position == "center":
        subtitle_filter += ",Alignment=5"  # Center
    else:  # bottom
        subtitle_filter += ",Alignment=2"  # Bottom center

    subtitle_filter += "'"

    cmd = [
        "ffmpeg",
        "-i",
        str(video.absolute()),
        "-vf",
        subtitle_filter,
        "-c:a",
        "copy",  # Copy audio without re-encoding
        "-y",  # Overwrite output file if exists
        str(output.absolute()),
    ]

    print("🎬 Burning subtitles into video...")
    print(f"   Input video: {video}")
    print(f"   Subtitles: {subtitle}")
    print(f"   Output: {output}")
    print(f"   Font: {font_name}, Size: {font_size}, Color: {font_color}")
    print()

    # Run ffmpeg
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ Subtitles burned successfully!")
        print(f"📹 Output saved to: {output}")
        return str(output.absolute())

    except subprocess.CalledProcessError as e:
        print("❌ ffmpeg error:")
        print(e.stderr)
        raise


def _color_to_hex(color: str) -> str:
    """Convert color name to ASSA hex format (BGR)."""
    colors = {
        "white": "FFFFFF",
        "black": "000000",
        "red": "0000FF",
        "green": "00FF00",
        "blue": "FF0000",
        "yellow": "00FFFF",
        "cyan": "FFFF00",
        "magenta": "FF00FF",
    }
    return colors.get(color.lower(), "FFFFFF")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Burn SRT subtitles into video using ffmpeg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - burn subtitles with default settings
  %(prog)s video.mkv subtitles.srt

  # Specify custom output file
  %(prog)s video.mkv subtitles.srt --output final_video.mp4

  # Customize appearance
  %(prog)s video.mkv subtitles.srt --font-size 24 --font-color yellow

  # Position subtitles at the top
  %(prog)s video.mkv subtitles.srt --position top

Note: This process re-encodes the video, which may take time for large files.
      Audio is copied without re-encoding to save time.
        """,
    )

    parser.add_argument("video_path", help="Path to input video file")
    parser.add_argument("subtitle_path", help="Path to SRT subtitle file")
    parser.add_argument("--output", "-o", help="Output video path (default: video_with_subs.ext)")
    parser.add_argument("--font-size", type=int, default=20, help="Subtitle font size (default: 20)")
    parser.add_argument(
        "--font-color",
        choices=["white", "black", "red", "green", "blue", "yellow", "cyan", "magenta"],
        default="white",
        help="Subtitle font color (default: white)",
    )
    parser.add_argument("--font-name", default="Arial", help="Font name (default: Arial)")
    parser.add_argument(
        "--position", choices=["bottom", "top", "center"], default="bottom", help="Subtitle position (default: bottom)"
    )

    args = parser.parse_args()

    # Check ffmpeg
    if not check_ffmpeg():
        print("❌ Error: ffmpeg is not installed or not in PATH")
        print("Install ffmpeg:")
        print("  Ubuntu/Debian: sudo apt install ffmpeg")
        print("  macOS: brew install ffmpeg")
        print("  Or download from: https://ffmpeg.org/download.html")
        return

    try:
        output = burn_subtitles(
            args.video_path,
            args.subtitle_path,
            args.output,
            args.font_size,
            args.font_color,
            args.font_name,
            args.position,
        )

        print()
        print("=" * 60)
        print("✅ Done!")
        print(f"📹 Video with burned subtitles: {output}")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
