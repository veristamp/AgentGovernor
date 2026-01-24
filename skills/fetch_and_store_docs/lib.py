import asyncio

async def fetch_and_store_docs(library_name: str, file_path: str) -> None:
    # Step 1: Resolve the library ID
    library_id_response = await ctx.resolve_library_id({"query": f"Fetch documentation for {library_name}", "libraryName": library_name})
    library_id = library_id_response['libraryId']

    # Step 2: Query the documentation using the resolved library ID
    docs_response = await ctx.query_docs({"libraryId": library_id, "query": f"Documentation for {library_name}"})
    documentation = docs_response['documentation']

    # Step 3: Store the documentation in a file
    edits = [{"oldText": "", "newText": documentation}]
    await ctx.edit_file({"path": file_path, "edits": edits, "dry_run": False})