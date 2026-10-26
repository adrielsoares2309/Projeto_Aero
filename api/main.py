"""Aplicação FastAPI da AeroMotion Dynamics."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from api.history import PredictionHistory
from api.predictor import ModelService
from api.schemas import BatchRequest, RegimeCommand, SensorReading
from simulator import REGIME_LABELS, REGIMES, request_regime, simulator_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
ROOT_DIR = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_path = Path(
        os.getenv(
            "AEROMOTION_DB_PATH",
            str(ROOT_DIR / "data" / "runtime" / "predictions.sqlite3"),
        )
    )
    history = PredictionHistory(database_path)
    try:
        app.state.service = ModelService(ROOT_DIR, history)
        app.state.history = history
        app.state.load_error = None
    except Exception as error:  # API remains available for diagnostic /health.
        logging.exception("Falha ao carregar artefatos")
        app.state.service = None
        app.state.history = history
        app.state.load_error = str(error)
    yield


app = FastAPI(title="AeroMotion Dynamics API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def service_or_error(request: Request) -> ModelService:
    if request.app.state.service is None:
        raise HTTPException(status_code=503, detail=f"Modelos indisponíveis: {request.app.state.load_error}")
    return request.app.state.service


@app.get("/health")
def health(request: Request):
    service = request.app.state.service
    return {
        "status": "online" if service else "degradado",
        "modelos_disponiveis": service is not None,
        "erro_carregamento": request.app.state.load_error,
        "modelo": service.status if service else None,
    }


@app.post("/predict")
def predict(reading: SensorReading, request: Request):
    try:
        return service_or_error(request).predict(reading.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        logging.exception("Erro durante a inferência")
        raise HTTPException(status_code=500, detail="Falha ao executar a inferência.") from error


@app.post("/predict-batch")
def predict_batch(batch: BatchRequest, request: Request):
    service = service_or_error(request)
    results = []
    for index, reading in enumerate(batch.leituras):
        try:
            results.append(service.predict(reading.model_dump()))
        except ValueError as error:
            raise HTTPException(status_code=409, detail={"indice": index, "erro": str(error)}) from error
    return {"quantidade": len(results), "resultados": results}


@app.get("/predictions")
def predictions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    equipamento: str | None = Query(default=None, pattern=r"^TURB-10[1-4]$"),
):
    service_or_error(request)
    return {"items": request.app.state.history.list(limit, equipamento)}


@app.get("/stats")
def stats(request: Request):
    service_or_error(request)
    return request.app.state.history.stats()


@app.get("/regime")
def get_regime():
    """Regime selecionado/ativo e heartbeat do simulador (fonte: arquivos locais)."""
    return simulator_status()


@app.post("/regime")
def set_regime(command: RegimeCommand):
    """Solicita um regime ao simulador. O processo aplica no próximo ciclo."""
    try:
        return request_regime(command.regime)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível gravar o comando do simulador: {error}",
        ) from error


@app.get("/regimes")
def list_regimes():
    """Lista os regimes operacionais disponíveis."""
    return {"regimes": list(REGIMES), "rotulos": dict(REGIME_LABELS)}
