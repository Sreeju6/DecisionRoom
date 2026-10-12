import re

FILE = "documents/government/Karnataka_startup_policy.txt"


def clean_karnataka():

    with open(
        FILE,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        text = f.read()

    original_length = len(text)

    print("Original characters:", original_length)

    # The injected content starts at DRAGON222
    # and ends at the timestamp immediately before
    # the legitimate/irrelevant page continuation.
    #
    # We remove only the clearly injected block.

    pattern = r"""
        DRAGON222
        .*?
        Jum,\s*12-Jun-2026\s*15\.17\.18
        .*?
        Live Jackpot
        .*?
        Celengan Naga
    """

    cleaned = re.sub(
        pattern,
        "",
        text,
        flags=re.IGNORECASE |
              re.DOTALL |
              re.VERBOSE
    )

    # Remove excessive blank lines created by deletion.
    cleaned = re.sub(
        r"\n\s*\n\s*\n+",
        "\n\n",
        cleaned
    )

    cleaned = cleaned.strip()

    with open(
        FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(cleaned)

    print("\n========================================")
    print("KARNATAKA DOCUMENT CLEANED")
    print("========================================")

    print(
        f"Original characters: {original_length:,}"
    )

    print(
        f"Cleaned characters: {len(cleaned):,}"
    )

    print(
        f"Removed characters: "
        f"{original_length - len(cleaned):,}"
    )

    print(
        "\nSaved:",
        FILE
    )


if __name__ == "__main__":
    clean_karnataka()