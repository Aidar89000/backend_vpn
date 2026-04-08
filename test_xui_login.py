"""
Тестовый скрипт для проверки подключения к XUI Panel.
Запустите: python test_xui_login.py
"""
import requests
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from app.config import get_settings

settings = get_settings()

def test_login():
    print("=" * 60)
    print("XUI Panel Login Test")
    print("=" * 60)
    print(f"\nXUI_HOST: {settings.XUI_HOST}")
    print(f"XUI_USERNAME: {settings.XUI_USERNAME}")
    print(f"XUI_PASSWORD: {'*' * len(settings.XUI_PASSWORD)}")
    
    # Пробуем разные варианты URL
    base = settings.XUI_HOST.rstrip("/")
    test_urls = [
        f"{base}/login",
        f"{base}/panel/login",
        f"{base}/xui/login",
    ]
    
    print(f"\nTesting login at different endpoints:\n")
    
    for url in test_urls:
        print(f"Trying: {url}")
        try:
            # Пробуем с form data
            response = requests.post(
                url,
                data={
                    "username": settings.XUI_USERNAME,
                    "password": settings.XUI_PASSWORD,
                },
                verify=False,
                timeout=10,
            )
            
            print(f"  Status: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            
            if response.status_code == 200:
                try:
                    json_resp = response.json()
                    print(f"  JSON: {json_resp}")
                    if json_resp.get("success"):
                        print(f"  ✅ SUCCESS!")
                        return True
                except:
                    pass
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        print()
    
    print("=" * 60)
    print("❌ All login attempts failed!")
    print("=" * 60)
    print("\nPossible issues:")
    print("1. Username or password is incorrect")
    print("2. Two-factor authentication (2FA) is enabled")
    print("3. XUI Panel API is disabled or changed")
    print("4. IP is blocked by XUI Panel")
    print("\nTry to login manually at:")
    print(f"{base}/login")
    
    return False

if __name__ == "__main__":
    test_login()
