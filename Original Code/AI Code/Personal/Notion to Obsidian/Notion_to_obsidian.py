from notion_client import Client
import os
import re
from pathlib import Path

from dotenv import load_dotenv

# Read NOTION_API_KEY from the shared workspace .env (AI Code/.env).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
ROOT_PAGE_ID = "34537e036a97808695a4dba650007592"
OUTPUT_DIR = "/Users/aryamanchandak/Documents/Obsidian Vault/Aryamans Vault/Notion"

notion = Client(auth=NOTION_API_KEY)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def get_plain_text(rich_text):
    return "".join([t["plain_text"] for t in rich_text])

def fetch_blocks(block_id):
    return notion.blocks.children.list(block_id=block_id)["results"]

def extract_title(block):
    return block["child_page"]["title"]

def process_page(block_id, path):
    blocks = fetch_blocks(block_id)
    content = ""

    for block in blocks:
        t = block["type"]

        if t == "paragraph":
            content += get_plain_text(block["paragraph"]["rich_text"]) + "\n\n"

        elif t == "heading_1":
            content += "# " + get_plain_text(block["heading_1"]["rich_text"]) + "\n\n"

        elif t == "child_page":
            title = extract_title(block)
            new_path = os.path.join(path, clean_filename(title))
            os.makedirs(new_path, exist_ok=True)

            child_content = process_page(block["id"], new_path)

            with open(os.path.join(new_path, clean_filename(title) + ".md"), "w") as f:
                f.write(child_content)

    return content

# START
root_blocks = fetch_blocks(ROOT_PAGE_ID)

for block in root_blocks:
    if block["type"] == "child_page":
        title = extract_title(block)
        page_path = os.path.join(OUTPUT_DIR, clean_filename(title))
        os.makedirs(page_path, exist_ok=True)

        content = process_page(block["id"], page_path)

        with open(os.path.join(page_path, clean_filename(title) + ".md"), "w") as f:
            f.write(content)

print("Sync complete.")