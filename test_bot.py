from playwright.sync_api import sync_playwright
import os
import time

USERNAME = os.environ.get('ENJOY_USERNAME')
PASSWORD = os.environ.get('ENJOY_PASSWORD')

def test_simple():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=False para VER
        page = browser.new_page()
        
        try:
            # 1. Login
            print("1. Login...")
            page.goto("https://member.resamania.com/enjoy")
            page.fill("input[type='email']", USERNAME)
            page.click("button:has-text('Continuar')")
            time.sleep(2)
            page.fill("input[type='password']", PASSWORD)
            page.click("button:has-text('Conectarme')")
            time.sleep(5)
            
            # 2. Ir a planning
            print("2. Planning page...")
            page.goto("https://member.resamania.com/enjoy/planning")
            time.sleep(5)
            
            # 3. Buscar día 5
            print("3. Buscando día 5...")
            page.click("text=5")
            time.sleep(5)
            
            # 4. Buscar AQUAGYM
            print("4. Buscando AQUAGYM...")
            content = page.text_content()
            
            if "AQUAGYM" in content.upper():
                print("✅ ¡AQUAGYM ENCONTRADO!")
                # Buscar la línea exacta
                lines = content.split('\n')
                for line in lines:
                    if "AQUAGYM" in line.upper():
                        print(f"   Línea: {line}")
            else:
                print("❌ AQUAGYM NO ENCONTRADO")
                
            # 5. Screenshot
            page.screenshot(path="test_result.png")
            print("📸 Screenshot: test_result.png")
            
        finally:
            browser.close()

if __name__ == "__main__":
    test_simple()
