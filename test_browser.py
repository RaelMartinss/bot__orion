import asyncio
from utils.browser_manager import get_browser_manager

async def test():
    bm = await get_browser_manager()
    print("Iniciando navegação...")
    res = await bm.goto("https://www.google.com")
    print(res)
    
    print("Lendo página...")
    content = await bm.read_page()
    print(content[:500] + "...")
    
    print("Fechando...")
    await bm.close()

if __name__ == "__main__":
    asyncio.run(test())
