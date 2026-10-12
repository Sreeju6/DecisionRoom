from pypdf import PdfReader

path = "documents/government/Tamil_Nadu_Startup_and_Innovation_Policy_2023.pdf"
reader = PdfReader(path)

topics = [
    "objectives",
    "definitions",
    "policy period",
    "investment ecosystem",
    "access to market",
    "startup support centres",
    "funding",
    "intellectual property",
    "procurement",
    "eligibility",
]

for topic in topics:
    matches = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if topic.lower() in text.lower():
            matches.append(i + 1)
    print(f"{topic}: {matches}")
