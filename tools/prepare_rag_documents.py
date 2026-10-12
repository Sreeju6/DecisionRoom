
import os
import re
import json

DOCUMENT_FOLDER = "documents/government"
OUTPUT_FOLDER = "data/processed"
OUTPUT_FILE = os.path.join(OUTPUT_FOLDER, "rag_documents.json")

NOISE_PATTERNS = [
    r"^screen reader access$",
    r"^a\+?$",
    r"^a-$",
    r"^english$",
    r"^telugu$",
    r"^hindi$",
    r"^kannada$",
    r"^malayalam$",
    r"^tamil$",
    r"^marathi$",
    r"^gujarati$",
    r"^odia$",
    r"^bengali$",
    r"^assamese$",
    r"^login$",
    r"^sign in$",
    r"^sign up$",
    r"^home$",
    r"^contact us$",
    r"^privacy policy$",
    r"^terms and conditions$",
    r"^copyright$",
    r"^skip to main content$",
    r"^search$",
    r"^menu$",
    r"^navigation$",
    r"^view application process$",
    r"^read more$",
    r"^learn more$",
    r"^click here$",
    r"^explore our latest initiatives$",
]


def is_noise_line(line):
    """Return True if a line is a known navigation or website-noise item."""
    cleaned = line.strip().lower()

    if not cleaned:
        return False

    for pattern in NOISE_PATTERNS:
        if re.match(pattern, cleaned):
            return True

    return False


def remove_source_metadata(text):
    """
    Remove internal RAG notes and primary-directory links without
    deleting substantive evidence or current-policy cautions.

    Recognized section headings are used as boundaries. This avoids
    removing all content that follows an internal metadata heading.
    """

    # Remove the RAG USE NOTE section only, stopping at the next
    # recognized uppercase section heading or the end of the file.
    text = re.sub(
        r"(?ims)^RAG USE NOTE[ \t]*\n.*?"
        r"(?=^[A-Z][A-Z /()-]*[ \t]*$|\Z)",
        "",
        text,
    )

    # Remove the PRIMARY DIRECTORY heading and its URL.
    # Do not remove any earlier evidence or caution sections.
    text = re.sub(
        r"(?im)^PRIMARY DIRECTORY[ \t]*\n"
        r"(?:[ \t]*https?://\S+[ \t]*\n?)?",
        "",
        text,
    )

    return text


def clean_text(text):
    """Normalize text and remove known navigation noise."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text = remove_source_metadata(text)

    cleaned_lines = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        if is_noise_line(line):
            continue

        line = re.sub(r"[ \t]+", " ", line)
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_into_chunks(text, chunk_size=1200, overlap=200):
    """Split cleaned text into overlapping chunks."""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end]

        if end < text_length:
            last_period = chunk.rfind(". ")
            last_newline = chunk.rfind("\n")
            boundary = max(last_period, last_newline)

            # Prefer a natural boundary when it is not too early.
            if boundary > chunk_size * 0.6:
                end = start + boundary + 1
                chunk = text[start:end]

        chunk = chunk.strip()

        if chunk:
            chunks.append(chunk)

        next_start = end - overlap

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


def prepare_documents():
    print("\n========== RAG DOCUMENT PREPARATION ==========")

    if not os.path.exists(DOCUMENT_FOLDER):
        print(f"ERROR: Government document folder not found: {DOCUMENT_FOLDER}")
        return

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    files = sorted(
        filename
        for filename in os.listdir(DOCUMENT_FOLDER)
        if filename.lower().endswith(".txt")
    )

    print(f"\nDocuments found: {len(files)}")

    all_chunks = []
    document_count = 0
    skipped_count = 0
    error_count = 0

    for filename in files:
        file_path = os.path.join(DOCUMENT_FOLDER, filename)

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                original_text = file.read()

            original_characters = len(original_text)
            cleaned_text = clean_text(original_text)
            cleaned_characters = len(cleaned_text)

            if not cleaned_text:
                print(f"SKIPPED: {filename} (empty after cleaning)")
                skipped_count += 1
                continue

            chunks = split_into_chunks(cleaned_text)

            document_count += 1

            removed = original_characters - cleaned_characters

            print(
                f"Processed: {filename} | "
                f"Original: {original_characters} | "
                f"Cleaned: {cleaned_characters} | "
                f"Removed: {removed} | "
                f"Chunks: {len(chunks)}"
            )

            for chunk_number, chunk in enumerate(chunks, start=1):
                all_chunks.append(
                    {
                        "chunk_id": len(all_chunks),
                        "document": filename,
                        "chunk_number": chunk_number,
                        "text": chunk,
                    }
                )

        except Exception as error:
            error_count += 1
            print(f"ERROR processing {filename}: {error}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(all_chunks, file, ensure_ascii=False, indent=2)

    print("\n========== PREPARATION SUMMARY ==========")
    print(f"Documents processed: {document_count}")
    print(f"Documents skipped: {skipped_count}")
    print(f"Processing errors: {error_count}")
    print(f"Total clean chunks: {len(all_chunks)}")
    print(f"Output file: {OUTPUT_FILE}")


if __name__ == "__main__":
    prepare_documents()
