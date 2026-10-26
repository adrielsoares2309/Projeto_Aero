"""Simulador de telemetria industrial para a API AeroMotion.

O simulador gera séries temporais sintéticas para os quatro equipamentos e as
envia à API FastAPI.  Diferentemente de um sorteio independente por leitura, o
estado físico de cada equipamento é mantido entre ciclos:

- a carga solicitada evolui com inércia;
- a temperatura do mancal responde com inércia térmica (primeira ordem);
- vibração, pressão, rotação, ruído e corrente acompanham a carga com
  constantes de tempo próprias e ruído de medição correlacionado (AR(1));
- as proporções nominais/anormais de cada regime são aplicadas em blocos
  determinísticos, com perfis de anomalia A/B/C derivados do dataset;
- a troca de regime altera apenas o alvo físico, sem reiniciar o processo nem
  apagar o histórico.

Os três regimes são mutuamente exclusivos e controlados por um arquivo de
controle (``data/runtime/simulator_control.json``).  O dashboard escreve nesse
arquivo através da API; o processo do simulador lê o comando no próximo ciclo.
O simulador grava seu estado/heartbeat em
``data/runtime/simulator_state.json`` e um lock de processo em
``data/runtime/simulator.lock`` para impedir instâncias duplicadas.

Todos os valores gerados são sintéticos (``origem_leitura="simulada"``) e não
representam medições reais de campo.  A classe prevista pelo modelo nunca é
definida aqui: o simulador envia apenas sensores e metadados operacionais.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - Linux/macOS
    msvcrt = None  # type: ignore[assignment]
    import fcntl

ROOT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(
    os.getenv("AEROMOTION_RUNTIME_DIR", str(ROOT_DIR / "data" / "runtime"))
)
CONTROL_FILE = RUNTIME_DIR / "simulator_control.json"
STATE_FILE = RUNTIME_DIR / "simulator_state.json"
LOCK_FILE = RUNTIME_DIR / "simulator.lock"

REGIMES = ("Cruzeiro", "Carga_Media", "Carga_Alta")
REGIME_LABELS = {
    "Cruzeiro": "Cruzeiro",
    "Carga_Media": "Carga Média",
    "Carga_Alta": "Carga Alta",
}
DEFAULT_REGIME = "Cruzeiro"
EQUIPMENTS = ("TURB-101", "TURB-102", "TURB-103", "TURB-104")

# Sensores reais do dataset. Nenhuma variável ou unidade é inventada.
SENSOR_FIELDS = (
    "temperatura_mancal_c",
    "vibracao_rms_mms",
    "pressao_oleo_bar",
    "rotacao_rpm",
    "emissao_acustica_db",
    "corrente_eletrica_amp",
)

# Limites operacionais usados pelos indicadores de faixa da API
# (api/predictor.py). O perfil NOMINAL do simulador opera dentro deles; os
# perfis de anomalia podem ultrapassá-los de propósito, mas continuam dentro
# de GENERATION_LIMITS.
SENSOR_LIMITS = {
    "temperatura_mancal_c": (45.0, 85.0),
    "vibracao_rms_mms": (1.0, 4.5),
    "pressao_oleo_bar": (3.5, 5.2),
    "rotacao_rpm": (2300.0, 3600.0),
    "emissao_acustica_db": (40.0, 68.0),
    "corrente_eletrica_amp": (18.0, 42.0),
}

# Alvos de equilíbrio por regime, estimados a partir das médias do dataset
# tratado para leituras NORMAIS (tipo_falha=0) em cada modo_operacao:
#   Cruzeiro: temp 51.9 | vib 1.81 | pressao 3.81 | rpm 2400.7 | acust 44.0 | corrente 20.05
#   Carga_Media: temp 61.9 | vib 2.50 | pressao 4.20 | rpm 3000.5 | acust 52.0 | corrente 27.98
#   Carga_Alta: temp 72.0 | vib 3.80 | pressao 4.80 | rpm 3500.6 | acust 62.0 | corrente 38.02
# A Carga_Alta nominal permanece dentro dos limites operacionais acima; os
# perfis anormais usam faixas mais amplas, derivadas do dataset.
REGIME_PROFILES: dict[str, dict[str, float]] = {
    "Cruzeiro": {
        "load_index": 0.25,
        "rotacao_rpm": 2400.7,
        "temperatura_mancal_c": 51.9,
        "vibracao_rms_mms": 1.81,
        "pressao_oleo_bar": 3.81,
        "emissao_acustica_db": 44.0,
        "corrente_eletrica_amp": 20.05,
        "noise_scale": 1.0,
    },
    "Carga_Media": {
        "load_index": 0.55,
        "rotacao_rpm": 3000.5,
        "temperatura_mancal_c": 61.9,
        "vibracao_rms_mms": 2.50,
        "pressao_oleo_bar": 4.20,
        "emissao_acustica_db": 52.0,
        "corrente_eletrica_amp": 27.98,
        "noise_scale": 1.15,
    },
    "Carga_Alta": {
        "load_index": 0.90,
        "rotacao_rpm": 3500.6,
        "temperatura_mancal_c": 72.0,
        "vibracao_rms_mms": 3.80,
        "pressao_oleo_bar": 4.80,
        "emissao_acustica_db": 62.0,
        "corrente_eletrica_amp": 38.02,
        "noise_scale": 1.30,
    },
}

# Faixas de GERAÇÃO sintética, derivadas dos mínimos/máximos observados no
# dataset tratado (12.000 leituras). Não são limites de segurança industrial e
# não devem ser usados como alarme de campo. Servem apenas para impedir que a
# simulação produza valores fora do domínio estatístico do treinamento.
GENERATION_LIMITS: dict[str, tuple[float, float]] = {
    "temperatura_mancal_c": (40.0, 119.6),
    "vibracao_rms_mms": (0.08, 15.17),
    "pressao_oleo_bar": (0.68, 5.59),
    "rotacao_rpm": (2278.2, 3641.4),
    "emissao_acustica_db": (34.15, 104.0),
    "corrente_eletrica_amp": (15.35, 62.54),
}

# Configuração centralizada do gerador. As proporções são do PERFIL GERADO
# (nominal/anormal), não da classe prevista pelo modelo.  O bloco define quantas
# leituras são sorteadas antes de repetir a proporção; 100 é múltiplo de todos
# os blocos, portanto um bloco de 100 leituras reproduz exatamente a proporção.
REGIME_CONFIG: dict[str, dict[str, Any]] = {
    "Cruzeiro": {
        "nominal_ratio": 0.95,
        "anomaly_ratio": 0.05,
        "block_size": 20,
        # Desvios leves: 30% do afastamento observado nas classes de falha.
        "anomaly_intensity": 0.30,
        "anomaly_weights": {"A": 0.40, "B": 0.40, "C": 0.20},
    },
    "Carga_Media": {
        "nominal_ratio": 0.70,
        "anomaly_ratio": 0.30,
        "block_size": 10,
        # Desvios moderados: 60% do afastamento das classes de falha.
        "anomaly_intensity": 0.60,
        "anomaly_weights": {"A": 0.35, "B": 0.35, "C": 0.30},
    },
    "Carga_Alta": {
        "nominal_ratio": 0.40,
        "anomaly_ratio": 0.60,
        "block_size": 5,
        # Esforço elevado: usa a escala observada nas classes de falha do dataset.
        "anomaly_intensity": 1.00,
        "anomaly_weights": {"A": 0.34, "B": 0.33, "C": 0.33},
    },
}

ANOMALY_PROFILE_LABELS = {
    "A": "Sobrecarga térmica",
    "B": "Solicitação mecânica e vibração",
    "C": "Desvio combinado",
}

# Afastamentos médios em relação ao perfil nominal de cada regime. Foram
# calculados a partir das médias de `tipo_falha` no dataset tratado:
#   A (classe 3 - térmica): temperatura sobe e pressão de óleo cai;
#   B (classe 1 - rolamento): vibração e emissão acústica sobem;
#   C (classe 2 - rotor): vibração e corrente sobem, com fração térmica.
# O perfil C usa 35% do afastamento térmico da classe 3 para representar uma
# combinação controlada, não uma falha confirmada.
ANOMALY_PROFILE_DELTAS: dict[str, dict[str, dict[str, float]]] = {
    "Cruzeiro": {
        "A": {"temperatura_mancal_c": 33.90, "pressao_oleo_bar": -2.27},
        "B": {"vibracao_rms_mms": 6.80, "emissao_acustica_db": 26.98},
        "C": {
            "temperatura_mancal_c": 11.87,
            "vibracao_rms_mms": 7.80,
            "emissao_acustica_db": 4.05,
            "corrente_eletrica_amp": 16.18,
        },
    },
    "Carga_Media": {
        "A": {"temperatura_mancal_c": 35.65, "pressao_oleo_bar": -2.27},
        "B": {"vibracao_rms_mms": 6.76, "emissao_acustica_db": 27.69},
        "C": {
            "temperatura_mancal_c": 12.48,
            "vibracao_rms_mms": 7.96,
            "emissao_acustica_db": 4.15,
            "corrente_eletrica_amp": 16.03,
        },
    },
    "Carga_Alta": {
        "A": {"temperatura_mancal_c": 34.77, "pressao_oleo_bar": -2.35},
        "B": {"vibracao_rms_mms": 6.69, "emissao_acustica_db": 27.93},
        "C": {
            "temperatura_mancal_c": 12.17,
            "vibracao_rms_mms": 7.94,
            "emissao_acustica_db": 4.19,
            "corrente_eletrica_amp": 16.08,
        },
    },
}


def _validate_regime_config() -> None:
    """Falha cedo se as proporções configuradas não forem representáveis."""
    for regime, config in REGIME_CONFIG.items():
        if regime not in REGIMES:
            raise ValueError(f"Configuração para regime desconhecido: {regime!r}")
        total = float(config["nominal_ratio"]) + float(config["anomaly_ratio"])
        if not math.isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError(f"As proporções de {regime} não totalizam 100%: {total}")
        block_size = int(config["block_size"])
        nominal_count = int(round(float(config["nominal_ratio"]) * block_size))
        if not math.isclose(
            nominal_count / block_size,
            float(config["nominal_ratio"]),
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"O bloco de {regime} não representa exatamente a proporção nominal."
            )
        weights = config["anomaly_weights"]
        if not math.isclose(sum(float(value) for value in weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError(f"Os pesos de anomalia de {regime} não totalizam 100%")
        if block_size <= 0 or nominal_count <= 0 or nominal_count >= block_size:
            raise ValueError(f"Bloco inválido para {regime}: {block_size}")


_validate_regime_config()

# Constantes de tempo físicas (segundos de operação simulados).
TAU_LOAD_S = 20.0
TAU_RPM_S = 12.0
TAU_VIBRATION_S = 18.0
TAU_THERMAL_S = 90.0
TAU_PRESSURE_S = 35.0
TAU_ACOUSTIC_S = 20.0
TAU_CURRENT_S = 12.0

# Ruído de processo/medição (desvio-padrão) e tempos de correlação.
SIGMA_LOAD = 0.004
TAU_LOAD_NOISE_S = 60.0
SIGMA_RPM = 6.0
TAU_RPM_NOISE_S = 20.0
SIGMA_VIBRATION = 0.06
TAU_VIBRATION_NOISE_S = 25.0
SIGMA_TEMP_DRIFT = 0.55
TAU_TEMP_DRIFT_S = 300.0
SIGMA_TEMP_MEASUREMENT = 0.10
SIGMA_PRESSURE = 0.025
TAU_PRESSURE_NOISE_S = 30.0
SIGMA_ACOUSTIC = 0.30
TAU_ACOUSTIC_NOISE_S = 25.0
SIGMA_CURRENT = 0.14
TAU_CURRENT_NOISE_S = 20.0

# Constantes de resposta dos componentes de anomalia. A temperatura de base do
# mancal continua com inércia de 90 s; o componente adicional de sobrecarga
# responde mais rápido para que um episódio de poucos ciclos seja observável.
# São aproximações de teste, não um modelo termodinâmico de falha.
TAU_ANOMALY_THERMAL_S = 25.0
TAU_ANOMALY_VIBRATION_S = 8.0
TAU_ANOMALY_PRESSURE_S = 12.0
TAU_ANOMALY_ACOUSTIC_S = 10.0
TAU_ANOMALY_CURRENT_S = 6.0


def _now_iso() -> str:
    """Timestamp local sem timezone, igual ao contrato da API."""
    return datetime.now().isoformat(timespec="milliseconds")


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Escrita atômica para evitar leitura parcial pelo dashboard."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else None
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def write_control(
    regime: str,
    *,
    action: str = "run",
    path: Path | None = None,
    requested_by: str = "dashboard",
) -> dict[str, Any]:
    """Registra o regime solicitado. O simulador aplica no próximo ciclo."""
    if regime not in REGIMES:
        raise ValueError(
            f"Regime inválido: {regime!r}. Valores aceitos: {', '.join(REGIMES)}."
        )
    if action not in {"run", "stop"}:
        raise ValueError(f"Ação inválida: {action!r}. Use 'run' ou 'stop'.")
    target = path or CONTROL_FILE
    payload = {
        "regime": regime,
        "action": action,
        "requested_by": requested_by,
        "updated_at": _now_iso(),
        "version": 2,
    }
    _atomic_write_json(target, payload)
    return payload


def read_control(path: Path | None = None) -> dict[str, Any] | None:
    return _read_json(path or CONTROL_FILE)


def request_stop(
    *, control_path: Path | None = None, state_path: Path | None = None
) -> dict[str, Any]:
    """Solicita parada graciosa preservando o estado e o histórico."""
    control = read_control(control_path)
    state = read_state(state_path)
    regime = None
    for source in (control, state):
        if source and source.get("regime") in REGIMES:
            regime = source["regime"]
            break
    return write_control(regime or DEFAULT_REGIME, action="stop", path=control_path)


def write_state(state: dict[str, Any], path: Path | None = None) -> None:
    _atomic_write_json(path or STATE_FILE, state)


def read_state(path: Path | None = None) -> dict[str, Any] | None:
    return _read_json(path or STATE_FILE)


def simulator_status(
    *,
    control_path: Path | None = None,
    state_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Une comando e heartbeat em um status consumível pela API/dashboard."""
    control = read_control(control_path) or {}
    state = read_state(state_path) or {}
    reference = now or datetime.now()

    selected = control.get("regime")
    if selected not in REGIMES:
        selected = state.get("regime") if state.get("regime") in REGIMES else DEFAULT_REGIME

    interval = float(state.get("interval_seconds") or 10.0)
    last_cycle = _parse_iso(state.get("last_cycle_at"))
    age = None
    online = False
    if state.get("status") == "running" and last_cycle is not None:
        age = max(0.0, (reference - last_cycle).total_seconds())
        online = age <= max(15.0, interval * 1.5 + 5.0)

    changed_at = _parse_iso(state.get("regime_changed_at")) or _parse_iso(
        control.get("updated_at")
    )
    since_seconds = None
    if changed_at is not None:
        since_seconds = max(0.0, (reference - changed_at).total_seconds())

    active = (
        state.get("regime")
        if online and state.get("regime") in REGIMES
        else None
    )
    status = state.get("status") or ("desconhecido" if not state else "parado")

    if online:
        message = f"Simulador online no regime {REGIME_LABELS.get(active or selected, active or selected)}."
    elif state:
        message = (
            f"Simulador sem heartbeat recente (status: {status}). "
            "Verifique o processo em infra/simulator.log."
        )
    else:
        message = "Simulador ainda não iniciado. O regime selecionado fica registrado para o próximo início."

    return {
        "regimes_disponiveis": list(REGIMES),
        "rotulos": dict(REGIME_LABELS),
        "regime_selecionado": selected,
        "regime_ativo": active,
        "regime_anterior": state.get("regime_anterior"),
        "ultima_mudanca": changed_at.isoformat(timespec="seconds") if changed_at else None,
        "segundos_desde_transicao": round(since_seconds, 1) if since_seconds is not None else None,
        "simulador_online": online,
        "status_simulador": status,
        "ultimo_ciclo": state.get("last_cycle_at"),
        "idade_ultimo_ciclo_s": round(age, 1) if age is not None else None,
        "intervalo_segundos": interval,
        "pid": state.get("pid"),
        "api_url": state.get("api_url"),
        "origem": "simulada",
        "mensagem": message,
        "atualizado_em": _now_iso(),
    }


def request_regime(
    regime: str,
    *,
    control_path: Path | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Valida e grava um novo regime, retornando o status resultante."""
    if regime not in REGIMES:
        raise ValueError(
            f"Regime inválido: {regime!r}. Valores aceitos: {', '.join(REGIMES)}."
        )
    write_control(regime, action="run", path=control_path, requested_by="api")
    return simulator_status(control_path=control_path, state_path=state_path)


class SimulatorLock:
    """Lock exclusivo de processo (Windows: msvcrt; POSIX: fcntl)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or LOCK_FILE
        self._handle: Any = None
        self.acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        try:
            if msvcrt is not None:
                self._handle.seek(0)
                if self.path.stat().st_size == 0:
                    self._handle.write("1")
                    self._handle.flush()
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - Linux/macOS
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
        except OSError:
            self.acquired = False
        return self.acquired

    def release(self) -> None:
        if not self._handle:
            return
        try:
            if self.acquired:
                if msvcrt is not None:
                    self._handle.seek(0)
                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - Linux/macOS
                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
            self.acquired = False


class WeightedProfileCycle:
    """Fila determinística de perfis de anomalia (A/B/C).

    A fila é montada por maior resto em um horizonte de 100 anomalias e
    embaralhada com uma semente própria. Isso evita que um regime com poucas
    anomalias (Cruzeiro, 5%) use sempre o mesmo perfil e mantém a distribuição
    configurada mesmo em execuções curtas.
    """

    HORIZON = 100

    def __init__(self, weights: dict[str, float], rng: np.random.Generator) -> None:
        self.weights = {key: float(value) for key, value in weights.items()}
        if set(self.weights) != set(ANOMALY_PROFILE_LABELS):
            raise ValueError("Os perfis de anomalia devem ser exatamente A, B e C.")
        if not math.isclose(sum(self.weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError("Os pesos dos perfis de anomalia devem totalizar 1.")
        self.rng = rng
        self._queue: list[str] = []
        self._refill()

    def _refill(self) -> None:
        raw = {key: self.weights[key] * self.HORIZON for key in self.weights}
        counts = {key: int(math.floor(value)) for key, value in raw.items()}
        remaining = self.HORIZON - sum(counts.values())
        order = sorted(
            raw,
            key=lambda key: (raw[key] - counts[key], key),
            reverse=True,
        )
        for key in order[:remaining]:
            counts[key] += 1
        items = [key for key in ("A", "B", "C") for _ in range(counts[key])]
        self.rng.shuffle(items)
        self._queue = items

    def next(self) -> str:
        if not self._queue:
            self._refill()
        return self._queue.pop(0)


@dataclass
class EquipmentState:
    """Estado físico interno de um equipamento (não reiniciado por troca)."""

    equipment: str
    load: float
    rotation: float
    temperature: float
    vibration: float
    pressure: float
    acoustic: float
    current: float
    hours: float
    phase: float
    drift_load: float = 0.0
    drift_temperature: float = 0.0
    drift_vibration: float = 0.0
    noise_rotation: float = 0.0
    noise_pressure: float = 0.0
    noise_acoustic: float = 0.0
    noise_current: float = 0.0
    # Componentes de anomalia persistidos entre leituras. Ao voltar ao perfil
    # nominal eles decaem gradualmente, evitando saltos e picos isolados.
    thermal_offset: float = 0.0
    vibration_offset: float = 0.0
    pressure_offset: float = 0.0
    acoustic_offset: float = 0.0
    current_offset: float = 0.0


def _anchor_points() -> list[tuple[float, dict[str, float]]]:
    return sorted(
        ((profile["load_index"], profile) for profile in REGIME_PROFILES.values()),
        key=lambda item: item[0],
    )


_ANCHORS = _anchor_points()


def equilibrium_for_load(load: float) -> dict[str, float]:
    """Interpola os alvos de equilíbrio entre os três regimes ancorados."""
    clamped = min(max(load, _ANCHORS[0][0]), _ANCHORS[-1][0])
    for (load_a, profile_a), (load_b, profile_b) in zip(_ANCHORS, _ANCHORS[1:]):
        if clamped <= load_b:
            fraction = 0.0 if load_b == load_a else (clamped - load_a) / (load_b - load_a)
            return {
                field: profile_a[field] + fraction * (profile_b[field] - profile_a[field])
                for field in SENSOR_FIELDS
            }
    return {field: _ANCHORS[-1][1][field] for field in SENSOR_FIELDS}


def _alpha(dt_seconds: float, tau_seconds: float) -> float:
    return 1.0 - math.exp(-max(dt_seconds, 0.0) / tau_seconds)


def anomaly_offset_targets(
    regime: str, perfil_anomalia: str | None
) -> dict[str, float]:
    """Afastamentos-alvo dos sensores para um perfil de anomalia.

    O perfil nominal zera todos os componentes. O perfil anormal usa os
    afastamentos estatísticos do dataset, multiplicados pela intensidade
    configurada para o regime. A função é separada para permitir auditoria e
    testes sem executar a dinâmica temporal.
    """
    fields = (
        "temperatura_mancal_c",
        "vibracao_rms_mms",
        "pressao_oleo_bar",
        "emissao_acustica_db",
        "corrente_eletrica_amp",
    )
    targets = {field: 0.0 for field in fields}
    if perfil_anomalia is None:
        return targets
    if perfil_anomalia not in ANOMALY_PROFILE_LABELS:
        raise ValueError(f"Perfil de anomalia inválido: {perfil_anomalia!r}")
    config = REGIME_CONFIG[regime]
    intensity = float(config["anomaly_intensity"])
    for field, delta in ANOMALY_PROFILE_DELTAS[regime][perfil_anomalia].items():
        targets[field] = float(delta) * intensity
    return targets


class TelemetrySimulator:
    """Gerador com estado temporal compartilhado entre ciclos."""

    def __init__(
        self,
        equipments: tuple[str, ...] = EQUIPMENTS,
        initial_hours: dict[str, float] | None = None,
        regime: str = DEFAULT_REGIME,
        seed: int = 42,
    ) -> None:
        if regime not in REGIMES:
            raise ValueError(f"Regime inicial inválido: {regime!r}.")
        self._seed = int(seed)
        self.rng = np.random.default_rng(seed)
        self.schedule_rng = np.random.default_rng(self._seed + 104729)
        self.equipments = equipments
        self.regime = regime
        self.previous_regime: str | None = None
        self.regime_changed_at = datetime.now()
        self.elapsed_seconds = 0.0
        self._block_plans: dict[str, list[tuple[str, str | None]]] = {
            equipment: [] for equipment in equipments
        }
        self._profile_cycles: dict[str, WeightedProfileCycle] = {
            equipment: self._new_profile_cycle(index)
            for index, equipment in enumerate(equipments)
        }
        hours = initial_hours or {}
        self.states: dict[str, EquipmentState] = {
            equipment: self._initial_state(
                equipment, float(hours.get(equipment, 0.0)), index
            )
            for index, equipment in enumerate(equipments)
        }

    def _new_profile_cycle(self, index: int) -> WeightedProfileCycle:
        weights = REGIME_CONFIG[self.regime]["anomaly_weights"]
        return WeightedProfileCycle(
            weights,
            np.random.default_rng(self._seed + 7919 + index * 997),
        )

    def _reset_profile_schedule(self) -> None:
        """Reinicia apenas o sorteio de perfis; o estado físico é preservado."""
        for index, equipment in enumerate(self.equipments):
            self._block_plans[equipment] = []
            self._profile_cycles[equipment] = self._new_profile_cycle(index)

    def _build_block_plan(self, equipment: str) -> list[tuple[str, str | None]]:
        """Cria um bloco com a proporção exata configurada.

        As anomalias ficam em uma sequência contígua dentro do bloco, com início
        sorteado. Isso preserva a proporção exigida e permite que a dinâmica
        temporal desenvolva o desvio por alguns ciclos, em vez de produzir um
        pico isolado cercado por leituras nominais. A posição dos perfis A/B/C
        dentro da sequência também é embaralhada.
        """
        config = REGIME_CONFIG[self.regime]
        block_size = int(config["block_size"])
        nominal_count = int(round(float(config["nominal_ratio"]) * block_size))
        anomaly_count = block_size - nominal_count
        plan: list[tuple[str, str | None]] = [("nominal", None)] * block_size

        profiles = [
            self._profile_cycles[equipment].next() for _ in range(anomaly_count)
        ]
        order = self.schedule_rng.permutation(anomaly_count)
        profiles = [profiles[int(index)] for index in order]
        start = int(self.schedule_rng.integers(0, block_size - anomaly_count + 1))
        for offset, profile in enumerate(profiles):
            plan[start + offset] = ("anormal", profile)
        return plan

    def _next_profile(self, equipment: str) -> tuple[str, str | None]:
        plan = self._block_plans[equipment]
        if not plan:
            plan = self._build_block_plan(equipment)
            self._block_plans[equipment] = plan
        return plan.pop(0)

    def _initial_state(
        self, equipment: str, hours: float, index: int
    ) -> EquipmentState:
        profile = REGIME_PROFILES[self.regime]
        return EquipmentState(
            equipment=equipment,
            load=profile["load_index"],
            rotation=profile["rotacao_rpm"],
            temperature=profile["temperatura_mancal_c"],
            vibration=profile["vibracao_rms_mms"],
            pressure=profile["pressao_oleo_bar"],
            acoustic=profile["emissao_acustica_db"],
            current=profile["corrente_eletrica_amp"],
            hours=hours,
            phase=0.9 * index + float(self.rng.uniform(-0.3, 0.3)),
        )

    def set_regime(self, regime: str) -> bool:
        """Troca o alvo preservando integralmente o estado físico."""
        if regime not in REGIMES:
            raise ValueError(
                f"Regime inválido: {regime!r}. Valores aceitos: {', '.join(REGIMES)}."
            )
        if regime == self.regime:
            return False
        self.previous_regime = self.regime
        self.regime = regime
        self.regime_changed_at = datetime.now()
        self._reset_profile_schedule()
        return True

    def _ar1(
        self, previous: float, sigma: float, tau_seconds: float, dt_seconds: float
    ) -> float:
        rho = math.exp(-max(dt_seconds, 0.0) / tau_seconds)
        step_sigma = sigma * math.sqrt(max(0.0, 1.0 - rho * rho))
        return rho * previous + step_sigma * float(self.rng.normal())

    def _step_equipment(
        self,
        state: EquipmentState,
        dt_seconds: float,
        perfil_sintetico: str,
        perfil_anomalia: str | None,
    ) -> dict[str, float]:
        profile = REGIME_PROFILES[self.regime]
        noise_scale = profile["noise_scale"]
        elapsed = self.elapsed_seconds

        # 0) Componentes do perfil gerado. O perfil nominal puxa os componentes
        # para zero; o anormal puxa para o afastamento estatístico configurado.
        # A resposta de primeira ordem mantém persistência e retorno gradual.
        anomaly_target = (
            anomaly_offset_targets(self.regime, perfil_anomalia)
            if perfil_sintetico == "anormal"
            else anomaly_offset_targets(self.regime, None)
        )
        state.thermal_offset += _alpha(dt_seconds, TAU_ANOMALY_THERMAL_S) * (
            anomaly_target["temperatura_mancal_c"] - state.thermal_offset
        )
        state.vibration_offset += _alpha(dt_seconds, TAU_ANOMALY_VIBRATION_S) * (
            anomaly_target["vibracao_rms_mms"] - state.vibration_offset
        )
        state.pressure_offset += _alpha(dt_seconds, TAU_ANOMALY_PRESSURE_S) * (
            anomaly_target["pressao_oleo_bar"] - state.pressure_offset
        )
        state.acoustic_offset += _alpha(dt_seconds, TAU_ANOMALY_ACOUSTIC_S) * (
            anomaly_target["emissao_acustica_db"] - state.acoustic_offset
        )
        state.current_offset += _alpha(dt_seconds, TAU_ANOMALY_CURRENT_S) * (
            anomaly_target["corrente_eletrica_amp"] - state.current_offset
        )

        # 1) Carga latente: aproxima do alvo do regime com inércia e oscilação
        # operacional lenta. Não é um sensor; serve apenas de variável interna.
        state.drift_load = self._ar1(
            state.drift_load, SIGMA_LOAD, TAU_LOAD_NOISE_S, dt_seconds
        )
        load_target = (
            profile["load_index"]
            + 0.006 * math.sin(elapsed / 17.0 + state.phase)
            + state.drift_load
        )
        state.load += _alpha(dt_seconds, TAU_LOAD_S) * (load_target - state.load)
        equilibrium = equilibrium_for_load(state.load)

        # 2) Rotação acompanha a carga com pequena oscilação de governador.
        rotation_target = equilibrium["rotacao_rpm"] + 5.0 * math.sin(
            elapsed / 9.0 + state.phase * 1.7
        )
        state.rotation += _alpha(dt_seconds, TAU_RPM_S) * (
            rotation_target - state.rotation
        )
        state.noise_rotation = self._ar1(
            state.noise_rotation, SIGMA_RPM, TAU_RPM_NOISE_S, dt_seconds
        )
        rotation_reading = state.rotation + state.noise_rotation

        # 3) Vibração RMS: responde à carga, mas com relação própria (não é
        # proporcional à temperatura) e ruído de medição correlacionado.
        state.vibration += _alpha(dt_seconds, TAU_VIBRATION_S) * (
            equilibrium["vibracao_rms_mms"] - state.vibration
        )
        state.drift_vibration = self._ar1(
            state.drift_vibration,
            SIGMA_VIBRATION * noise_scale,
            TAU_VIBRATION_NOISE_S,
            dt_seconds,
        )
        vibration_oscillation = (
            0.025 * noise_scale * math.sin(elapsed / 2.7 + state.phase * 1.3)
        )
        vibration_reading = (
            state.vibration
            + state.drift_vibration
            + vibration_oscillation
            + state.vibration_offset
        )

        # 4) Temperatura do mancal: inércia térmica de primeira ordem. O
        # componente de anomalia é somado ao alvo e à leitura final.
        thermal_target = (
            equilibrium["temperatura_mancal_c"]
            + 0.18 * (vibration_reading - equilibrium["vibracao_rms_mms"])
        )
        state.temperature += _alpha(dt_seconds, TAU_THERMAL_S) * (
            thermal_target - state.temperature
        )
        state.drift_temperature = self._ar1(
            state.drift_temperature,
            SIGMA_TEMP_DRIFT,
            TAU_TEMP_DRIFT_S,
            dt_seconds,
        )
        temperature_reading = (
            state.temperature
            + state.drift_temperature
            + state.thermal_offset
            + float(self.rng.normal(0.0, SIGMA_TEMP_MEASUREMENT))
        )

        # 5) Pressão do óleo: acompanha a carga, com ruído pequeno. A queda de
        # pressão do perfil térmico é aplicada como componente persistente.
        state.pressure += _alpha(dt_seconds, TAU_PRESSURE_S) * (
            equilibrium["pressao_oleo_bar"] - state.pressure
        )
        state.noise_pressure = self._ar1(
            state.noise_pressure, SIGMA_PRESSURE, TAU_PRESSURE_NOISE_S, dt_seconds
        )
        pressure_reading = state.pressure + state.noise_pressure + state.pressure_offset

        # 6) Emissão acústica: relacionada à vibração e à rotação nos dados.
        acoustic_target = (
            equilibrium["emissao_acustica_db"]
            + 0.55 * (vibration_reading - equilibrium["vibracao_rms_mms"])
            + 0.002 * (rotation_reading - equilibrium["rotacao_rpm"])
        )
        state.acoustic += _alpha(dt_seconds, TAU_ACOUSTIC_S) * (
            acoustic_target - state.acoustic
        )
        state.noise_acoustic = self._ar1(
            state.noise_acoustic,
            SIGMA_ACOUSTIC * noise_scale,
            TAU_ACOUSTIC_NOISE_S,
            dt_seconds,
        )
        acoustic_reading = (
            state.acoustic + state.noise_acoustic + state.acoustic_offset
        )

        # 7) Corrente elétrica: proxy de esforço/carga, correlacionada à rotação.
        current_target = (
            equilibrium["corrente_eletrica_amp"]
            + 0.012 * (rotation_reading - equilibrium["rotacao_rpm"])
        )
        state.current += _alpha(dt_seconds, TAU_CURRENT_S) * (
            current_target - state.current
        )
        state.noise_current = self._ar1(
            state.noise_current,
            SIGMA_CURRENT * noise_scale,
            TAU_CURRENT_NOISE_S,
            dt_seconds,
        )
        current_reading = (
            state.current + state.noise_current + state.current_offset
        )

        state.hours += dt_seconds / 3600.0

        values = {
            "temperatura_mancal_c": temperature_reading,
            "vibracao_rms_mms": vibration_reading,
            "pressao_oleo_bar": pressure_reading,
            "rotacao_rpm": rotation_reading,
            "emissao_acustica_db": acoustic_reading,
            "corrente_eletrica_amp": current_reading,
        }
        return {
            field: round(
                float(np.clip(value, *GENERATION_LIMITS[field])), 3
            )
            for field, value in values.items()
        }

    def step(self, dt_seconds: float = 5.0) -> list[dict[str, Any]]:
        """Gera uma leitura por equipamento e avança o estado."""
        if dt_seconds <= 0:
            raise ValueError("O intervalo entre leituras deve ser maior que zero.")
        timestamp = _now_iso()
        changed_at = self.regime_changed_at.isoformat(timespec="seconds")
        readings: list[dict[str, Any]] = []
        self.elapsed_seconds += dt_seconds
        for equipment in self.equipments:
            state = self.states[equipment]
            perfil_sintetico, perfil_anomalia = self._next_profile(equipment)
            values = self._step_equipment(
                state, dt_seconds, perfil_sintetico, perfil_anomalia
            )
            readings.append(
                {
                    "timestamp": timestamp,
                    "id_equipamento": equipment,
                    "modo_operacao": self.regime,
                    "regime_operacional": self.regime,
                    "regime_anterior": self.previous_regime,
                    "regime_alterado_em": changed_at,
                    "origem_leitura": "simulada",
                    "perfil_sintetico": perfil_sintetico,
                    "perfil_anomalia": perfil_anomalia,
                    "horas_operacao_acumuladas": round(state.hours, 2),
                    **values,
                }
            )
        return readings


def _initial_hours() -> dict[str, float]:
    """Preserva a contagem de horas a partir do dataset original (não alterado)."""
    path = ROOT_DIR / "data" / "raw" / "dados_sensores_aeromotion.csv"
    try:
        data = pd.read_csv(path)
        return {
            equipment: float(
                data.loc[data["id_equipamento"] == equipment, "horas_operacao_acumuladas"].max()
            )
            for equipment in EQUIPMENTS
        }
    except Exception:  # noqa: BLE001 - o simulador pode operar mesmo sem o CSV
        logging.warning("Não foi possível ler as horas do dataset; iniciando em zero.")
        return {equipment: 0.0 for equipment in EQUIPMENTS}


def _sleep_with_stop_check(seconds: float, control_path: Path) -> bool:
    """Dorme em fatias curtas para reagir rapidamente ao comando de parada."""
    deadline = time.monotonic() + seconds
    while True:
        control = read_control(control_path)
        if control and control.get("action") == "stop":
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(1.0, remaining))


def run(args: argparse.Namespace) -> int:
    runtime_dir = Path(args.runtime_dir) if args.runtime_dir else RUNTIME_DIR
    control_path = runtime_dir / "simulator_control.json"
    state_path = runtime_dir / "simulator_state.json"
    lock_path = runtime_dir / "simulator.lock"

    lock = SimulatorLock(lock_path)
    if not lock.acquire():
        logging.error(
            "Já existe um simulador em execução (lock: %s). Encerrando esta instância.",
            lock_path,
        )
        return 0

    try:
        control = read_control(control_path)
        if control and control.get("regime") in REGIMES:
            initial_regime = str(control["regime"])
        elif args.regime in REGIMES:
            initial_regime = str(args.regime)
        else:
            initial_regime = DEFAULT_REGIME

        # Substitui um eventual comando de parada anterior por execução.
        write_control(
            initial_regime,
            action="run",
            path=control_path,
            requested_by="simulator",
        )

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )

        simulator = TelemetrySimulator(
            EQUIPMENTS,
            initial_hours=_initial_hours(),
            regime=initial_regime,
            seed=args.seed,
        )
        started_at = _now_iso()
        state: dict[str, Any] = {
            "pid": os.getpid(),
            "status": "running",
            "regime": initial_regime,
            "regime_anterior": None,
            "regime_changed_at": started_at,
            "started_at": started_at,
            "last_cycle_at": started_at,
            "cycle": 0,
            "interval_seconds": float(args.intervalo),
            "api_url": args.api_url,
            "origem": "simulada",
            "last_error": None,
            "version": 2,
        }
        write_state(state, state_path)
        logging.info(
            "Simulador iniciado (PID %s) no regime %s, intervalo %.1fs.",
            os.getpid(),
            initial_regime,
            args.intervalo,
        )

        session = requests.Session()
        cycle = 0
        while not args.quantidade or cycle < args.quantidade:
            cycle += 1
            cycle_started = time.monotonic()
            last_error: str | None = None

            control = read_control(control_path)
            if control:
                if control.get("action") == "stop":
                    logging.info("Comando de parada recebido.")
                    break
                requested = control.get("regime")
                if requested not in REGIMES:
                    last_error = f"Regime inválido no arquivo de controle: {requested!r}"
                    logging.warning(last_error)
                elif simulator.set_regime(str(requested)):
                    logging.info(
                        "Regime alterado: %s -> %s (estado preservado).",
                        simulator.previous_regime,
                        simulator.regime,
                    )

            for reading in simulator.step(float(args.intervalo)):
                try:
                    response = session.post(
                        f"{args.api_url.rstrip('/')}/predict",
                        json=reading,
                        timeout=10,
                    )
                    if response.ok:
                        result = response.json()
                        logging.info(
                            "%s | %s | %s | %s%s -> HTTP %s | classe=%s",
                            reading["timestamp"],
                            reading["id_equipamento"],
                            reading["regime_operacional"],
                            reading["perfil_sintetico"],
                            f" ({reading['perfil_anomalia']})"
                            if reading.get("perfil_anomalia")
                            else "",
                            response.status_code,
                            result.get("nome_classe_prevista"),
                        )
                    else:
                        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                        logging.warning(last_error)
                except requests.RequestException as error:
                    last_error = f"Falha de comunicação com a API: {error}"
                    logging.warning(last_error)

            state.update(
                {
                    "status": "running",
                    "regime": simulator.regime,
                    "regime_anterior": simulator.previous_regime,
                    "regime_changed_at": simulator.regime_changed_at.isoformat(
                        timespec="seconds"
                    ),
                    "last_cycle_at": _now_iso(),
                    "cycle": cycle,
                    "last_error": last_error,
                }
            )
            write_state(state, state_path)

            if args.quantidade and cycle >= args.quantidade:
                break
            remaining = float(args.intervalo) - (time.monotonic() - cycle_started)
            if remaining > 0 and _sleep_with_stop_check(remaining, control_path):
                logging.info("Comando de parada recebido durante a espera.")
                break
    finally:
        try:
            state.update({"status": "stopped", "stopped_at": _now_iso()})
            write_state(state, state_path)
        except Exception:  # noqa: BLE001
            pass
        lock.release()
        logging.info("Simulador encerrado com segurança.")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Envia leituras simuladas por regime operacional à API AeroMotion."
    )
    parser.add_argument("--api-url", default=os.getenv("AEROMOTION_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument(
        "--regime",
        default=None,
        choices=REGIMES,
        help="Regime inicial quando ainda não existe comando salvo (padrão: Cruzeiro).",
    )
    parser.add_argument(
        "--intervalo",
        type=float,
        default=float(os.getenv("SIMULATOR_INTERVAL", "5")),
        help="Intervalo entre ciclos em segundos.",
    )
    parser.add_argument(
        "--quantidade", type=int, default=0, help="0 executa continuamente."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--runtime-dir",
        default=None,
        help="Diretório de controle/estado (padrão: data/runtime).",
    )
    args = parser.parse_args()
    if args.intervalo <= 0:
        parser.error("--intervalo deve ser maior que zero.")
    if args.quantidade < 0:
        parser.error("--quantidade não pode ser negativa.")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
