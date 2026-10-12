import os
import requests
from pypdf import PdfReader

PDF_URL = "https://abvil.jharkhand.gov.in/documents/Policy2023.pdf"

PDF_FILE = "data/raw/Jharkhand_Startup_Policy_2023.pdf"
TEXT_FILE = "documents/government/Jharkhand_startup_policy.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def download_pdf():

    print("\n========== DOWNLOADING JHARKHAND POLICY ==========")

    os.makedirs("data/raw", exist_ok=True)

    response = requests.get(
        PDF_URL,
        headers=HEADERS,
        timeout=60
    )

    print("HTTP Status:", response.status_code)
    print("Downloaded bytes:", len(response.content))

    response.raise_for_status()

    with open(PDF_FILE, "wb") as file:
        file.write(response.content)

    print("PDF saved to:")
    print(PDF_FILE)


def extract_text():

    print("\n========== EXTRACTING PDF TEXT ==========")

    reader = PdfReader(PDF_FILE)

    print("Number of pages:", len(reader.pages))

    all_text = []

    for page_number, page in enumerate(reader.pages, start=1):

        text = page.extract_text()

        if text:
            all_text.append(text)

        print(
            f"Page {page_number}: "
            f"{len(text) if text else 0} characters"
        )

    final_text = "\n\n".join(all_text)

    with open(
        TEXT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "State/UT: Jharkhand\n"
        )
        file.write(
            "Source: Jharkhand Startup Policy 2023\n"
        )
        file.write(
            f"URL: {PDF_URL}\n\n"
        )
        file.write(final_text)

    print("\nExtracted text characters:", len(final_text))

    print("Clean text saved to:")
    print(TEXT_FILE)


if __name__ == "__main__":

    try:
        download_pdf()
        extract_text()

        print("\n========== SUCCESS ==========")
        print("Jharkhand policy PDF was downloaded and converted to text.")

    except Exception as error:

        print("\n========== ERROR ==========")
        print(error)