import skills

async def main():
    # Assuming "docs-to-files" was found and added
    docs = await skills.load("docs-to-files").fetch_and_store(library="/vercel/next.js", topic="routing", output_dir="output/docs")
    return docs
