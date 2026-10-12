from pypdf import PdfReader

path = "documents/government/Tamil_Nadu_Startup_and_Innovation_Policy_2023.pdf"
reader = PdfReader(path)

for page_num in [19, 20, 22, 24, 25, 27, 28, 34, 35, 36, 38, 39]:
    text = reader.pages[page_num - 1].extract_text() or ""
    print(f"\n{'=' * 25} PAGE {page_num} {'=' * 25}")
    print(text[:3500] if text.strip() else "[No extractable text]")
