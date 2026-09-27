#!/usr/bin/env python3
"""Deterministically turn a word-level transcript into clips.json candidates."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Sequence


DEFAULT_MIN_DURATION = 15.0
DEFAULT_MAX_DURATION = 55.0
_ENDING_RE = re.compile(r"[.!?][\"')\]]*$")
_HOOK_TERMS = {
    "actually",
    "hidden",
    "how",
    "mistake",
    "never",
    "nobody",
    "secret",
    "truth",
    "why",
}


def _valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _word_list(transcript: Any) -> List[Dict[str, Any]]:
    """Return validated words from the upstream transcript shape, or [] if invalid."""
    if not isinstance(transcript, dict):
        return []

    raw_words = transcript.get("words")
    if not isinstance(raw_words, list) or not raw_words:
        raw_words = []
        for segment in transcript.get("segments", []):
            if not isinstance(segment, dict) or not isinstance(segment.get("words"), list):
                return []
            raw_words.extend(segment["words"])

    words: List[Dict[str, Any]] = []
    for word in raw_words:
        if not isinstance(word, dict):
            return []
        text = word.get("word")
        start = word.get("start")
        end = word.get("end")
        if (
            not isinstance(text, str)
            or not text.strip()
            or not _valid_number(start)
            or not _valid_number(end)
            or start < 0
            or end <= start
        ):
            return []
        words.append({"word": text.strip(), "start": float(start), "end": float(end)})

    return sorted(words, key=lambda item: (item["start"], item["end"]))


def load_transcript(path: str) -> List[Dict[str, Any]]:
    """Read an upstream transcript; malformed or missing input yields no words."""
    try:
        with open(path, encoding="utf-8") as transcript_file:
            return _word_list(json.load(transcript_file))
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def _is_sentence_end(word: str) -> bool:
    return bool(_ENDING_RE.search(word))


def _clip_score(words: Sequence[Dict[str, Any]]) -> int:
    text = " ".join(word["word"] for word in words)
    lower_words = {
        word["word"].lower().strip(".,!?;:()[]{}\"'") for word in words
    }

    score = 60
    score += 10 if lower_words & _HOOK_TERMS else 0
    score += 5 if any(char.isdigit() for char in text) else 0
    score += 4 if "?" in text or "!" in text else 0
    score += 5 if len(words) >= 20 else 0
    return max(0, min(100, score))


def _phrase(words: Sequence[Dict[str, Any]], limit: int) -> str:
    phrase = " ".join(word["word"] for word in words[:limit]).strip()
    return phrase if len(phrase) <= 72 else phrase[:69].rstrip() + "..."


def select_candidates(
    words: Sequence[Dict[str, Any]],
    min_duration: float = DEFAULT_MIN_DURATION,
    max_duration: float = DEFAULT_MAX_DURATION,
    max_clips: int = 8,
) -> List[Dict[str, Any]]:
    """Select non-overlapping sentence-aware windows with downstream timings."""
    if (
        not words
        or min_duration <= 0
        or max_duration < min_duration
        or max_clips <= 0
    ):
        return []

    candidates: List[Dict[str, Any]] = []
    cursor = 0
    while cursor < len(words) and len(candidates) < max_clips:
        start = words[cursor]["start"]
        latest_end = start + max_duration
        eligible = [
            index
            for index in range(cursor, len(words))
            if words[index]["end"] <= latest_end + 1e-9
        ]
        if not eligible:
            break

        minimum_end = start + min_duration
        sentence_ends = [
            index for index in eligible
            if words[index]["end"] >= minimum_end and _is_sentence_end(words[index]["word"])
        ]
        if sentence_ends:
            end_index = sentence_ends[-1]
        else:
            long_enough = [index for index in eligible if words[index]["end"] >= minimum_end]
            if not long_enough:
                break
            end_index = long_enough[0]

        clip_words = words[cursor : end_index + 1]
        end = clip_words[-1]["end"]
        duration = end - start
        if duration < min_duration or duration > max_duration:
            break

        hook = _phrase(clip_words, 8)
        candidates.append(
            {
                "id": f"{len(candidates) + 1:02d}",
                "title": _phrase(clip_words, 6),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
                "score": _clip_score(clip_words),
                "hook": hook,
            }
        )
        cursor = end_index + 1

    return candidates


def build_clips_json(
    transcript: Any,
    source: str = "source.mp4",
    min_duration: float = DEFAULT_MIN_DURATION,
    max_duration: float = DEFAULT_MAX_DURATION,
) -> Dict[str, Any]:
    """Build the exact clips.json envelope consumed by the upstream engine."""
    words = _word_list(transcript)
    return {
        "source": source,
        "clips": select_candidates(words, min_duration, max_duration),
        "caption_style": "none",
        "platform": "all",
    }


def write_clips_json(data: Dict[str, Any], path: str) -> None:
    """Write a manifest atomically so downstream never sees a partial JSON file."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as output_file:
        json.dump(data, output_file, indent=2)
        output_file.write("\n")
    os.replace(temporary_path, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select deterministic clip candidates")
    parser.add_argument("transcript", nargs="?", default="transcript.json")
    parser.add_argument("--output", default="clips.json")
    parser.add_argument("--source", default="source.mp4")
    parser.add_argument("--min-duration", type=float, default=DEFAULT_MIN_DURATION)
    parser.add_argument("--max-duration", type=float, default=DEFAULT_MAX_DURATION)
    args = parser.parse_args()

    words = load_transcript(args.transcript)
    data = {
        "source": args.source,
        "clips": select_candidates(words, args.min_duration, args.max_duration),
        "caption_style": "none",
        "platform": "all",
    }
    write_clips_json(data, args.output)
    print(f"Wrote {len(data['clips'])} clip candidates to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())