import docx
import sys

def read_docx(file_path):
    try:
        doc = docx.Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    print(read_docx("Datová a ekonomická Analýza FVE Antelon Energy zadání.docx"))
