import os
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_FILE = "data/raw/government_sources.csv"

OUTPUT_FOLDER = "documents/government"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36"
    )
}


# ============================================================
# CREATE OUTPUT FOLDER
# ============================================================

os.makedirs(
    OUTPUT_FOLDER,
    exist_ok=True
)


# ============================================================
# CLEAN FILE NAME
# ============================================================

def clean_filename(name):
    """
    Convert a state name into a safe file name.
    """

    name = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        name
    )

    return name.strip("_")


# ============================================================
# DOWNLOAD AND EXTRACT PAGE TEXT
# ============================================================

def collect_source(state, source_name, url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        status = response.status_code

        if status != 200:

            return {
                "State_UT": state,
                "URL": url,
                "Status": f"HTTP {status}",
                "Saved_File": ""
            }

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # Remove elements that usually contain
        # navigation or unnecessary page content
        for element in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header"
            ]
        ):
            element.decompose()

        text = soup.get_text(
            separator="\n"
        )

        # Clean blank lines
        lines = []

        for line in text.splitlines():

            line = line.strip()

            if line:
                lines.append(line)

        text = "\n".join(lines)

        if len(text) < 200:

            return {
                "State_UT": state,
                "URL": url,
                "Status": "No useful text",
                "Saved_File": ""
            }

        filename = (
            clean_filename(state)
            + "_startup_policy.txt"
        )

        output_path = os.path.join(
            OUTPUT_FOLDER,
            filename
        )

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                f"State/UT: {state}\n"
            )

            file.write(
                f"Source: {source_name}\n"
            )

            file.write(
                f"URL: {url}\n\n"
            )

            file.write(
                text
            )

        return {
            "State_UT": state,
            "URL": url,
            "Status": "Downloaded",
            "Saved_File": output_path
        }

    except Exception as error:

        return {
            "State_UT": state,
            "URL": url,
            "Status": f"ERROR: {error}",
            "Saved_File": ""
        }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "\n========== GOVERNMENT SOURCE COLLECTION =========="
    )

    df = pd.read_csv(
        SOURCE_FILE
    )

    results = []

    for _, row in df.iterrows():

        state = row["State_UT"]
        source_name = row["Source_Name"]
        url = row["Source_URL"]

        print(
            f"\nCollecting: {state}"
        )

        print(
            f"URL: {url}"
        )

        result = collect_source(
            state,
            source_name,
            url
        )

        results.append(
            result
        )

        print(
            f"Status: {result['Status']}"
        )

        # Avoid sending requests too quickly
        time.sleep(1)


    # --------------------------------------------------------
    # SAVE COLLECTION REPORT
    # --------------------------------------------------------

    report = pd.DataFrame(
        results
    )

    report_file = (
        "data/processed/"
        "government_collection_report.csv"
    )

    os.makedirs(
        "data/processed",
        exist_ok=True
    )

    report.to_csv(
        report_file,
        index=False
    )

    print(
        "\n========== COLLECTION SUMMARY =========="
    )

    print(
        report["Status"]
        .value_counts()
        .to_string()
    )

    print(
        "\nReport saved to:"
    )

    print(
        report_file
    )