from pypdf import PdfReader
from pathlib import Path

pdf_path = Path(
    "documents/government/"
    "Tamil_Nadu_Startup_and_Innovation_Policy_2023.pdf"
)

txt_path = Path(
    "documents/government/"
    "Tamil_Nadu_Startup_and_Innovation_Policy_2023.txt"
)

reader = PdfReader(str(pdf_path))

with txt_path.open("w", encoding="utf-8") as output:
    output.write(
        "State/UT: Tamil Nadu\n"
        "Source: Tamil Nadu Startup and Innovation Policy 2023\n"
        "Policy period: 2023-2032\n"
        "Official policy PDF: "
        "https://startuptn.in/pdf/Tamil-Nadu-Startup-and-Innovation-Policy-2023.pdf\n\n"
    )

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            output.write(f"\n--- PDF PAGE {page_number} ---\n")
            output.write(text.strip() + "\n")

print("Created:", txt_path)
print("Pages read:", len(reader.pages))
print("Text characters:", txt_path.stat().st_size)
