"""
Check script to verify project setup
"""
import sys
from pathlib import Path

def check_file(path, description):
    """Check if file exists."""
    full_path = Path(path)
    if full_path.exists():
        print(f"✓ {description}: {path}")
        return True
    else:
        print(f"✗ {description}: {path} NOT FOUND")
        return False

def check_directory(path, description):
    """Check if directory exists."""
    full_path = Path(path)
    if full_path.is_dir():
        print(f"✓ {description}: {path}")
        return True
    else:
        print(f"✗ {description}: {path} NOT FOUND")
        return False

def main():
    print("\n" + "="*60)
    print("Checking FastAPI Project Setup")
    print("="*60 + "\n")
    
    checks = []
    
    # Configuration files
    print("Configuration Files:")
    checks.append(check_file("pyproject.toml", "Dependencies config"))
    checks.append(check_file(".env.example", "Environment template"))
    checks.append(check_file(".env", "Environment file"))
    checks.append(check_file("docker-compose.yml", "Docker Compose config"))
    checks.append(check_file("Dockerfile", "Dockerfile"))
    print()
    
    # Application structure
    print("Application Structure:")
    checks.append(check_directory("app", "App package"))
    checks.append(check_file("app/__init__.py", "App init"))
    checks.append(check_file("app/main.py", "Main application file"))
    checks.append(check_file("app/config.py", "Configuration"))
    checks.append(check_file("app/database.py", "Database setup"))
    checks.append(check_file("app/redis_client.py", "Redis client"))
    checks.append(check_file("app/dependencies.py", "Dependencies"))
    print()
    
    # Models
    print("Models:")
    checks.append(check_directory("app/models", "Models package"))
    checks.append(check_file("app/models/__init__.py", "Models init"))
    checks.append(check_file("app/models/user.py", "User model"))
    print()
    
    # Schemas
    print("Schemas:")
    checks.append(check_directory("app/schemas", "Schemas package"))
    checks.append(check_file("app/schemas/__init__.py", "Schemas init"))
    checks.append(check_file("app/schemas/user.py", "User schemas"))
    print()
    
    # CRUD
    print("CRUD Operations:")
    checks.append(check_directory("app/crud", "CRUD package"))
    checks.append(check_file("app/crud/__init__.py", "CRUD init"))
    checks.append(check_file("app/crud/user.py", "User CRUD"))
    checks.append(check_file("app/crud/vpn_key.py", "VPN Key CRUD"))
    print()
    
    # VPN Client
    print("VPN Client:")
    checks.append(check_file("app/xui_client.py", "XUI Panel client"))
    print()
    
    # VPN Models
    print("VPN Models:")
    checks.append(check_file("app/models/vpn_key.py", "VPN Key model"))
    print()
    
    # VPN Schemas
    print("VPN Schemas:")
    checks.append(check_file("app/schemas/vpn_key.py", "VPN Key schemas"))
    print()
    
    # VPN Routers
    print("VPN Routers:")
    checks.append(check_file("app/routers/vpn.py", "VPN router"))
    print()
    
    # Routers
    print("Routers:")
    checks.append(check_directory("app/routers", "Routers package"))
    checks.append(check_file("app/routers/__init__.py", "Routers init"))
    checks.append(check_file("app/routers/auth.py", "Auth router (API)"))
    checks.append(check_file("app/routers/web.py", "Web router (pages)"))
    print()
    
    # Templates
    print("Templates:")
    checks.append(check_directory("app/templates", "Templates directory"))
    checks.append(check_file("app/templates/base.html", "Base template"))
    checks.append(check_file("app/templates/register.html", "Register template"))
    checks.append(check_file("app/templates/login.html", "Login template"))
    checks.append(check_file("app/templates/profile.html", "Profile template"))
    checks.append(check_file("app/templates/vpn_panel.html", "VPN panel template"))
    checks.append(check_file("app/templates/vpn_new.html", "VPN new key template"))
    print()
    
    # Tests
    print("Tests:")
    checks.append(check_directory("tests", "Tests package"))
    checks.append(check_file("tests/__init__.py", "Tests init"))
    checks.append(check_file("tests/test_auth.py", "Auth tests"))
    print()
    
    # Documentation
    print("Documentation:")
    checks.append(check_file("README.md", "Main README"))
    checks.append(check_file("QUICKSTART.md", "Quick Start Guide"))
    print()
    
    # Summary
    print("="*60)
    total = len(checks)
    passed = sum(checks)
    failed = total - passed
    
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    
    if failed == 0:
        print("\n✓ All checks passed! Project is ready to use.\n")
        print("Next steps:")
        print("1. Start PostgreSQL and Redis (docker-compose up -d postgres redis)")
        print("2. Run: uvicorn app.main:app --reload")
        print("3. Open: http://localhost:8000\n")
        return 0
    else:
        print("\n✗ Some checks failed. Please review the output above.\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
