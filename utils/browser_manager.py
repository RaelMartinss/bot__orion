"""
utils/browser_manager.py
Gerenciador persistente do Playwright para o Orion (Nível 5).
Permite navegação, leitura simplificada e interação com a web.
"""

import logging
import asyncio
import re
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class BrowserManager:
    _instance = None

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _ensure_browser(self):
        async with self._lock:
            if not self.playwright:
                self.playwright = await async_playwright().start()
            if not self.browser:
                try:
                    self.browser = await self.playwright.chromium.launch(headless=False)
                except Exception as e:
                    if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                        logger.warning("Chromium não encontrado. Instalando automaticamente...")
                        proc = await asyncio.create_subprocess_exec(
                            "playwright", "install", "chromium",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        await proc.wait()
                        logger.info("Chromium instalado. Tentando iniciar novamente.")
                        self.browser = await self.playwright.chromium.launch(headless=False)
                    else:
                        raise
                self.context = await self.browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
                )
                self.page = await self.context.new_page()
            return self.page

    async def goto(self, url: str):
        page = await self._ensure_browser()
        if not url.startswith("http"):
            url = f"https://www.google.com/search?q={url}" if "." not in url else f"https://{url}"
        
        await page.goto(url, wait_until="networkidle", timeout=60000)
        return f"Navegado com sucesso para: {page.url}"

    async def read_page(self) -> str:
        page = await self._ensure_browser()
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")

        # Remove scripts, styles e lixo orbital
        for s in soup(["script", "style", "header", "footer", "nav"]):
            s.decompose()

        # Extrai links e inputs importantes
        links = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if text and len(text) > 2:
                links.append(f"[LINK: {text}]")

        inputs = []
        for i in soup.find_all(["input", "button", "textarea"]):
            placeholder = i.get("placeholder") or i.get("name") or i.get("id") or i.get("value") or i.get_text(strip=True)
            if placeholder:
                inputs.append(f"[INPUT/BTN: {placeholder}]")

        # Texto visível limpo
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)[:2000] # Limite de 2000 caracteres para o prompt

        res = f"📍 URL ATUAL: {page.url}\n\n"
        res += f"🔎 TEXTO ÚTIL:\n{text}\n\n"
        res += f"🔗 LINKS CLICÁVEIS (Amostra):\n{', '.join(links[:15])}\n\n"
        res += f"⌨️ CAMPOS DE INTERAÇÃO:\n{', '.join(inputs[:10])}"
        
        return res

    async def click(self, selector: str):
        page = await self._ensure_browser()
        # Tenta clicar por texto primeiro (mais intuitivo para LLM)
        try:
            await page.get_by_role("button", name=selector, exact=False).click(timeout=5000)
        except:
            try:
                await page.get_by_text(selector, exact=False).first.click(timeout=5000)
            except:
                await page.click(selector, timeout=10000)
        
        await page.wait_for_load_state("networkidle", timeout=5000)
        return f"Clique executado em '{selector}'. URL agora: {page.url}"

    async def fill(self, selector: str, text: str):
        page = await self._ensure_browser()
        # Localiza o melhor campo
        try:
            target = page.locator(selector)
            await target.fill(text)
        except:
            # Fallback para placeholder ou nome
            await page.get_by_placeholder(selector, exact=False).fill(text)
        
        return f"Campo '{selector}' preenchido com '{text}'."

    async def close(self):
        async with self._lock:
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
        return "Navegador encerrado com sucesso."

async def get_browser_manager() -> BrowserManager:
    return await BrowserManager.get_instance()
