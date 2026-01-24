import aiohttp
import asyncio

async def fetch_and_store(url: str, file_path: str) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.text()
            with open(file_path, 'w') as file:
                file.write(content)

if __name__ == '__main__':
    url = 'https://example.com/documentation'
    file_path = 'documentation.txt'
    asyncio.run(fetch_and_store(url, file_path))