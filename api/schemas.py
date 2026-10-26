"""Contratos HTTP da API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


EQUIPAMENTOS = {"TURB-101", "TURB-102", "TURB-103", "TURB-104"}
MODOS = {"Cruzeiro", "Carga_Media", "Carga_Alta"}
REGIMES = ("Cruzeiro", "Carga_Media", "Carga_Alta")


class SensorReading(BaseModel):
    timestamp: datetime
    id_equipamento: str = Field(pattern=r"^TURB-10[1-4]$")
    # ``modo_operacao`` é o nome histórico do regime no dataset e no modelo.
    modo_operacao: Literal["Cruzeiro", "Carga_Media", "Carga_Alta"]
    horas_operacao_acumuladas: float = Field(ge=0, le=10000)
    temperatura_mancal_c: float = Field(ge=-20, le=200)
    vibracao_rms_mms: float = Field(ge=0, le=100)
    pressao_oleo_bar: float = Field(ge=0, le=20)
    rotacao_rpm: float = Field(ge=0, le=10000)
    emissao_acustica_db: float = Field(ge=0, le=160)
    corrente_eletrica_amp: float = Field(ge=0, le=500)
    cenario_simulado: str | None = Field(
        default=None, description="Metadado legado de cenário de teste."
    )
    # Regime operacional separado da classe predita. Quando omitido, assume o
    # modo_operacao recebido (compatibilidade com clientes antigos).
    regime_operacional: Literal["Cruzeiro", "Carga_Media", "Carga_Alta"] | None = None
    regime_anterior: Literal["Cruzeiro", "Carga_Media", "Carga_Alta"] | None = None
    regime_alterado_em: datetime | None = None
    origem_leitura: Literal["simulada", "real", "desconhecida"] = Field(
        default="desconhecida",
        description="Distingue telemetria sintética de leitura real de campo.",
    )
    # Perfil do gerador, separado da classe predita. ``nominal``/``anormal``
    # descrevem a intenção da amostra sintética; não são rótulos de falha.
    perfil_sintetico: Literal["nominal", "anormal"] | None = Field(
        default=None,
        description="Perfil de geração da amostra sintética (não é a classe do modelo).",
    )
    perfil_anomalia: Literal["A", "B", "C"] | None = Field(
        default=None,
        description="Perfil de anomalia: A térmica, B vibração, C combinada.",
    )

    @field_validator("timestamp", "regime_alterado_em")
    @classmethod
    def timestamp_without_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=None) if value.tzinfo else value

    @model_validator(mode="after")
    def fill_regime(self) -> "SensorReading":
        if self.regime_operacional is None:
            self.regime_operacional = self.modo_operacao
        if self.perfil_sintetico == "nominal":
            self.perfil_anomalia = None
        return self


class BatchRequest(BaseModel):
    leituras: list[SensorReading] = Field(min_length=1, max_length=500)


class RegimeCommand(BaseModel):
    """Comando de regime operacional enviado pelo dashboard."""

    regime: Literal["Cruzeiro", "Carga_Media", "Carga_Alta"]
