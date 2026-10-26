"""Componentes reutilizáveis do dashboard AeroMotion Dynamics.

Identidade visual industrial moderna:
- Predominantemente branco (#FFFFFF) e fundos limpos
- Textos em tons de azul-escuro (#102A43, #183B56, #334E68)
- Textos auxiliares com contraste adequado (#627D98)
- Indicadores semânticos claros para falhas e estados operacionais
- Ícones SVG consistentes da biblioteca Lucide
- Zero emojis em qualquer componente
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

import frontend.icons as ic
from frontend.styles import CLASS_COLORS, COLORS

# Mapeamento oficial dos rótulos das classes do modelo
CLASS_LABEL = {
    "Normal": "Operação Normal",
    "Desgaste_Rolamento": "Desgaste de Rolamento",
    "Desbalanceamento_Rotor": "Desbalanceamento do Rotor",
    "Cavitacao_Superaquecimento": "Cavitação / Superaquecimento",
}

# Índice numérico → nome de classe da API
CLASS_NAMES: dict[int, str] = {
    0: "Normal",
    1: "Desgaste_Rolamento",
    2: "Desbalanceamento_Rotor",
    3: "Cavitacao_Superaquecimento",
}

# Rótulos dos regimes operacionais (distintos das classes do modelo)
REGIME_LABELS: dict[str, str] = {
    "Cruzeiro": "Cruzeiro",
    "Carga_Media": "Carga Média",
    "Carga_Alta": "Carga Alta",
}

ORIGIN_LABELS: dict[str, str] = {
    "simulada": "Simulada",
    "real": "Real",
    "desconhecida": "Desconhecida",
}

PERFIL_LABELS: dict[str, str] = {
    "nominal": "Nominal",
    "anormal": "Anormal",
    "desconhecido": "Desconhecido",
}

PERFIL_ANOMALIA_LABELS: dict[str, str] = {
    "A": "A — Térmica",
    "B": "B — Vibração",
    "C": "C — Combinada",
}


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    total = int(max(0, seconds))
    if total < 60:
        return f"{total} s"
    if total < 3600:
        return f"{total // 60} min {total % 60:02d} s"
    return f"{total // 3600} h {(total % 3600) // 60:02d} min"



def render_header(
    api_online: bool,
    sim_running: bool,
    selected_equipment: str,
    last_update: datetime | None,
) -> None:
    """Cabeçalho industrial limpo com fundo branco e alinhamento consistente."""
    # Estado da API
    api_dot = "dot-green" if api_online else "dot-red"
    api_label = "Conectada" if api_online else "Desconectada"
    api_icon = ic.server(color=COLORS["green"] if api_online else COLORS["red"], size=15)

    # Estado da Conexão
    conn_dot = "dot-green" if api_online else "dot-red"
    conn_label = "Estável" if api_online else "Instável"
    conn_icon = ic.wifi(color=COLORS["green"] if api_online else COLORS["red"], size=15)

    # Estado da Simulação
    sim_dot = "dot-green" if sim_running else "dot-gray"
    sim_label = "Ativa" if sim_running else "Inativa"
    sim_icon = ic.play(color=COLORS["green"], size=15) if sim_running else ic.square_stop(color=COLORS["text_secondary"], size=15)

    # Horário da última atualização
    clock_icon = ic.clock(color=COLORS["text_secondary"], size=15)
    update_str = last_update.strftime("%H:%M:%S") if last_update else "—"

    st.markdown(f"""
<div class="aero-header">
  <div class="aero-header-left">
    <h1>AeroMotion Dynamics</h1>
    <p>Monitoramento Preditivo Industrial &nbsp;&bull;&nbsp; Equipamento: <strong>{selected_equipment}</strong></p>
  </div>
  <div class="aero-header-right">
    <div class="aero-status-badge">
      {api_icon}
      <span class="badge-title">API:</span>
      <span class="aero-status-dot {api_dot}"></span>
      <span class="label">{api_label}</span>
    </div>
    <div class="aero-status-badge">
      {conn_icon}
      <span class="badge-title">Conexão:</span>
      <span class="aero-status-dot {conn_dot}"></span>
      <span class="label">{conn_label}</span>
    </div>
    <div class="aero-status-badge">
      {sim_icon}
      <span class="badge-title">Simulação:</span>
      <span class="aero-status-dot {sim_dot}"></span>
      <span class="label">{sim_label}</span>
    </div>
    <div class="aero-status-badge">
      {clock_icon}
      <span class="badge-title">Atualização:</span>
      <span class="label">{update_str}</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


def render_regime_card(status: dict[str, Any] | None) -> None:
    """Cartão compacto do regime ativo, transição e comunicação do simulador."""
    if status is None:
        st.markdown(
            f"""
<div class="regime-card">
  <div class="regime-card-left">
    <div class="regime-card-icon">{ic.activity(color=COLORS['text_muted'], size=22)}</div>
    <div>
      <div class="regime-card-tag">Regime de Operação</div>
      <div class="regime-card-name" style="color:{COLORS['text_secondary']};">Comunicação indisponível</div>
      <div class="regime-card-meta">Não foi possível consultar o estado do simulador na API.</div>
    </div>
  </div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    active_key = status.get("regime_ativo") or status.get("regime_selecionado")
    labels = status.get("rotulos") or REGIME_LABELS
    active_label = labels.get(active_key, (active_key or "—").replace("_", " "))
    online = bool(status.get("simulador_online"))
    changed_at = status.get("ultima_mudanca") or "—"
    since = _format_duration(status.get("segundos_desde_transicao"))
    interval = status.get("intervalo_segundos")

    dot_class = "dot-green" if online else "dot-red"
    state_text = "Online" if online else "Offline"
    meta = (
        f"Última mudança: <strong>{changed_at}</strong> &nbsp;|&nbsp; "
        f"há <strong>{since}</strong>"
    )
    if interval is not None:
        meta += f" &nbsp;|&nbsp; ciclo: <strong>{float(interval):.0f} s</strong>"

    note = "" if online else (
        f'<div class="regime-card-note">{status.get("mensagem", "")}</div>'
    )

    st.markdown(
        f"""
<div class="regime-card">
  <div class="regime-card-left">
    <div class="regime-card-icon">{ic.activity(color=COLORS['blue_primary'], size=22)}</div>
    <div>
      <div class="regime-card-tag">Regime de Operação</div>
      <div class="regime-card-name">{active_label}</div>
      <div class="regime-card-meta">{meta}</div>
    </div>
  </div>
  <div class="regime-card-right">
    <span class="regime-card-status">
      <span class="aero-status-dot {dot_class}"></span>
      Simulador: <strong>{state_text}</strong>
    </span>
    <div class="regime-card-note">Origem dos dados: simulada</div>
    {note}
  </div>
</div>""",
        unsafe_allow_html=True,
    )


def render_telemetry_cards(latest: pd.Series | None) -> None:
    """Indicadores compactos das variáveis existentes no sistema."""
    metrics = [
        ("temperatura_mancal_c", "Temperatura do Mancal", "°C", ic.thermometer, COLORS["blue_primary"], 1),
        ("vibracao_rms_mms", "Vibração RMS", "mm/s", ic.activity, COLORS["orange"], 2),
        ("pressao_oleo_bar", "Pressão do Óleo", "bar", ic.gauge, COLORS["purple"], 2),
        ("rotacao_rpm", "Rotação", "RPM", ic.rotate_cw, COLORS["teal"], 0),
        ("corrente_eletrica_amp", "Corrente Elétrica", "A", ic.power, COLORS["text_heading"], 2),
        ("emissao_acustica_db", "Emissão Acústica", "dB", ic.volume_2, COLORS["slate"], 1),
    ]

    cards = []
    for field, label, unit, icon_fn, color, decimals in metrics:
        value = latest.get(field) if latest is not None else None
        if value is None or pd.isna(value):
            value_str = "—"
        elif decimals == 0:
            value_str = f"{float(value):,.0f}"
        else:
            value_str = f"{float(value):,.{decimals}f}"
        cards.append(
            f"""
<div class="telemetry-card">
  <div class="telemetry-top">
    <span class="telemetry-label">{label}</span>
    <span class="telemetry-icon">{icon_fn(color=color, size=16)}</span>
  </div>
  <div class="telemetry-value" style="color:{color};">{value_str}<span class="telemetry-unit">{unit}</span></div>
</div>"""
        )

    st.markdown(
        '<div class="telemetry-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def render_kpi_cards(latest: pd.Series | None, probabilities: dict[str, float] | None) -> None:
    """Quatro cartões principais de probabilidade estimada de falha (fundo branco, borda fina)."""
    class_order = [
        ("0", "Normal", ic.check_circle),
        ("1", "Desgaste_Rolamento", ic.zap),
        ("2", "Desbalanceamento_Rotor", ic.activity),
        ("3", "Cavitacao_Superaquecimento", ic.thermometer),
    ]

    cards_html = '<div class="kpi-grid">'

    for key, class_name, icon_fn in class_order:
        label = CLASS_LABEL.get(class_name, class_name)
        color = CLASS_COLORS.get(class_name, COLORS["blue_light"])
        icon_svg = icon_fn(color=color, size=22)

        if probabilities and key in probabilities:
            prob = probabilities[key]
            value_str = f"{prob:.1%}"
            sub = "Probabilidade estimada pelo modelo"
        elif probabilities is not None:
            value_str = "N/D"
            sub = "Classe ausente na resposta"
        else:
            value_str = "—"
            sub = "Aguardando predições da API"

        cards_html += f"""
<div class="kpi-card">
  <div class="kpi-top">
    <span class="kpi-label">{label}</span>
    <span class="kpi-icon">{icon_svg}</span>
  </div>
  <div class="kpi-value" style="color:{color}">{value_str}</div>
  <div class="kpi-sub">{sub}</div>
  <div class="kpi-accent-bar" style="background:{color};"></div>
</div>"""

    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)


def render_predicted_class(latest: pd.Series | None, probabilities: dict[str, float] | None) -> None:
    """Painel branco de classe predominante, com hierarquia clara e sem blocos escuros."""
    section_icon = ic.cpu(color=COLORS["text_heading"], size=16)
    st.markdown(
        f'<div class="section-title">{section_icon} Classe Predominante</div>',
        unsafe_allow_html=True,
    )

    if latest is None:
        empty_icon = ic.cpu(color=COLORS["text_secondary"], size=22)
        st.markdown(
            f"""
<div class="predicted-class-box" style="border-left: 4px solid {COLORS['border']};">
  <div class="pclass-left">
    <div class="pclass-icon-wrapper">{empty_icon}</div>
    <div class="pclass-main">
      <div class="pclass-tag">Estado Atual</div>
      <div class="pclass-name" style="color:{COLORS['text_secondary']};">Sem dados disponíveis</div>
      <div class="pclass-meta">Inicie a simulação para receber predições em tempo real da API.</div>
    </div>
  </div>
  <div class="pclass-prob-wrapper">
    <div class="pclass-prob-label">Confiança</div>
    <div class="pclass-prob" style="color:{COLORS['text_muted']};">—</div>
  </div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    class_name = latest.get("classe", "Normal")
    label = CLASS_LABEL.get(class_name, class_name)
    color = CLASS_COLORS.get(class_name, COLORS["text_secondary"])
    equipment = latest.get("id_equipamento", "—")

    # Ícone representativo da condição prevista
    if class_name == "Normal":
        icon_svg = ic.check_circle(color=color, size=24)
    elif class_name == "Desgaste_Rolamento":
        icon_svg = ic.zap(color=color, size=24)
    elif class_name == "Desbalanceamento_Rotor":
        icon_svg = ic.activity(color=color, size=24)
    else:
        icon_svg = ic.thermometer(color=color, size=24)

    # Data e horário formatados
    ts = latest.get("timestamp")
    ts_str = ts.strftime("%d/%m/%Y %H:%M:%S") if isinstance(ts, (datetime, pd.Timestamp)) else str(ts)

    # Probabilidade da classe prevista
    key = str(next((k for k, v in CLASS_NAMES.items() if v == class_name), ""))
    prob = probabilities.get(key) if probabilities and key else None
    prob_str = f"{prob:.1%}" if prob is not None else "—"

    # Aviso claro quando a previsão for diferente de Normal
    warning_html = ""
    if class_name != "Normal":
        alert_icon = ic.alert_triangle(color=COLORS["red"], size=16)
        warning_html = (
            f'<div class="failure-notice">{alert_icon}'
            f'<span>Alerta preditivo: <strong>Possível falha em andamento ({label})</strong> detectada pelo modelo no equipamento {equipment}. '
            f'Esta estimativa indica prioridade de inspeção preventiva.</span></div>'
        )

    st.markdown(f"""
{warning_html}
<div class="predicted-class-box" style="border-left: 4.5px solid {color};">
  <div class="pclass-left">
    <div class="pclass-icon-wrapper" style="background-color: {color}12; border-color: {color}30;">
      {icon_svg}
    </div>
    <div class="pclass-main">
      <div class="pclass-tag">Diagnóstico Preditivo</div>
      <div class="pclass-name">{label}</div>
      <div class="pclass-meta">Equipamento: <strong>{equipment}</strong> &nbsp;|&nbsp; Registro: <strong>{ts_str}</strong></div>
    </div>
  </div>
  <div class="pclass-prob-wrapper">
    <div class="pclass-prob-label">Confiança Estimada</div>
    <div class="pclass-prob" style="color:{color};">{prob_str}</div>
  </div>
</div>
""", unsafe_allow_html=True)


def render_anomaly_section(latest: pd.Series | None, df: pd.DataFrame) -> None:
    """Indicador de anomalia não supervisionada (Isolation Forest)."""
    section_icon = ic.alert_triangle(color=COLORS["text_heading"], size=16)
    st.markdown(
        f'<div class="section-title">{section_icon} Detecção de Anomalias (Isolation Forest)</div>',
        unsafe_allow_html=True,
    )

    if latest is None or "anomalia" not in (latest.index if hasattr(latest, "index") else []):
        st.markdown(
            f'<div class="anomaly-container">'
            f'<span class="anomaly-indicator anomaly-unknown">{ic.info(color=COLORS["text_secondary"], size=14)} Módulo não carregado ou sem leituras</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    anomaly_val = latest.get("anomalia")
    if anomaly_val is None:
        st.markdown(
            f'<div class="anomaly-container">'
            f'<span class="anomaly-indicator anomaly-unknown">{ic.info(color=COLORS["text_secondary"], size=14)} Detector de anomalias inativo</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    if anomaly_val:
        icon_html = ic.alert_triangle(color=COLORS["red"], size=15)
        badge = f'<div class="anomaly-indicator anomaly-yes">{icon_html} Anomalia detectada</div>'
    else:
        icon_html = ic.check_circle(color=COLORS["green"], size=15)
        badge = f'<div class="anomaly-indicator anomaly-no">{icon_html} Leitura dentro do padrão esperado</div>'

    # Contagem de leituras anômalas no histórico
    if not df.empty and "anomalia" in df.columns:
        total = len(df)
        anomalies = int(df["anomalia"].apply(lambda v: v is True).sum())
        meta = f'<span style="font-size:0.78rem;color:{COLORS["text_secondary"]};font-weight:500;">Histórico recente: <strong>{anomalies} anomalia(s)</strong> identificada(s) em {total} leituras.</span>'
    else:
        meta = ""

    st.markdown(f'<div class="anomaly-container">{badge}&nbsp;&nbsp;{meta}</div>', unsafe_allow_html=True)


def render_warmup_notice(is_warmup: bool) -> None:
    """Aviso de aquecimento do histórico móvel."""
    if not is_warmup:
        return
    icon_html = ic.info(color=COLORS["yellow"], size=16)
    st.markdown(
        f'<div class="warmup-notice">{icon_html}'
        f'<span><strong>Aquecimento da janela temporal:</strong> Menos de 2 leituras na janela de 1 hora. '
        f'Desvios móveis estão sendo imputados pelo pipeline até a formação da série contínua.</span></div>',
        unsafe_allow_html=True,
    )


def render_stale_data_warning(last_ts: pd.Timestamp | None, threshold_minutes: int = 5) -> None:
    """Aviso quando as leituras de telemetria estiverem muito antigas."""
    if last_ts is None:
        return
    age = datetime.now() - last_ts.to_pydatetime()
    if age > timedelta(minutes=threshold_minutes):
        mins = int(age.total_seconds() // 60)
        icon_html = ic.alert_triangle(color=COLORS["yellow"], size=16)
        st.markdown(
            f'<div class="warmup-notice">{icon_html}'
            f'<span><strong>Telemetria estagnada:</strong> A última leitura recebida ocorreu há {mins} minuto(s). '
            f'Verifique se o processo do simulador está em execução.</span></div>',
            unsafe_allow_html=True,
        )


def render_api_offline_message(error: str | None) -> None:
    """Mensagem de indisponibilidade da API FastAPI com contraste industrial."""
    icon_html = ic.x_circle(color=COLORS["red"], size=18)
    msg = error or "A API FastAPI não está respondendo no endereço configurado."
    st.markdown(
        f'<div class="failure-notice">{icon_html}'
        f'<span><strong>API Indisponível:</strong> {msg} '
        f'Certifique-se de que a API foi iniciada através do comando <code>uvicorn api.main:app --port 8000</code>.</span></div>',
        unsafe_allow_html=True,
    )


def to_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    """Converte lista de predições da API em DataFrame normalizado e ordenado."""
    rows = []
    for item in items:
        row: dict[str, Any] = {
            "timestamp": item.get("timestamp"),
            "id_equipamento": item.get("id_equipamento"),
            "classe": item.get("nome_classe_prevista"),
            "classe_prevista": item.get("classe_prevista"),
            "regime": item.get("regime_operacional") or item.get("modo_operacao"),
            "regime_anterior": item.get("regime_anterior"),
            "regime_alterado_em": item.get("regime_alterado_em"),
            "origem": item.get("origem_leitura") or "desconhecida",
            "perfil_sintetico": item.get("perfil_sintetico") or "desconhecido",
            "perfil_anomalia": item.get("perfil_anomalia"),
            "anomalia": item.get("anomalia"),
            "aquecimento": item.get("aquecimento_historico"),
        }
        for field, value in (item.get("sensores") or {}).items():
            row[field] = value
        for label, value in (item.get("probabilidades") or {}).items():
            row[f"prob_{label}"] = value
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    return df


def get_latest(df: pd.DataFrame, equipment: str | None = None) -> pd.Series | None:
    """Retorna o registro mais recente filtrado por equipamento."""
    if df.empty:
        return None
    sub = df[df["id_equipamento"] == equipment] if equipment else df
    if sub.empty:
        return None
    return sub.iloc[-1]


def extract_probabilities(latest: pd.Series | None) -> dict[str, float] | None:
    """Extrai e valida as probabilidades estimadas da predição mais recente."""
    if latest is None:
        return None
    prob_cols = {col.replace("prob_", ""): latest[col] for col in latest.index if col.startswith("prob_")}
    if not prob_cols:
        return None
    total = sum(v for v in prob_cols.values() if pd.notna(v))
    if total < 0.7 or total > 1.3:
        return None
    return {k: float(v) for k, v in prob_cols.items() if pd.notna(v)}


def render_history_table(
    df: pd.DataFrame,
    filter_equipment: str | None,
    filter_class: str | None,
    max_rows: int = 100,
) -> None:
    """Tabela de histórico de predições com cabeçalho contrastante e formatação limpa."""
    if df.empty:
        st.info("Nenhuma leitura registrada no histórico.")
        return

    sub = df.copy()
    if filter_equipment and filter_equipment != "Todos":
        sub = sub[sub["id_equipamento"] == filter_equipment]
    if filter_class and filter_class != "Todas":
        sub = sub[sub["classe"] == filter_class]

    sub = sub.sort_values("timestamp", ascending=False).head(max_rows)

    # Confiança da classe efetivamente prevista (probabilidade do modelo).
    sub = sub.copy()
    if {"classe_prevista", "prob_0"}.issubset(sub.columns):
        def _confidence(row: pd.Series) -> float | None:
            label = row.get("classe_prevista")
            if pd.isna(label):
                return None
            value = row.get(f"prob_{int(label)}")
            return float(value) if pd.notna(value) else None
        sub["confianca"] = sub.apply(_confidence, axis=1)

    col_map = {
        "timestamp": "Timestamp",
        "id_equipamento": "Equipamento",
        "regime": "Regime",
        "perfil_sintetico": "Perfil Gerado",
        "perfil_anomalia": "Perfil de Anomalia",
        "origem": "Origem",
        "temperatura_mancal_c": "Temp. Mancal (°C)",
        "vibracao_rms_mms": "Vibração RMS (mm/s)",
        "pressao_oleo_bar": "Pressão Óleo (bar)",
        "rotacao_rpm": "Rotação (RPM)",
        "corrente_eletrica_amp": "Corrente (A)",
        "classe": "Classe Prevista",
        "confianca": "Confiança",
        "anomalia": "Anomalia",
    }
    available = {k: v for k, v in col_map.items() if k in sub.columns}
    display = sub[list(available.keys())].rename(columns=available)

    # Formatação numérica
    for col in ["Temp. Mancal (°C)", "Vibração RMS (mm/s)", "Pressão Óleo (bar)", "Corrente (A)"]:
        if col in display.columns:
            display[col] = display[col].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    for col in ["Rotação (RPM)"]:
        if col in display.columns:
            display[col] = display[col].apply(lambda v: f"{v:.0f}" if pd.notna(v) else "—")
    if "Classe Prevista" in display.columns:
        display["Classe Prevista"] = display["Classe Prevista"].apply(lambda v: CLASS_LABEL.get(v, v))
    if "Regime" in display.columns:
        display["Regime"] = display["Regime"].apply(
            lambda v: REGIME_LABELS.get(v, str(v).replace("_", " ")) if pd.notna(v) else "—"
        )
    if "Origem" in display.columns:
        display["Origem"] = display["Origem"].apply(
            lambda v: ORIGIN_LABELS.get(v, str(v)) if pd.notna(v) else "Desconhecida"
        )
    if "Perfil Gerado" in display.columns:
        display["Perfil Gerado"] = display["Perfil Gerado"].apply(
            lambda v: PERFIL_LABELS.get(v, str(v)) if pd.notna(v) else "—"
        )
    if "Perfil de Anomalia" in display.columns:
        display["Perfil de Anomalia"] = display["Perfil de Anomalia"].apply(
            lambda v: PERFIL_ANOMALIA_LABELS.get(v, str(v)) if pd.notna(v) else "—"
        )
    if "Confiança" in display.columns:
        display["Confiança"] = display["Confiança"].apply(
            lambda v: f"{float(v):.1%}" if pd.notna(v) else "—"
        )
    if "Anomalia" in display.columns:
        display["Anomalia"] = display["Anomalia"].apply(
            lambda v: "Sim" if v is True else ("Não" if v is False else "—")
        )

    if "Timestamp" in display.columns:
        display["Timestamp"] = display["Timestamp"].dt.strftime("%d/%m/%Y %H:%M:%S")

    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(f"Exibindo os {len(display)} registros mais recentes do histórico.")


def render_regime_evaluation(stats: dict[str, Any] | None) -> None:
    """Compara a geração nominal/anormal com a reação real do classificador.

    A primeira tabela mostra o que o gerador produziu. A segunda mostra o que o
    modelo respondeu. As duas distribuições são deliberadamente separadas: o
    perfil sintético nunca é usado como rótulo da predição.
    """
    if not stats:
        st.info("Estatísticas da API indisponíveis no momento.")
        return

    evaluation = stats.get("avaliacao_por_regime") or {}
    regimes = ("Cruzeiro", "Carga_Media", "Carga_Alta")
    rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []

    for regime in regimes:
        item = evaluation.get(regime) or {}
        classes = item.get("classes_previstas") or {}
        probabilities = item.get("probabilidade_media_por_classe") or {}
        total_predicted = sum(int(value) for value in classes.values())
        normal_predicted = int(classes.get("0", 0))
        failure_predicted = total_predicted - normal_predicted
        failure_probability = sum(
            float(value) for label, value in probabilities.items() if label != "0"
        )
        nominal_ratio = item.get("proporcao_nominal_gerada")
        anomaly_ratio = item.get("proporcao_anormal_gerada")
        rows.append(
            {
                "Regime": REGIME_LABELS.get(regime, regime),
                "Leituras totais": int(item.get("leituras", 0)),
                "Leituras com perfil": int(
                    item.get(
                        "leituras_com_perfil",
                        int(item.get("nominais", 0)) + int(item.get("anormais", 0)),
                    )
                ),
                "Nominais gerados": int(item.get("nominais", 0)),
                "Anormais gerados": int(item.get("anormais", 0)),
                "% nominal gerado": (
                    f"{float(nominal_ratio):.1%}" if nominal_ratio is not None else "—"
                ),
                "% anormal gerado": (
                    f"{float(anomaly_ratio):.1%}" if anomaly_ratio is not None else "—"
                ),
                "Normais previstos": normal_predicted,
                "Falhas previstas": failure_predicted,
                "Prob. média de falha": (
                    f"{failure_probability:.1%}" if probabilities else "—"
                ),
                "Inferência média (ms)": (
                    f"{float(item['tempo_medio_inferencia_ms']):.2f}"
                    if item.get("tempo_medio_inferencia_ms") is not None
                    else "—"
                ),
            }
        )
        for code, label in CLASS_NAMES.items():
            detail_rows.append(
                {
                    "Regime": REGIME_LABELS.get(regime, regime),
                    "Classe prevista": CLASS_LABEL.get(label, label),
                    "Quantidade": int(classes.get(str(code), 0)),
                    "Probabilidade média": (
                        f"{float(probabilities.get(str(code), 0.0)):.1%}"
                        if probabilities
                        else "—"
                    ),
                }
            )

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        "Proporções nominais/anormais e classes previstas referem-se apenas às leituras "
        "com perfil sintético registrado. As proporções descrevem o gerador; as classes "
        "e probabilidades são a reação real do modelo e não forçam sua saída."
    )
    with st.expander("Distribuição detalhada das classes previstas e probabilidades"):
        st.dataframe(
            pd.DataFrame(detail_rows), use_container_width=True, hide_index=True
        )

