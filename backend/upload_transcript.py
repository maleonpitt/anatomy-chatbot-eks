#!/usr/bin/env python3
"""
Video Transcript Uploader for Anatomy Chatbot
----------------------------------------------
Parses SRT/caption files and uploads to Pinecone with timestamp metadata.

Usage:
    python upload_transcript.py <transcript_file.txt>
    python upload_transcript.py <transcript_file.txt> --chunk-duration 45

Example:
    python upload_transcript.py "PT_2030_Flexor_Region.txt"
"""

import os
import re
import sys
import argparse
from dotenv import load_dotenv
from pinecone import Pinecone as PineconeClient
from langchain_openai import OpenAIEmbeddings

# Load environment variables
env_file = ".env.production" if os.getenv("FLASK_ENV") == "production" else ".env"
load_dotenv(env_file)

# === Configuration ===
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

# Initialize clients
pc = PineconeClient(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")


def parse_timestamp(ts_str):
    """Convert timestamp string to seconds. Handles both HH:MM:SS,ms and MM:SS,ms formats."""
    ts_str = ts_str.replace(",", ".")
    parts = ts_str.split(":")

    if len(parts) == 3:  # HH:MM:SS.ms
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    elif len(parts) == 2:  # MM:SS.ms
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    else:
        return 0


def format_timestamp(seconds):
    """Convert seconds to MM:SS format for display."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def parse_srt_file(filepath):
    """
    Parse an SRT/caption file and return a list of caption entries.
    Each entry: {'index': int, 'start': float, 'end': float, 'text': str}
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by double newlines (caption blocks)
    blocks = re.split(r"\n\n+", content.strip())

    captions = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        # First line is index
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue

        # Second line is timestamp
        timestamp_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d+)\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d+)", lines[1]
        )
        if not timestamp_match:
            continue

        start_time = parse_timestamp(timestamp_match.group(1))
        end_time = parse_timestamp(timestamp_match.group(2))

        # Rest is text (may span multiple lines)
        text = " ".join(lines[2:]).strip()

        # Skip empty or music-only entries
        if not text or text in [">> [MUSIC]", "[MUSIC]"]:
            continue

        # Clean up text
        text = re.sub(r">>\s*", "", text)  # Remove >> markers
        text = re.sub(r"\s+", " ", text)  # Normalize whitespace

        captions.append(
            {"index": idx, "start": start_time, "end": end_time, "text": text}
        )

    return captions


def extract_video_title(filename):
    """Extract a clean video title from the filename."""
    # Remove extension
    name = os.path.splitext(os.path.basename(filename))[0]

    # Remove common suffixes
    name = re.sub(r"_Captions.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_English.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_United_States.*$", "", name, flags=re.IGNORECASE)

    # Replace underscores with spaces
    name = name.replace("_", " ")

    # Clean up multiple spaces and dashes
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"\s*-\s*", " - ", name)

    # Remove PT 2030 prefix if present (course code)
    name = re.sub(r"^PT\s*\d+\s*[-_]?\s*", "", name)

    # Remove "Gross Anatomy" prefix if redundant
    name = re.sub(r"^Gross Anatomy\s*[-_]?\s*", "", name)

    return name.strip()


def chunk_captions(captions, target_duration=30):
    """
    Group captions into chunks of approximately target_duration seconds.
    Returns list of chunks with combined text and time ranges.
    """
    if not captions:
        return []

    chunks = []
    current_chunk = {
        "texts": [],
        "start": captions[0]["start"],
        "end": captions[0]["end"],
    }

    for caption in captions:
        chunk_duration = current_chunk["end"] - current_chunk["start"]

        # If adding this caption would exceed target duration AND we have some content
        if chunk_duration >= target_duration and current_chunk["texts"]:
            # Save current chunk
            chunks.append(
                {
                    "text": " ".join(current_chunk["texts"]),
                    "start": current_chunk["start"],
                    "end": current_chunk["end"],
                }
            )
            # Start new chunk
            current_chunk = {
                "texts": [caption["text"]],
                "start": caption["start"],
                "end": caption["end"],
            }
        else:
            # Add to current chunk
            current_chunk["texts"].append(caption["text"])
            current_chunk["end"] = caption["end"]

    # Don't forget the last chunk
    if current_chunk["texts"]:
        chunks.append(
            {
                "text": " ".join(current_chunk["texts"]),
                "start": current_chunk["start"],
                "end": current_chunk["end"],
            }
        )

    return chunks


def upload_to_pinecone(chunks, video_title, filename):
    """Embed and upload chunks to Pinecone with metadata."""
    print(f"\n📤 Uploading {len(chunks)} chunks to Pinecone...")

    # Prepare texts for embedding
    texts = [chunk["text"] for chunk in chunks]

    print("🔄 Generating embeddings...")
    vectors = embeddings.embed_documents(texts)

    # Create upsert data with metadata
    upserts = []
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        # Create a unique ID
        safe_filename = re.sub(r"[^a-zA-Z0-9]", "_", filename)[:50]
        chunk_id = f"transcript-{safe_filename}-{i}"

        upserts.append(
            {
                "id": chunk_id,
                "values": vector,
                "metadata": {
                    "text": chunk["text"],
                    "start_time": format_timestamp(chunk["start"]),
                    "end_time": format_timestamp(chunk["end"]),
                    "start_seconds": chunk["start"],
                    "end_seconds": chunk["end"],
                    "video_title": video_title,
                    "source_type": "video_transcript",
                    "source_file": filename,
                },
            }
        )

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(upserts), batch_size):
        batch = upserts[i : i + batch_size]
        index.upsert(vectors=batch)
        print(
            f"  ✅ Uploaded batch {i // batch_size + 1}/{(len(upserts) - 1) // batch_size + 1}"
        )

    print(f"\n✅ Successfully uploaded {len(chunks)} chunks for '{video_title}'")
    return len(chunks)


def main():
    parser = argparse.ArgumentParser(
        description="Upload video transcript to Pinecone with timestamp metadata"
    )
    parser.add_argument("transcript_file", help="Path to the SRT/caption file")
    parser.add_argument(
        "--chunk-duration",
        type=int,
        default=30,
        help="Target duration in seconds for each chunk (default: 30)",
    )
    parser.add_argument(
        "--video-title",
        type=str,
        default=None,
        help="Custom video title (default: extracted from filename)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Parse and show chunks without uploading"
    )

    args = parser.parse_args()

    # Check file exists
    if not os.path.exists(args.transcript_file):
        print(f"❌ Error: File not found: {args.transcript_file}")
        sys.exit(1)

    print(f"📂 Processing: {args.transcript_file}")

    # Extract video title
    video_title = args.video_title or extract_video_title(args.transcript_file)
    print(f"🎬 Video title: {video_title}")

    # Parse the file
    print("📝 Parsing captions...")
    captions = parse_srt_file(args.transcript_file)
    print(f"   Found {len(captions)} caption entries")

    if not captions:
        print("❌ Error: No captions found in file")
        sys.exit(1)

    # Chunk the captions
    print(f"📦 Chunking with target duration: {args.chunk_duration}s")
    chunks = chunk_captions(captions, target_duration=args.chunk_duration)
    print(f"   Created {len(chunks)} chunks")

    # Show preview
    print("\n--- Preview of first 3 chunks ---")
    for i, chunk in enumerate(chunks[:3]):
        print(f"\nChunk {i + 1}:")
        print(
            f"  Time: {format_timestamp(chunk['start'])} - {format_timestamp(chunk['end'])}"
        )
        print(f"  Text: {chunk['text'][:150]}...")
    print("-----------------------------------\n")

    if args.dry_run:
        print("🔍 Dry run complete. No data uploaded.")
        return

    # Upload to Pinecone
    filename = os.path.basename(args.transcript_file)
    upload_to_pinecone(chunks, video_title, filename)

    print("\n🎉 Done! Students can now ask about timestamps in this video.")
    print(
        f"   Example query: 'Where in the video can I see the coracobrachialis muscle?'"
    )


if __name__ == "__main__":
    main()
