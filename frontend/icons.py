"""Ícones SVG Lucide para o dashboard AeroMotion Dynamics.

Todos os ícones são inline SVG com traço consistente (stroke-width=1.75).
Nenhum emoji é utilizado em nenhuma parte do dashboard.
"""
from __future__ import annotations

_STROKE = "#627D98"  # text_secondary da paleta industrial clara
_W = 18             # tamanho padrão em pixels


def _svg(path_d: str, color: str = _STROKE, size: int = _W, extra_attrs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" {extra_attrs}>'
        f'{path_d}</svg>'
    )


def thermometer(color: str = _STROKE, size: int = _W) -> str:
    """Termômetro — usado para temperatura do mancal e falha de superaquecimento."""
    return _svg(
        '<path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>',
        color, size,
    )


def activity(color: str = _STROKE, size: int = _W) -> str:
    """Linha de atividade / pulso — usada para vibração RMS e recall."""
    return _svg(
        '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
        color, size,
    )


def gauge(color: str = _STROKE, size: int = _W) -> str:
    """Manômetro / medidor — usado para pressão do óleo e probabilidade."""
    return _svg(
        '<path d="m12 14 4-4"/>'
        '<path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
        color, size,
    )


def server(color: str = _STROKE, size: int = _W) -> str:
    """Servidor — usado para estado da API."""
    return _svg(
        '<rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>'
        '<rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>'
        '<line x1="6" x2="6.01" y1="6" y2="6"/>'
        '<line x1="6" x2="6.01" y1="18" y2="18"/>',
        color, size,
    )


def wifi(color: str = _STROKE, size: int = _W) -> str:
    """Conexão / Sinal de rede — usado para estado da conexão."""
    return _svg(
        '<path d="M5 12.55a11 11 0 0 1 14.08 0"/>'
        '<path d="M1.42 9a16 16 0 0 1 21.16 0"/>'
        '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>'
        '<line x1="12" x2="12.01" y1="20" y2="20"/>',
        color, size,
    )


def play(color: str = _STROKE, size: int = _W) -> str:
    """Play — usado para iniciar simulação e status ativo."""
    return _svg(
        '<polygon points="6 3 20 12 6 21 6 3"/>',
        color, size,
    )


def square_stop(color: str = _STROKE, size: int = _W) -> str:
    """Stop — usado para parar simulação e status inativo."""
    return _svg(
        '<rect width="14" height="14" x="5" y="5" rx="2"/>',
        color, size,
    )


def alert_triangle(color: str = _STROKE, size: int = _W) -> str:
    """Alerta / Triângulo — usado para falhas e anomalias."""
    return _svg(
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/>'
        '<line x1="12" x2="12" y1="9" y2="13"/>'
        '<line x1="12" x2="12.01" y1="17" y2="17"/>',
        color, size,
    )


def chart_line(color: str = _STROKE, size: int = _W) -> str:
    """Gráfico de linhas — usado para telemetria."""
    return _svg(
        '<path d="M3 3v18h18"/>'
        '<path d="m19 9-5 5-4-4-3 3"/>',
        color, size,
    )


def database(color: str = _STROKE, size: int = _W) -> str:
    """Banco de dados — usado para histórico."""
    return _svg(
        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
        '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
        color, size,
    )


def cpu(color: str = _STROKE, size: int = _W) -> str:
    """Processador / Equipamento — usado para turbinas e predição."""
    return _svg(
        '<rect width="16" height="16" x="4" y="4" rx="2"/>'
        '<rect width="6" height="6" x="9" y="9" rx="1"/>'
        '<path d="M15 2v2M9 2v2M15 20v2M9 20v2M2 15h2M2 9h2M20 15h2M20 9h2"/>',
        color, size,
    )


def layers(color: str = _STROKE, size: int = _W) -> str:
    """Camadas — usado para navegação e seções."""
    return _svg(
        '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/>'
        '<path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>'
        '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
        color, size,
    )


def bar_chart(color: str = _STROKE, size: int = _W) -> str:
    """Gráfico de barras — usado para métricas de avaliação e feature importance."""
    return _svg(
        '<line x1="18" x2="18" y1="20" y2="10"/>'
        '<line x1="12" x2="12" y1="20" y2="4"/>'
        '<line x1="6" x2="6" y1="20" y2="14"/>'
        '<line x1="2" x2="22" y1="20" y2="20"/>',
        color, size,
    )


def settings(color: str = _STROKE, size: int = _W) -> str:
    """Configurações / Controles."""
    return _svg(
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        '<circle cx="12" cy="12" r="3"/>',
        color, size,
    )


def check_circle(color: str = _STROKE, size: int = _W) -> str:
    """Círculo de confirmação — usado para Operação Normal."""
    return _svg(
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
        '<polyline points="22 4 12 14.01 9 11.01"/>',
        color, size,
    )


def x_circle(color: str = _STROKE, size: int = _W) -> str:
    """Círculo com X — usado para erro e desconexão."""
    return _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="15" x2="9" y1="9" y2="15"/>'
        '<line x1="9" x2="15" y1="9" y2="15"/>',
        color, size,
    )


def clock(color: str = _STROKE, size: int = _W) -> str:
    """Relógio — usado para data/horário da última atualização."""
    return _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<polyline points="12 6 12 12 16 14"/>',
        color, size,
    )


def zap(color: str = _STROKE, size: int = _W) -> str:
    """Raio — usado para Desgaste de Rolamento."""
    return _svg(
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
        color, size,
    )


def info(color: str = _STROKE, size: int = _W) -> str:
    """Informação — usado para avisos de aquecimento."""
    return _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" x2="12" y1="8" y2="12"/>'
        '<line x1="12" x2="12.01" y1="16" y2="16"/>',
        color, size,
    )


def rotate_cw(color: str = _STROKE, size: int = _W) -> str:
    """Rotação — usado para rotação do eixo em RPM."""
    return _svg(
        '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>'
        '<path d="M21 3v5h-5"/>',
        color, size,
    )


def volume_2(color: str = _STROKE, size: int = _W) -> str:
    """Som — usado para emissão acústica."""
    return _svg(
        '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>'
        '<path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>'
        '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
        color, size,
    )


def power(color: str = _STROKE, size: int = _W) -> str:
    """Energia — usado para corrente elétrica."""
    return _svg(
        '<path d="M12 2v10"/>'
        '<path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>',
        color, size,
    )

