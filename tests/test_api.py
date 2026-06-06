import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Certificar que a raiz do projeto e o backend estão no sys.path
PROJECT_ROOT = Path(__file__).parent.parent
backend_dir = str(PROJECT_ROOT / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app_fastapi import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_endpoint(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "supabase_url" in data
    assert "supabase_anon_key" in data


def test_unauthorized_private_endpoint(client):
    # Rota privada sem cookie/header deve retornar 401
    response = client.post("/api/calculate", json={})
    assert response.status_code == 401
    assert "Sessao expirada" in response.json().get("detail", "")


def test_auth_middleware_bypass_public_paths(client):
    # Rota pública (/login) deve ser acessível sem autenticação
    response = client.get("/login")
    assert response.status_code == 200


@patch("app_fastapi._verify_supabase_jwt")
def test_authorized_private_endpoint(mock_verify, client):
    # Mock do JWT válido
    mock_verify.return_value = "user@eletromarquez.com.br"
    
    # Faz requisição com cookie de sessão
    client.cookies.set("sb-access-token", "dummy_token")
    response = client.get("/")
    
    # Deve retornar sucesso (200) e ter chamado a verificação de JWT
    assert response.status_code == 200
    mock_verify.assert_called_once_with("dummy_token")


@patch("app_fastapi._verify_supabase_jwt")
def test_auth_session_endpoint_success(mock_verify, client):
    mock_verify.return_value = "user@eletromarquez.com.br"
    
    response = client.post("/auth/session", json={"token": "valid_token"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "email": "user@eletromarquez.com.br"}
    assert "sb-access-token" in response.cookies


@patch("app_fastapi._verify_supabase_jwt")
def test_auth_session_endpoint_failure(mock_verify, client):
    mock_verify.return_value = None
    
    response = client.post("/auth/session", json={"token": "invalid_token"})
    assert response.status_code == 401
    assert "Sessao invalida" in response.json().get("detail", "")
