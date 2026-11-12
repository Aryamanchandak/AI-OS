import os
import tempfile

from google import genai


def upload_pdf_to_gemini(pdf_bytes: bytes, display_name: str = "document.pdf"):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        return client.files.upload(file=tmp_path)
    finally:
        os.unlink(tmp_path)


def get_gemini_file(client: genai.Client, file_uri: str):
    """Look up an already-uploaded Gemini Files API file by its URI."""
    name = "files/" + file_uri.split("/files/")[-1]
    return client.files.get(name=name)
