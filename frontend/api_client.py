"""Cliente HTTP para a API AeroMotion Dynamics.

Centraliza todas as requisições, tratamento de erros e timeouts.
Nenhuma URL é espalhada fora deste módulo.
"""
from __future__ import annotations

import os
from typing import Any

import requests

# URL base configurável via variável de ambiente
API_BASE_URL: str = os.getenv("AEROMOTION_API_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_TIMEOUT: int = 5  # segundos


def _get(path: str, params: dict | None = None) -> tuple[dict | list | None, str | None]:
    """GET genérico. Retorna (dados, erro)."""
    try:
        response = requests.get(
            f"{API_BASE_URL}{path}", params=params, timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        return response.json(), None
    except requests.ConnectionError:
        return None, "Conexão recusada — a API não está acessível."
    except requests.Timeout:
        return None, f"Timeout após {DEFAULT_TIMEOUT}s — a API não respondeu."
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return None, f"HTTP {exc.response.status_code}: {detail}"
    except ValueError:
        return None, "Resposta JSON inválida recebida da API."
    except Exception as exc:  # noqa: BLE001
        return None, f"Erro inesperado: {exc}"


def _post(path: str, payload: dict) -> tuple[dict | None, str | None]:
    """POST genérico. Retorna (dados, erro)."""
    try:
        response = requests.post(
            f"{API_BASE_URL}{path}", json=payload, timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        return response.json(), None
    except requests.ConnectionError:
        return None, "Conexão recusada — a API não está acessível."
    except requests.Timeout:
        return None, f"Timeout após {DEFAULT_TIMEOUT}s — a API não respondeu."
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return None, f"HTTP {exc.response.status_code}: {detail}"
    except ValueError:
        return None, "Resposta JSON inválida recebida da API."
    except Exception as exc:  # noqa: BLE001
        return None, f"Erro inesperado: {exc}"


# --- Endpoints específicos ---

def get_health() -> tuple[dict | None, str | None]:
    """GET /health — estado da API e disponibilidade dos modelos."""
    return _get("/health")


def get_predictions(limit: int = 200, equipamento: str | None = None) -> tuple[dict | None, str | None]:
    """GET /predictions — histórico de predições."""
    params: dict[str, Any] = {"limit": limit}
    if equipamento:
        params["equipamento"] = equipamento
    return _get("/predictions", params)


def get_stats() -> tuple[dict | None, str | None]:
    """GET /stats — estatísticas globais do histórico."""
    return _get("/stats")


def get_regime_status() -> tuple[dict | None, str | None]:
    """GET /regime — regime selecionado/ativo e estado do simulador."""
    return _get("/regime")


def set_operating_regime(regime: str) -> tuple[dict | None, str | None]:
    """POST /regime — solicita a troca de regime ao simulador real."""
    return _post("/regime", {"regime": regime})


def get_regimes() -> tuple[dict | None, str | None]:
    """GET /regimes — lista os regimes operacionais disponíveis."""
    return _get("/regimes")


def is_api_online(health: dict | None) -> bool:
    """Verifica se a API está online e os modelos estão disponíveis."""
    if health is None:
        return False
    return health.get("modelos_disponiveis", False)
