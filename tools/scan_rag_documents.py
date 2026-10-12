import os
import re


GOVERNMENT_FOLDER = "documents/government"


# Words/phrases that should NOT normally appear
# in a government startup-policy document.
SUSPICIOUS_PATTERNS = [
    r"casino",
    r"gambling",
    r"slots",
    r"poker",
    r"sabung ayam",
    r"togel",
    r"jackpot",
    r"winrate",
    r"online game",
    r"game online",
    r"telegram",
    r"daftar id",
    r"server luar negeri",
    r"hot games",
    r"live casino",
    r"crash game",
    r"dragon222",
]


def scan_file(filepath):

    with open(
        filepath,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as file:
        text = file.read()

    matches = []

    for pattern in SUSPICIOUS_PATTERNS:

        found = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if found:
            matches.append(
                pattern.replace("\\", "")
            )

    return matches, text


def main():

    print("\n========================================")
    print("RAG DOCUMENT SECURITY / QUALITY SCAN")
    print("========================================")

    files = sorted(
        file
        for file in os.listdir(GOVERNMENT_FOLDER)
        if file.endswith(".txt")
    )

    print(f"\nDocuments found: {len(files)}")

    suspicious_files = []

    for filename in files:

        filepath = os.path.join(
            GOVERNMENT_FOLDER,
            filename
        )

        matches, text = scan_file(filepath)

        print("\n----------------------------------------")
        print(filename)
        print("----------------------------------------")

        print(
            f"Characters: {len(text):,}"
        )

        if matches:

            print("⚠️ SUSPICIOUS CONTENT FOUND")

            for match in matches:
                print(f"  - {match}")

            suspicious_files.append(
                {
                    "filename": filename,
                    "matches": matches
                }
            )

        else:

            print("✓ No suspicious patterns found")

    print("\n========================================")
    print("SCAN SUMMARY")
    print("========================================")

    print(
        f"Total documents: {len(files)}"
    )

    print(
        f"Suspicious documents: "
        f"{len(suspicious_files)}"
    )

    if suspicious_files:

        print("\nFiles requiring inspection:")

        for item in suspicious_files:

            print(
                f"\n{item['filename']}"
            )

            print(
                "Patterns:",
                ", ".join(item["matches"])
            )

    else:

        print(
            "\n✓ No suspicious documents detected."
        )


if __name__ == "__main__":
    main()