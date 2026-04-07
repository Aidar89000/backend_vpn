from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_index_page():
    """Test index page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Добро пожаловать" in response.text


def test_register_page():
    """Test register page."""
    response = client.get("/register")
    assert response.status_code == 200
    assert "Регистрация" in response.text


def test_login_page():
    """Test login page."""
    response = client.get("/login")
    assert response.status_code == 200
    assert "Вход" in response.text


def test_register_user():
    """Test user registration."""
    response = client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123"
        }
    )
    # Should be 201 or 400 if user already exists
    assert response.status_code in [201, 400]


def test_login_wrong_credentials():
    """Test login with wrong credentials."""
    response = client.post(
        "/auth/login",
        json={
            "username": "wronguser",
            "password": "wrongpass"
        }
    )
    assert response.status_code == 401
