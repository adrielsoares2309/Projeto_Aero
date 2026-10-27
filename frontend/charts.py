"""Gráficos Plotly para o dashboard AeroMotion Dynamics.

Paleta de Cores Industrial de Alto Contraste:
- Área de plotagem (canvas): `#FFFFFF` (fundo branco com grade e moldura contrastantes)
- Fundo externo (card): `#FFFFFF`
- Borda e eixos: `#475569` com mirror=True (quadro fechado e nítido)
- Linhas de grade: `#CBD5E1` (perfeitamente visíveis sobre o canvas)
- Temperatura do mancal: Linha azul-escura `#1565C0` sólida e espessa (3px) + marcadores
- Vibração RMS: Linha laranja escura `#E65100` sólida e espessa (3px) + marcadores
- Pressão do óleo: Linha roxo escuro `#6A1B9A` sólida e espessa (3px) + marcadores
- Limites operacionais máximos: Linha vermelha tracejada `#C62828` (2px)
- Limites operacionais mínimos: Linha âmbar pontilhada `#B77900` (2px)
- Leituras anômalas: Marcadores destacados em vermelho `#C62828` com contorno branco
- Zero emojis em qualquer visualização ou anotação.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from frontend.styles import PLOTLY_TEMPLATE

# --------------------------------------------------------------------------- #
# Paleta Oficial de Alto Contraste                                            #
# --------------------------------------------------------------------------- #
CHART_PALETTE = {
    "blue": "#1565C0",          # Temperatura do mancal e séries principais
    "orange": "#E65100",        # Vibração RMS e séries secundárias
    "purple": "#6A1B9A",        # Pressão do óleo e variáveis adicionais
    "green": "#16803C",         # Condição normal e faixa segura
    "amber": "#B77900",         # Alertas e atenção
    "red": "#C62828",           # Falhas críticas e fora dos limites
    "teal": "#00796B",          # Séries adicionais e destaque
    "slate": "#475569",         # Eixos e bordas dos gráficos
    "grid": "#CBD5E1",          # Linhas de grade nítidas
    "plot_bg": "#FFFFFF",       # Fundo branco da área de plotagem
    "paper_bg": "#FFFFFF",      # Fundo do cartão externo
    "font_heading": "#0F172A",  # Títulos e labels principais
    "font_body": "#1E293B",     # Rótulos de eixos e valores
    "safe_fill": "rgba(22, 128, 60, 0.09)",  # Faixa operacional segura
}

# Limites operacionais definidos para turbinas industriais
SENSOR_LIMITS = {
    "temperatura_mancal_c": (45.0, 85.0),
    "vibracao_rms_mms": (1.0, 4.5),
    "pressao_oleo_bar": (3.5, 5.2),
}

REGIME_LABELS = {
    "Cruzeiro": "Cruzeiro",
    "Carga_Media": "Carga Média",
    "Carga_Alta": "Carga Alta",
}
REGIME_COLORS = {
    "Cruzeiro": CHART_PALETTE["blue"],
    "Carga_Media": CHART_PALETTE["amber"],
    "Carga_Alta": CHART_PALETTE["orange"],
}

_CHART_HEIGHT = 280
_COMPACT_HEIGHT = 240


def _add_regime_transitions(fig: go.Figure, sub: pd.DataFrame) -> None:
    """Marca trocas de regime com linhas verticais discretas e rotuladas.

    A transição é identificada pela coluna ``regime`` (ou ``modo_operacao``),
    nunca pela classe prevista pelo modelo.
    """
    column = "regime" if "regime" in sub.columns else ("modo_operacao" if "modo_operacao" in sub.columns else None)
    if column is None or "timestamp" not in sub.columns:
        return

    ordered = sub.dropna(subset=["timestamp"]).sort_values("timestamp")
    if len(ordered) < 2:
        return

    labels = ordered[column].tolist()
    moments = ordered["timestamp"].tolist()
    transitions = [
        (moments[index], labels[index])
        for index in range(1, len(labels))
        if pd.notna(labels[index]) and labels[index] != labels[index - 1]
    ]
    for timestamp, regime in transitions[-8:]:
        color = REGIME_COLORS.get(str(regime), CHART_PALETTE["slate"])
        fig.add_vline(
            x=timestamp,
            line_dash="dot",
            line_color=color,
            line_width=1.4,
            annotation_text=REGIME_LABELS.get(str(regime), str(regime).replace("_", " ")),
            annotation_position="top left",
            annotation_font_size=9,
            annotation_font_color=color,
            annotation_bgcolor="rgba(255,255,255,0.85)",
        )


# --------------------------------------------------------------------------- #
# Layout Base com Canvas Nítido e Quadro Delimitado                           #
# --------------------------------------------------------------------------- #
_BASE_LAYOUT: dict[str, Any] = dict(
    template=PLOTLY_TEMPLATE,
    paper_bgcolor=CHART_PALETTE["paper_bg"],
    plot_bgcolor=CHART_PALETTE["plot_bg"],
    margin=dict(l=60, r=25, t=32, b=45),
    font=dict(family="'Inter', -apple-system, sans-serif", size=11, color=CHART_PALETTE["font_heading"]),
    xaxis=dict(
        gridcolor=CHART_PALETTE["grid"],
        gridwidth=1,
        showgrid=True,
        zeroline=False,
        showline=True,
        linecolor=CHART_PALETTE["slate"],
        linewidth=1.5,
        mirror=True,  # Fecha a moldura do gráfico para definição visual perfeita
        tickfont=dict(family="'Inter', sans-serif", size=10, color=CHART_PALETTE["font_body"]),
        tickformat="%H:%M:%S",
        title_font=dict(family="'Inter', sans-serif", size=11, color=CHART_PALETTE["font_heading"]),
    ),
    yaxis=dict(
        gridcolor=CHART_PALETTE["grid"],
        gridwidth=1,
        showgrid=True,
        zeroline=False,
        showline=True,
        linecolor=CHART_PALETTE["slate"],
        linewidth=1.5,
        mirror=True,  # Fecha a moldura do gráfico
        tickfont=dict(family="'Inter', sans-serif", size=10, color=CHART_PALETTE["font_body"]),
        title_font=dict(family="'Inter', sans-serif", size=11, color=CHART_PALETTE["font_heading"]),
    ),
    legend=dict(
        font=dict(family="'Inter', sans-serif", size=10, color=CHART_PALETTE["font_heading"]),
        bgcolor="rgba(255, 255, 255, 0.95)",
        bordercolor=CHART_PALETTE["grid"],
        borderwidth=1,
        orientation="h",
        yanchor="bottom",
        y=1.03,
        xanchor="left",
        x=0,
    ),
    hoverlabel=dict(
        bgcolor="#FFFFFF",
        bordercolor=CHART_PALETTE["slate"],
        font_family="'Inter', sans-serif",
        font_size=11,
        font_color=CHART_PALETTE["font_heading"],
    ),
)


# --------------------------------------------------------------------------- #
# 1. Gráfico de Temperatura do Mancal (°C)                                     #
# --------------------------------------------------------------------------- #
def temperature_chart(df: pd.DataFrame, equipment: str | None = None) -> go.Figure:
    """Gráfico temporal da temperatura do mancal.
    
    - Canvas branco com grade e moldura contrastantes (#475569)
    - Linha azul-escura (#1565C0) sólida e espessa (3px)
    - Faixa segura (45.0 a 85.0 °C) destacada
    - Limite máximo em linha vermelha tracejada (#C62828, 2px)
    - Limite mínimo em linha âmbar pontilhada (#B77900, 2px)
    - Leituras fora dos limites com círculos vermelhos destacados
    """
    fig = go.Figure()
    if df.empty or "temperatura_mancal_c" not in df.columns:
        return fig

    sub = df.copy()
    if equipment:
        sub = sub[sub["id_equipamento"] == equipment]

    sub = sub.dropna(subset=["temperatura_mancal_c", "timestamp"]).sort_values("timestamp")
    if sub.empty:
        return fig

    low, high = SENSOR_LIMITS["temperatura_mancal_c"]

    # Faixa operacional segura destacada
    fig.add_hrect(
        y0=low,
        y1=high,
        fillcolor=CHART_PALETTE["safe_fill"],
        line_width=0,
        layer="below",
    )

    # Limite Mínimo (Âmbar pontilhado, 2px)
    fig.add_hline(
        y=low,
        line_dash="dot",
        line_color=CHART_PALETTE["amber"],
        line_width=2,
        annotation_text=f"Mín. seguro ({low:.1f} °C)",
        annotation_position="bottom right",
        annotation_font_size=9,
        annotation_font_color=CHART_PALETTE["amber"],
    )

    # Limite Máximo (Vermelho tracejado, 2px)
    fig.add_hline(
        y=high,
        line_dash="dash",
        line_color=CHART_PALETTE["red"],
        line_width=2,
        annotation_text=f"Limite Máx ({high:.1f} °C)",
        annotation_position="top right",
        annotation_font_size=9,
        annotation_font_color=CHART_PALETTE["red"],
    )

    # Linha de dados: Azul-escuro (#1565C0), 3px, marcadores sólidos
    fig.add_trace(go.Scatter(
        x=sub["timestamp"],
        y=sub["temperatura_mancal_c"],
        mode="lines+markers",
        name="Temperatura do Mancal",
        line=dict(color=CHART_PALETTE["blue"], width=3),
        marker=dict(size=5, color=CHART_PALETTE["blue"]),
        hovertemplate="<b>%{x|%d/%m/%Y %H:%M:%S}</b><br>Temperatura: <b>%{y:.1f} °C</b><extra></extra>",
    ))

    # Destaque de leituras fora dos limites com círculos vermelhos
    out_of_range = sub[(sub["temperatura_mancal_c"] < low) | (sub["temperatura_mancal_c"] > high)]
    if not out_of_range.empty:
        fig.add_trace(go.Scatter(
            x=out_of_range["timestamp"],
            y=out_of_range["temperatura_mancal_c"],
            mode="markers",
            name="Alerta Fora da Faixa",
            marker=dict(
                size=9,
                color=CHART_PALETTE["red"],
                symbol="circle",
                line=dict(color="#FFFFFF", width=2),
            ),
            hovertemplate="<b>%{x|%d/%m/%Y %H:%M:%S}</b><br>Alerta Temp: <b>%{y:.1f} °C (fora da faixa)</b><extra></extra>",
        ))

    _add_regime_transitions(fig, sub)

    layout = dict(**_BASE_LAYOUT)
    layout["height"] = _CHART_HEIGHT
    layout["yaxis"] = dict(**layout["yaxis"], title="Temperatura do Mancal (°C)")
    fig.update_layout(**layout)
    return fig


# --------------------------------------------------------------------------- #
# 2. Gráfico de Vibração RMS (mm/s)                                            #
# --------------------------------------------------------------------------- #
def vibration_chart(df: pd.DataFrame, equipment: str | None = None) -> go.Figure:
    """Gráfico temporal da vibração RMS.
    
    - Canvas branco com grade e moldura contrastantes (#475569)
    - Linha laranja escura (#E65100) sólida e espessa (3px)
    - Faixa segura (1.00 a 4.50 mm/s) destacada
    - Limite máximo em linha vermelha tracejada (#C62828, 2px)
    - Limite mínimo em linha âmbar pontilhada (#B77900, 2px)
    - Leituras fora dos limites com diamantes vermelhos destacados
    """
    fig = go.Figure()
    if df.empty or "vibracao_rms_mms" not in df.columns:
        return fig

    sub = df.copy()
    if equipment:
        sub = sub[sub["id_equipamento"] == equipment]

    sub = sub.dropna(subset=["vibracao_rms_mms", "timestamp"]).sort_values("timestamp")
    if sub.empty:
        return fig

    low, high = SENSOR_LIMITS["vibracao_rms_mms"]

    # Faixa operacional segura
    fig.add_hrect(
        y0=low,
        y1=high,
        fillcolor=CHART_PALETTE["safe_fill"],
        line_width=0,
        layer="below",
    )

    # Limite Mínimo (Âmbar pontilhado, 2px)
    fig.add_hline(
        y=low,
        line_dash="dot",
        line_color=CHART_PALETTE["amber"],
        line_width=2,
        annotation_text=f"Mín. seguro ({low:.2f} mm/s)",
        annotation_position="bottom right",
        annotation_font_size=9,
        annotation_font_color=CHART_PALETTE["amber"],
    )

    # Limite Máximo (Vermelho tracejado, 2px)
    fig.add_hline(
        y=high,
        line_dash="dash",
        line_color=CHART_PALETTE["red"],
        line_width=2,
        annotation_text=f"Limite Máx ({high:.2f} mm/s)",
        annotation_position="top right",
        annotation_font_size=9,
        annotation_font_color=CHART_PALETTE["red"],
    )

    # Linha de dados: Laranja escuro (#E65100), 3px, marcadores sólidos
    fig.add_trace(go.Scatter(
        x=sub["timestamp"],
        y=sub["vibracao_rms_mms"],
        mode="lines+markers",
        name="Vibração RMS",
        line=dict(color=CHART_PALETTE["orange"], width=3),
        marker=dict(size=5, color=CHART_PALETTE["orange"]),
        hovertemplate="<b>%{x|%d/%m/%Y %H:%M:%S}</b><br>Vibração: <b>%{y:.2f} mm/s</b><extra></extra>",
    ))

    # Destaque de leituras fora dos limites com diamantes vermelhos
    out_of_range = sub[(sub["vibracao_rms_mms"] < low) | (sub["vibracao_rms_mms"] > high)]
    if not out_of_range.empty:
        fig.add_trace(go.Scatter(
            x=out_of_range["timestamp"],
            y=out_of_range["vibracao_rms_mms"],
            mode="markers",
            name="Alerta Fora da Faixa",
            marker=dict(
                size=9,
                color=CHART_PALETTE["red"],
                symbol="diamond",
                line=dict(color="#FFFFFF", width=2),
            ),
            hovertemplate="<b>%{x|%d/%m/%Y %H:%M:%S}</b><br>Alerta Vibração: <b>%{y:.2f} mm/s (fora da faixa)</b><extra></extra>",
        ))

    _add_regime_transitions(fig, sub)

    layout = dict(**_BASE_LAYOUT)
    layout["height"] = _CHART_HEIGHT
    layout["yaxis"] = dict(**layout["yaxis"], title="Vibração RMS (mm/s)")
    fig.update_layout(**layout)
    return fig


# --------------------------------------------------------------------------- #
# 3. Gráfico de Pressão do Óleo (bar)                                         #
# --------------------------------------------------------------------------- #
def pressure_chart(df: pd.DataFrame, equipment: str | None = None) -> go.Figure:
    """Gráfico temporal da pressão do óleo lubrificante.
    
    - Canvas branco com grade e moldura contrastantes (#475569)
    - Linha roxo escuro (#6A1B9A) sólida e espessa (3px)
    - Faixa segura (3.50 a 5.20 bar) destacada
    - Limite máximo em linha vermelha (#C62828, 2px)
    - Limite mínimo em linha âmbar (#B77900, 2px)
    - Leituras fora dos limites com triângulos vermelhos destacados
    """
    fig = go.Figure()
    if df.empty or "pressao_oleo_bar" not in df.columns:
        return fig

    sub = df.copy()
    if equipment:
        sub = sub[sub["id_equipamento"] == equipment]

    sub = sub.dropna(subset=["pressao_oleo_bar", "timestamp"]).sort_values("timestamp")
    if sub.empty:
        return fig

    low, high = SENSOR_LIMITS["pressao_oleo_bar"]

    # Faixa operacional segura
    fig.add_hrect(
        y0=low,
        y1=high,
        fillcolor=CHART_PALETTE["safe_fill"],
        line_width=0,
        layer="below",
    )

    # Limite Mínimo (Âmbar pontilhado, 2px)
    fig.add_hline(
        y=low,
        line_dash="dot",
        line_color=CHART_PALETTE["amber"],
        line_width=2,
        annotation_text=f"Mín. seguro ({low:.2f} bar)",
        annotation_position="bottom right",
        annotation_font_size=9,
        annotation_font_color=CHART_PALETTE["amber"],
    )

    # Limite Máximo (Vermelho tracejado, 2px)
    fig.add_hline(
        y=high,
        line_dash="dash",
        line_color=CHART_PALETTE["red"],
        line_width=2,
        annotation_text=f"Limite Máx ({high:.2f} bar)",
        annotation_position="top right",
        annotation_font_size=9,
        annotation_font_color=CHART_PALETTE["red"],
    )

    # Linha de dados: Roxo escuro (#6A1B9A), 3px, marcadores sólidos
    fig.add_trace(go.Scatter(
        x=sub["timestamp"],
        y=sub["pressao_oleo_bar"],
        mode="lines+markers",
        name="Pressão do Óleo",
        line=dict(color=CHART_PALETTE["purple"], width=3),
        marker=dict(size=5, color=CHART_PALETTE["purple"]),
        hovertemplate="<b>%{x|%d/%m/%Y %H:%M:%S}</b><br>Pressão: <b>%{y:.2f} bar</b><extra></extra>",
    ))

    # Destaque de leituras fora dos limites com triângulos vermelhos
    out_of_range = sub[(sub["pressao_oleo_bar"] < low) | (sub["pressao_oleo_bar"] > high)]
    if not out_of_range.empty:
        fig.add_trace(go.Scatter(
            x=out_of_range["timestamp"],
            y=out_of_range["pressao_oleo_bar"],
            mode="markers",
            name="Alerta Fora da Faixa",
            marker=dict(
                size=9,
                color=CHART_PALETTE["red"],
                symbol="triangle-up",
                line=dict(color="#FFFFFF", width=2),
            ),
            hovertemplate="<b>%{x|%d/%m/%Y %H:%M:%S}</b><br>Alerta Pressão: <b>%{y:.2f} bar</b><extra></extra>",
        ))

    _add_regime_transitions(fig, sub)

    layout = dict(**_BASE_LAYOUT)
    layout["height"] = _COMPACT_HEIGHT
    layout["yaxis"] = dict(**layout["yaxis"], title="Pressão do Óleo (bar)")
    fig.update_layout(**layout)
    return fig


# --------------------------------------------------------------------------- #
# 4. Matriz de Confusão 4 × 4 com Contraste Automático                         #
# --------------------------------------------------------------------------- #
def confusion_matrix_chart(
    matrix: list[list[int]],
    class_names: list[str],
    source_label: str = "Conjunto de teste",
) -> go.Figure:
    """Matriz de confusão 4x4 com escala bem visível e contraste automático célula a célula."""
    z = matrix
    n = len(class_names)
    clean_labels = [name.replace("_", " ") for name in class_names]

    x_labels = [f"Pred: {label}" for label in clean_labels]
    y_labels = [f"Real: {label}" for label in clean_labels]

    max_val = max(max(row) for row in z) if z and any(z) else 1

    # Anotações para garantia absoluta de contraste:
    # Células escuras recebem texto branco; células claras recebem texto azul-escuro profundo
    annotations = []
    for i in range(n):
        for j in range(n):
            val = z[i][j]
            text_color = "#FFFFFF" if val > (max_val * 0.38) else "#0F172A"
            annotations.append(dict(
                x=x_labels[j],
                y=y_labels[i],
                text=f"<b>{val}</b>",
                font=dict(family="'JetBrains Mono', monospace", size=13, color=text_color),
                showarrow=False,
            ))

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=x_labels,
        y=y_labels,
        colorscale=[
            [0.0, "#F1F5F9"],        # Fundo claro visível (não branco invisível)
            [0.15, "#BFDBFE"],       # Azul suave
            [0.45, "#3B82F6"],       # Azul médio saturado
            [0.75, "#1565C0"],       # Azul institucional
            [1.0, "#0D3059"],        # Azul marinho profundo
        ],
        showscale=True,
        colorbar=dict(
            title=dict(
                text="Amostras",
                font=dict(family="'Inter', sans-serif", size=10, color=CHART_PALETTE["slate"]),
            ),
            tickfont=dict(family="'Inter', sans-serif", size=9, color=CHART_PALETTE["slate"]),
            thickness=14,
            len=0.88,
        ),
        hoverongaps=False,
        hovertemplate="Classe Real: <b>%{y}</b><br>Classe Prevista: <b>%{x}</b><br>Quantidade: <b>%{z}</b><extra></extra>",
    ))

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor=CHART_PALETTE["paper_bg"],
        plot_bgcolor=CHART_PALETTE["plot_bg"],
        height=390,
        margin=dict(l=40, r=40, t=35, b=55),
        font=dict(family="'Inter', sans-serif", size=11, color=CHART_PALETTE["font_heading"]),
        xaxis=dict(
            tickangle=-15,
            tickfont=dict(size=10, color=CHART_PALETTE["font_heading"], family="'Inter', sans-serif", weight=600),
            side="bottom",
            linecolor=CHART_PALETTE["slate"],
            linewidth=1.2,
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=10, color=CHART_PALETTE["font_heading"], family="'Inter', sans-serif", weight=600),
            linecolor=CHART_PALETTE["slate"],
            linewidth=1.2,
        ),
        annotations=annotations,
    )
    return fig


# --------------------------------------------------------------------------- #
# 5. Gráfico de Importância das Variáveis (Feature Importance)                 #
# --------------------------------------------------------------------------- #
def feature_importance_chart(features: list[str], importances: list[float]) -> go.Figure:
    """Gráfico de barras horizontal da importância das variáveis com alto contraste."""
    pairs = sorted(zip(importances, features))
    sorted_imp, sorted_feat = zip(*pairs) if pairs else ([], [])

    clean_names = [
        f.replace("numericas__", "")
         .replace("categoricas__", "cat: ")
         .replace("_", " ")
        for f in sorted_feat
    ]

    # As 3 variáveis mais importantes destacadas em laranja escuro (#E65100), as demais em azul (#1565C0)
    total = len(sorted_feat)
    bar_colors = [
        CHART_PALETTE["orange"] if i >= (total - 3) else CHART_PALETTE["blue"]
        for i in range(total)
    ]

    fig = go.Figure(go.Bar(
        x=list(sorted_imp),
        y=clean_names,
        orientation="h",
        marker=dict(
            color=bar_colors,
            line=dict(color=CHART_PALETTE["slate"], width=1),
        ),
        text=[f"<b>{v:.4f}</b>" for v in sorted_imp],
        textposition="outside",
        textfont=dict(family="'JetBrains Mono', monospace", size=10, color=CHART_PALETTE["font_heading"]),
        hovertemplate="Variável: <b>%{y}</b><br>Importância Relativa: <b>%{x:.4f}</b><extra></extra>",
    ))

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor=CHART_PALETTE["paper_bg"],
        plot_bgcolor=CHART_PALETTE["plot_bg"],
        height=max(330, len(sorted_feat) * 25),
        margin=dict(l=10, r=60, t=15, b=25),
        xaxis=dict(
            gridcolor=CHART_PALETTE["grid"],
            gridwidth=1,
            showline=True,
            linecolor=CHART_PALETTE["slate"],
            linewidth=1.2,
            title_text="Importância Relativa (Critério Gini)",
            title_font=dict(size=10, color=CHART_PALETTE["slate"]),
            tickfont=dict(size=9, color=CHART_PALETTE["font_body"]),
        ),
        yaxis=dict(
            gridcolor=CHART_PALETTE["grid"],
            showline=True,
            linecolor=CHART_PALETTE["slate"],
            linewidth=1.2,
            tickfont=dict(size=10, color=CHART_PALETTE["font_heading"], weight=600),
        ),
        font=dict(family="'Inter', sans-serif", size=11, color=CHART_PALETTE["font_heading"]),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=CHART_PALETTE["slate"]),
    )
    return fig


# --------------------------------------------------------------------------- #
# 6. Gráfico de Recall por Classe de Falha                                     #
# --------------------------------------------------------------------------- #
def recall_bar_chart(classes: list[str], recalls: list[float]) -> go.Figure:
    """Gráfico de barras horizontal com cores sólidas e saturadas para cada classe."""
    color_map = {
        "Normal": CHART_PALETTE["green"],
        "Desgaste_Rolamento": CHART_PALETTE["amber"],
        "Desbalanceamento_Rotor": CHART_PALETTE["orange"],
        "Cavitacao_Superaquecimento": CHART_PALETTE["red"],
    }
    colors = [color_map.get(c, CHART_PALETTE["blue"]) for c in classes]
    labels = [c.replace("_", " ") for c in classes]

    fig = go.Figure(go.Bar(
        x=recalls,
        y=labels,
        orientation="h",
        marker=dict(color=colors, line=dict(color=CHART_PALETTE["slate"], width=1)),
        text=[f"<b>{v:.1%}</b>" for v in recalls],
        textposition="inside",
        insidetextanchor="middle",
        textfont=dict(family="'JetBrains Mono', monospace", size=11, color="#FFFFFF"),
        hovertemplate="Classe: <b>%{y}</b><br>Taxa de Recall: <b>%{x:.2%}</b><extra></extra>",
    ))

    # Linha de referência da meta industrial (90%)
    fig.add_vline(
        x=0.90,
        line_dash="dot",
        line_color=CHART_PALETTE["slate"],
        line_width=1.8,
        annotation_text="Meta industrial (90%)",
        annotation_position="top left",
        annotation_font_size=9,
        annotation_font_color=CHART_PALETTE["slate"],
    )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor=CHART_PALETTE["paper_bg"],
        plot_bgcolor=CHART_PALETTE["plot_bg"],
        height=225,
        margin=dict(l=10, r=20, t=20, b=25),
        xaxis=dict(
            range=[0, 1.05],
            tickformat=".0%",
            gridcolor=CHART_PALETTE["grid"],
            gridwidth=1,
            showline=True,
            linecolor=CHART_PALETTE["slate"],
            linewidth=1.2,
            tickfont=dict(size=10, color=CHART_PALETTE["font_body"]),
        ),
        yaxis=dict(
            gridcolor=CHART_PALETTE["grid"],
            showline=True,
            linecolor=CHART_PALETTE["slate"],
            linewidth=1.2,
            tickfont=dict(size=10, color=CHART_PALETTE["font_heading"], weight=600),
        ),
        font=dict(family="'Inter', sans-serif", size=11, color=CHART_PALETTE["font_heading"]),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=CHART_PALETTE["slate"]),
    )
    return fig


# --------------------------------------------------------------------------- #
# 7. Linha do Tempo de Detecção de Anomalias (Isolation Forest)               #
# --------------------------------------------------------------------------- #
def anomaly_timeline_chart(df: pd.DataFrame, equipment: str | None = None) -> go.Figure:
    """Linha do tempo de detecção de anomalias com pontos verdes e diamantes vermelhos."""
    fig = go.Figure()
    if df.empty or "anomalia" not in df.columns:
        return fig

    sub = df.copy()
    if equipment:
        sub = sub[sub["id_equipamento"] == equipment]
    sub = sub.dropna(subset=["timestamp"]).sort_values("timestamp")
    if sub.empty:
        return fig

    sub["anomalia_num"] = sub["anomalia"].apply(lambda v: 1 if v is True else 0)

    normal = sub[sub["anomalia_num"] == 0]
    anomal = sub[sub["anomalia_num"] == 1]

    if not normal.empty:
        fig.add_trace(go.Scatter(
            x=normal["timestamp"],
            y=normal["anomalia_num"],
            mode="markers",
            name="Normal",
            marker=dict(color=CHART_PALETTE["green"], size=7, symbol="circle"),
            hovertemplate="<b>%{x|%H:%M:%S}</b> — Estado Normal<extra></extra>",
        ))
    if not anomal.empty:
        fig.add_trace(go.Scatter(
            x=anomal["timestamp"],
            y=anomal["anomalia_num"],
            mode="markers",
            name="Anomalia Detectada",
            marker=dict(
                color=CHART_PALETTE["red"],
                size=9,
                symbol="diamond",
                line=dict(color="#FFFFFF", width=1.5),
            ),
            hovertemplate="<b>%{x|%H:%M:%S}</b> — <b>Anomalia Detectada</b><extra></extra>",
        ))

    _add_regime_transitions(fig, sub)

    layout = dict(**_BASE_LAYOUT)
    layout["height"] = 155
    layout["yaxis"] = dict(
        tickvals=[0, 1],
        ticktext=["Normal", "Anomalia"],
        range=[-0.4, 1.4],
        gridcolor=CHART_PALETTE["grid"],
        showline=True,
        linecolor=CHART_PALETTE["slate"],
        linewidth=1.2,
        tickfont=dict(size=10, color=CHART_PALETTE["font_heading"], weight=600),
    )
    fig.update_layout(**layout)
    return fig


def correlation_heatmap(correlation: pd.DataFrame, annotate: bool | None = None) -> go.Figure:
    """Mapa divergente de coeficientes de correlação, limitado a [-1, 1]."""
    labels = [str(column) for column in correlation.columns]
    values = correlation.to_numpy(dtype=float)
    if annotate is None:
        annotate = len(labels) <= 12
    fig = go.Figure(go.Heatmap(
        x=labels, y=labels, z=values,
        zmin=-1, zmax=1, zmid=0,
        colorscale=[[0, "#2166AC"], [0.5, "#FFFFFF"], [1, "#B2182B"]],
        colorbar=dict(title="Correlação", tickvals=[-1, -0.5, 0, 0.5, 1]),
        customdata=np.stack(np.meshgrid(labels, labels), axis=-1),
        hovertemplate="Variáveis: %{y} × %{x}<br>Coeficiente: %{z:.3f}<extra></extra>",
    ))
    if annotate:
        for row, y_label in enumerate(labels):
            for col, x_label in enumerate(labels):
                value = values[row, col]
                if np.isfinite(value):
                    fig.add_annotation(x=x_label, y=y_label, text=f"{value:.2f}",
                                       showarrow=False,
                                       font=dict(size=9, color="#FFFFFF" if abs(value) >= 0.45 else "#183B56"))
    height = min(820, max(420, 34 * len(labels) + 160))
    fig.update_layout(
        template=PLOTLY_TEMPLATE, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        height=height, margin=dict(l=150, r=30, t=24, b=140),
        font=dict(family="'Inter', sans-serif", color="#183B56"),
        xaxis=dict(tickangle=-45, side="bottom", automargin=True),
        yaxis=dict(autorange="reversed", automargin=True, scaleanchor="x", scaleratio=1),
    )
    return fig
