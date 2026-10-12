from pypdf import PdfReader

path = "documents/government/Tamil_Nadu_Startup_and_Innovation_Policy_2023.pdf"
reader = PdfReader(path)

lengths = [len(page.extract_text() or "") for page in reader.pages]

print("TOTAL PAGES:", len(reader.pages))
print("PAGES WITH TEXT:", sum(n > 100 for n in lengths))
print("PAGES WITH LITTLE OR NO TEXT:", sum(n <= 100 for n in lengths))
print("TOTAL EXTRACTED CHARACTERS:", sum(lengths))
print("\nTEXT SAMPLE FROM PAGES 4-6:")

for i in range(3, min(6, len(reader.pages))):
    print(f"\n--- PAGE {i + 1} ---")
    print((reader.pages[i].extract_text() or "")[:2000])
