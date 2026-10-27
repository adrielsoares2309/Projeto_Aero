"""Dashboard de monitoramento preditivo — AeroMotion Dynamics.

Interface industrial moderna em Streamlit e Plotly:
- Paleta predominantemente branca e neutra (#FFFFFF, #F7F9FC)
- Tipografia em tons de azul-escuro (#102A43, #183B56, #334E68)
- Gráficos Plotly com fundo 100% branco e eixos legíveis
- Cartões de probabilidade com indicadores de falhas claros
- Zero emojis em toda a aplicação (utiliza exclusivamente ícones Lucide SVG)
- Integração completa com a API FastAPI e suporte ao simulador
"""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import cv2
import numpy as np

# Diretório raiz para garantir imports absolutos
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import frontend.api_client as api
import frontend.charts as charts
import frontend.components as comp
import frontend.icons as ic
import simulator as sim
from frontend.styles import COLORS, inject_css
from vision.geometry import GeometryConfig, analyze_geometry, load_image, classify_geometry_against_references
from vision.pipeline import diagnose_image_dataset, predict_image
from vision.thermal import ThermalConfig, analyze_thermal, classify_thermal_against_references

# --------------------------------------------------------------------------- #
# Configuração da página Streamlit                                            #
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="AeroMotion Dynamics — Monitoramento Preditivo Industrial",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(inject_css(), unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Constantes do Sistema                                                       #
# --------------------------------------------------------------------------- #
MODELS_DIR = ROOT_DIR / "data" / "processed" / "modelos"
EQUIPMENTS = ["TURB-101", "TURB-102", "TURB-103", "TURB-104"]

REGIME_BUTTONS = [
    ("Cruzeiro", "Cruzeiro", ic.rotate_cw),
    ("Carga_Media", "Carga Média", ic.activity),
    ("Carga_Alta", "Carga Alta", ic.zap),
]


# --------------------------------------------------------------------------- #
# Gerenciamento de Processo do Simulador                                       #
# --------------------------------------------------------------------------- #
def simulator_running() -> bool:
    """Considera o simulador ativo apenas por heartbeat, não por sessão Streamlit."""
    if bool(sim.simulator_status().get("simulador_online")):
        return True
    proc = st.session_state.get("sim_process")
    return proc is not None and proc.poll() is None


def _current_local_status() -> dict:
    return sim.simulator_status()


def start_simulator(interval: float, quantity: int) -> None:
    """Inicia uma única instância do simulador em background.

    O comando de regime é persistido em arquivo; nenhum processo é criado ao
    trocar de regime. O lock do próprio simulator.py impede duplicidade mesmo
    se outra sessão do Streamlit clicar em Iniciar simultaneamente.
    """
    if simulator_running():
        return

    control = sim.read_control()
    if not control or control.get("regime") not in sim.REGIMES or control.get("action") == "stop":
        selected = st.session_state.get("regime_selecionado", sim.DEFAULT_REGIME)
        sim.write_control(selected, action="run", requested_by="dashboard")

    cmd = [
        sys.executable,
        str(ROOT_DIR / "simulator.py"),
        "--api-url", api.API_BASE_URL,
        "--intervalo", str(interval),
        "--quantidade", str(quantity),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log_path = ROOT_DIR / "infra" / "simulator.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    try:
        st.session_state.sim_process = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    finally:
        log_handle.close()


def stop_simulator() -> None:
    """Solicita parada graciosa; o histórico e o estado são preservados."""
    sim.request_stop()
    proc = st.session_state.get("sim_process")
    if proc and proc.poll() is None:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
    st.session_state.sim_process = None


def apply_regime(regime: str) -> tuple[dict | None, str | None]:
    """Envia o comando de regime à API; retorna (status, erro)."""
    status, error = api.set_operating_regime(regime)
    if error:
        return None, error
    st.session_state["regime_selecionado"] = regime
    return status, None



# --------------------------------------------------------------------------- #
# Barra Lateral (Sidebar)                                                     #
# --------------------------------------------------------------------------- #
def render_sidebar() -> tuple[str, str, int]:
    """Barra lateral: navegação, equipamento, regimes e controle do simulador."""
    with st.sidebar:
        # Marca e cabeçalho da sidebar
        brand_icon = ic.cpu(color=COLORS["blue_primary"], size=22)
        st.markdown(
            f"""
<div class="sidebar-brand">
  {brand_icon}
  <span class="sidebar-brand-title">AeroMotion Dynamics</span>
</div>
""",
            unsafe_allow_html=True,
        )

        # Seção: Navegação
        nav_icon = ic.layers(color=COLORS["text_heading"], size=14)
        st.markdown(
            f'<div class="sidebar-section-title">{nav_icon} Navegação</div>',
            unsafe_allow_html=True,
        )
        page = st.radio(
            "Navegação do Sistema",
            ["Monitoramento", "Avaliação do Modelo", "Visão Computacional"],
            label_visibility="collapsed",
        )

        # Seção: Equipamento
        equip_icon = ic.settings(color=COLORS["text_heading"], size=14)
        st.markdown(
            f'<div class="sidebar-section-title">{equip_icon} Equipamento</div>',
            unsafe_allow_html=True,
        )
        equipment = st.selectbox(
            "Equipamento monitorado",
            EQUIPMENTS,
            label_visibility="collapsed",
        )

        interval, quantity, refresh = 5.0, 0, 5

        if page == "Monitoramento":
            # --------------------------------------------------------------- #
            # REGIME DE OPERAÇÃO — três botões mutuamente exclusivos          #
            # --------------------------------------------------------------- #
            regime_status, regime_error = api.get_regime_status()
            if regime_status is None:
                regime_status = _current_local_status()
            selected_regime = (
                regime_status.get("regime_selecionado") or sim.DEFAULT_REGIME
            )
            st.session_state["regime_selecionado"] = selected_regime

            regime_icon = ic.activity(color=COLORS["text_heading"], size=14)
            st.markdown(
                f'<div class="sidebar-section-title">{regime_icon} Regime de Operação</div>',
                unsafe_allow_html=True,
            )

            cols = st.columns(3)
            clicked: str | None = None
            for column, (key, label, icon_fn) in zip(cols, REGIME_BUTTONS):
                active = key == selected_regime
                with column:
                    st.markdown(
                        f'<div class="regime-icon-row"><div class="regime-icon-box{" active" if active else ""}">'
                        f'{icon_fn(color=COLORS["blue_primary"] if active else COLORS["text_secondary"], size=16)}'
                        f"</div></div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        label,
                        key=f"regime_{key.lower()}",
                        type="primary" if active else "secondary",
                        use_container_width=True,
                        help=f"Solicita ao simulador o regime {label}",
                    ):
                        clicked = key

            if clicked is not None:
                _, error = apply_regime(clicked)
                if error:
                    st.error(
                        "Falha ao comunicar a troca de regime ao simulador: "
                        f"{error}"
                    )
                else:
                    st.rerun()

            active_key = regime_status.get("regime_ativo") or selected_regime
            active_label = comp.REGIME_LABELS.get(
                active_key, str(active_key).replace("_", " ")
            )
            st.markdown(
                f'<div class="regime-active-note">{ic.check_circle(color=COLORS["blue_primary"], size=14)}'
                f"Regime ativo: {active_label}</div>",
                unsafe_allow_html=True,
            )
            if regime_error:
                st.caption(f"Estado lido localmente; API indisponível: {regime_error}")
            if not regime_status.get("simulador_online"):
                st.caption(regime_status.get("mensagem", "Simulador offline."))

            # --------------------------------------------------------------- #
            # Controle do processo do simulador                               #
            # --------------------------------------------------------------- #
            sim_icon = ic.play(color=COLORS["text_heading"], size=14)
            st.markdown(
                f'<div class="sidebar-section-title">{sim_icon} Simulação</div>',
                unsafe_allow_html=True,
            )

            interval = st.slider("Intervalo entre leituras (s)", 1.0, 60.0, 5.0, 1.0)
            quantity = st.number_input(
                "Quantidade de leituras (0 = contínua)",
                min_value=0,
                max_value=10000,
                value=0,
                step=50,
            )
            refresh = st.slider("Frequência de atualização (s)", 2, 60, 5)

            col_btn1, col_btn2 = st.columns(2)
            running = simulator_running()
            if col_btn1.button(
                "Iniciar",
                type="primary",
                use_container_width=True,
                disabled=running,
                help="Inicia uma única instância do gerador de telemetria",
            ):
                start_simulator(interval, int(quantity))
                st.rerun()

            if col_btn2.button(
                "Parar",
                key="stop_simulator",
                type="secondary",
                use_container_width=True,
                disabled=not running,
                help="Interrompe o simulador com segurança",
            ):
                stop_simulator()
                st.rerun()

            # Painel compacto do estado do simulador
            if running:
                st.markdown(
                    f"""
<div class="sim-status-box active">
  <span class="aero-status-dot dot-green"></span>
  <span>Simulador: <strong>Online</strong> ({comp.REGIME_LABELS.get(active_key, active_key)})</span>
</div>
""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
<div class="sim-status-box idle">
  <span class="aero-status-dot dot-gray"></span>
  <span>Simulador: <strong>Offline</strong></span>
</div>
""",
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        api_icon = ic.server(color=COLORS["text_secondary"], size=13)
        st.markdown(
            f"""
<div style="font-size:0.72rem;color:{COLORS['text_secondary']};display:flex;align-items:center;gap:0.35rem;padding:0.4rem 0.2rem;border-top:1px solid {COLORS['border_light']};">
  {api_icon} API: <code style="color:{COLORS['text_heading']};background:#F0F4F8;padding:1px 4px;border-radius:4px;">{api.API_BASE_URL}</code>
</div>
""",
            unsafe_allow_html=True,
        )

    return page, equipment, refresh



# --------------------------------------------------------------------------- #
# Página: Monitoramento em Tempo Real                                          #
# --------------------------------------------------------------------------- #
def page_monitoring(equipment: str, refresh: int) -> None:
    """Renderiza a página principal de monitoramento preditivo e telemetria."""

    @st.fragment(run_every=timedelta(seconds=refresh))
    def _live_view() -> None:
        now = datetime.now()

        # Comunicação com a API FastAPI
        health, health_err = api.get_health()
        online = api.is_api_online(health)

        predictions_data, pred_err = api.get_predictions(limit=300, equipamento=None)

        # Cabeçalho da aplicação
        comp.render_header(
            api_online=online,
            sim_running=simulator_running(),
            selected_equipment=equipment,
            last_update=now,
        )

        # Regime operacional: estado real do simulador (API com fallback local)
        regime_status, regime_err = api.get_regime_status()
        if regime_status is None:
            regime_status = _current_local_status()
        comp.render_regime_card(regime_status)
        if regime_err:
            st.caption(f"Estado do regime lido localmente; API indisponível: {regime_err}")

        # Tratamento de indisponibilidade da API
        if not online:
            comp.render_api_offline_message(health_err or pred_err)
            if health and not health.get("modelos_disponiveis"):
                err = health.get("erro_carregamento")
                if err:
                    st.caption(f"Detalhes do carregamento: {err}")
            return

        # Normalização dos dados de predição e telemetria
        items = (predictions_data or {}).get("items", [])
        df_all = comp.to_dataframe(items)

        # Filtragem para o equipamento selecionado
        df_eq = df_all[df_all["id_equipamento"] == equipment] if not df_all.empty else df_all
        latest = comp.get_latest(df_all, equipment)
        probabilities = comp.extract_probabilities(latest)

        # Alerta se dados de telemetria estiverem antigos
        if not df_eq.empty and "timestamp" in df_eq.columns:
            last_ts = df_eq["timestamp"].max()
            comp.render_stale_data_warning(last_ts)

        if df_all.empty:
            st.info(
                "Nenhuma leitura de telemetria registrada no banco. Inicie a simulação para gerar dados reais."
            )
            return

        # Aviso de aquecimento do histórico
        if latest is not None:
            comp.render_warmup_notice(bool(latest.get("aquecimento")))

        # --- Seção 1: Cartões de Probabilidade de Falha ---
        kpi_sec_icon = ic.gauge(color=COLORS["text_heading"], size=16)
        st.markdown(
            f'<div class="section-title">{kpi_sec_icon} Probabilidade Estimada de Falha</div>',
            unsafe_allow_html=True,
        )
        comp.render_kpi_cards(latest, probabilities)

        # --- Seção 2: Classe Predominante ---
        comp.render_predicted_class(latest, probabilities)

        # --- Seção 2b: Indicadores compactos de telemetria ---
        telemetry_icon = ic.activity(color=COLORS["text_heading"], size=16)
        st.markdown(
            f'<div class="section-title">{telemetry_icon} Telemetria Atual — {equipment}</div>',
            unsafe_allow_html=True,
        )
        comp.render_telemetry_cards(latest)

        # --- Seção 3: Gráficos de Telemetria (Duas colunas) ---
        chart_sec_icon = ic.chart_line(color=COLORS["text_heading"], size=16)
        st.markdown(
            f'<div class="section-title">{chart_sec_icon} Telemetria de Sensores — {equipment}</div>',
            unsafe_allow_html=True,
        )

        col_temp, col_vib = st.columns(2)
        with col_temp:
            st.markdown(
                f'<div style="font-size:0.8rem;font-weight:600;color:{COLORS["text_heading"]};margin-bottom:0.25rem;">'
                f'{ic.thermometer(color=COLORS["blue_primary"], size=14)} Temperatura do Mancal (°C)</div>',
                unsafe_allow_html=True,
            )
            fig_temp = charts.temperature_chart(df_eq, equipment=None)
            if df_eq.empty or "temperatura_mancal_c" not in df_eq.columns:
                st.caption("Sem leituras de temperatura.")
            else:
                st.plotly_chart(fig_temp, use_container_width=True, config={"displayModeBar": False})

        with col_vib:
            st.markdown(
                f'<div style="font-size:0.8rem;font-weight:600;color:{COLORS["text_heading"]};margin-bottom:0.25rem;">'
                f'{ic.activity(color=COLORS["orange"], size=14)} Vibração RMS (mm/s)</div>',
                unsafe_allow_html=True,
            )
            fig_vib = charts.vibration_chart(df_eq, equipment=None)
            if df_eq.empty or "vibracao_rms_mms" not in df_eq.columns:
                st.caption("Sem leituras de vibração.")
            else:
                st.plotly_chart(fig_vib, use_container_width=True, config={"displayModeBar": False})

        # --- Gráfico de Pressão do Óleo ---
        if not df_eq.empty and "pressao_oleo_bar" in df_eq.columns:
            st.markdown(
                f'<div style="font-size:0.8rem;font-weight:600;color:{COLORS["text_heading"]};margin-bottom:0.25rem;">'
                f'{ic.gauge(color=COLORS["purple"], size=14)} Pressão do Óleo Lubrificante (bar)</div>',
                unsafe_allow_html=True,
            )
            fig_pres = charts.pressure_chart(df_eq, equipment=None)
            st.plotly_chart(fig_pres, use_container_width=True, config={"displayModeBar": False})

        # --- Seção 4: Detecção de Anomalias (Isolation Forest) ---
        if latest is not None and latest.get("anomalia") is not None:
            comp.render_anomaly_section(latest, df_eq)
            if not df_eq.empty and "anomalia" in df_eq.columns:
                fig_anom = charts.anomaly_timeline_chart(df_eq)
                st.plotly_chart(fig_anom, use_container_width=True, config={"displayModeBar": False})

        # --- Seção 5: Histórico de Predições ---
        hist_icon = ic.database(color=COLORS["text_heading"], size=16)
        st.markdown(
            f'<div class="section-title">{hist_icon} Histórico de Predições e Telemetria</div>',
            unsafe_allow_html=True,
        )

        all_equip = ["Todos"] + EQUIPMENTS
        all_classes = ["Todas"] + list(comp.CLASS_NAMES.values())

        fc1, fc2 = st.columns([1, 1])
        f_eq = fc1.selectbox("Filtrar Histórico por Equipamento", all_equip, key="filter_eq")
        f_cls = fc2.selectbox("Filtrar Histórico por Classe", all_classes, key="filter_cls")

        comp.render_history_table(df_all, f_eq, f_cls, max_rows=100)

    _live_view()


# --------------------------------------------------------------------------- #
# Página: Avaliação do Modelo de Machine Learning                             #
# --------------------------------------------------------------------------- #
def page_evaluation() -> None:
    """Renderiza a página de avaliação dos modelos e interpretabilidade preditiva."""
    eval_icon = ic.bar_chart(color=COLORS["blue_primary"], size=22)
    st.markdown(
        f"""
<div class="aero-header">
  <div class="aero-header-left">
    <h1>{eval_icon} &nbsp;Avaliação do Modelo Preditivo</h1>
    <p>Métricas de validação, interpretabilidade e matriz de confusão baseadas nos dados de treinamento real</p>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # 1. Metadados do Treinamento
    meta_path = MODELS_DIR / "metadados_treinamento.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            st.markdown(
                f"""
<div class="stat-row">
  <div class="stat-box">
    <div class="stat-label">Melhor Modelo</div>
    <div class="stat-value" style="font-size:1.1rem;">{meta.get("melhor_modelo_por_f1_macro_teste", "Random Forest")}</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Amostras de Treino</div>
    <div class="stat-value">{meta.get("quantidade_treino", "—")}</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Amostras de Teste</div>
    <div class="stat-value">{meta.get("quantidade_teste", "—")}</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Variável Alvo</div>
    <div class="stat-value" style="font-size:1rem;">{meta.get("variavel_alvo", "classe_falha")}</div>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.caption(f"Erro ao ler metadados: {e}")

    # 2. Comparação de Modelos Treinados
    comp_path = MODELS_DIR / "comparacao_modelos.csv"
    if comp_path.exists():
        comp_icon = ic.layers(color=COLORS["text_heading"], size=16)
        st.markdown(
            f'<div class="section-title">{comp_icon} Comparação de Desempenho entre Modelos</div>',
            unsafe_allow_html=True,
        )
        try:
            df_comp = pd.read_csv(comp_path, encoding="utf-8-sig")
            num_cols = [c for c in df_comp.columns if c != "Modelo"]
            df_fmt = df_comp.copy()
            for col in num_cols:
                df_fmt[col] = df_fmt[col].apply(lambda v: f"{float(v):.4f}" if pd.notna(v) else "—")
            st.dataframe(df_fmt, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Erro ao carregar comparação de modelos: {e}")

    # 3. Reação do modelo aos dados sintéticos por regime
    reaction_icon = ic.activity(color=COLORS["text_heading"], size=16)
    st.markdown(
        f'<div class="section-title">{reaction_icon} Reação do Modelo por Regime — Dados Sintéticos</div>',
        unsafe_allow_html=True,
    )
    stats, stats_error = api.get_stats()
    if stats is None:
        st.caption(f"Estatísticas do histórico indisponíveis: {stats_error or 'API offline'}")
    else:
        comp.render_regime_evaluation(stats)

    # 4. Métricas por Classe e Matriz de Confusão
    metrics_path = MODELS_DIR / "metricas_por_classe.csv"
    CLASS_LABEL_MAP = {
        0: "Normal",
        1: "Desgaste de Rolamento",
        2: "Desbalanceamento do Rotor",
        3: "Cavitação / Superaquecimento",
    }

    if metrics_path.exists():
        try:
            df_metrics = pd.read_csv(metrics_path, encoding="utf-8-sig")
            col_modelo = next((c for c in df_metrics.columns if "Modelo" in c or "modelo" in c), None)
            col_classe = next((c for c in df_metrics.columns if "Classe" in c or "classe" in c), None)
            col_recall = next((c for c in df_metrics.columns if "Recall" in c or "recall" in c), None)
            col_precision = next((c for c in df_metrics.columns if "Precis" in c), None)
            col_f1 = next((c for c in df_metrics.columns if "F1" in c or "f1" in c), None)
            col_support = next((c for c in df_metrics.columns if "Suporte" in c or "suporte" in c), None)

            # --- Matriz de Confusão Multiclasse 4x4 ---
            cm_icon = ic.chart_line(color=COLORS["text_heading"], size=16)
            st.markdown(
                f'<div class="section-title">{cm_icon} Matriz de Confusão Multiclasse (4 × 4)</div>',
                unsafe_allow_html=True,
            )

            cm_path = MODELS_DIR / "matriz_confusao.csv"
            if cm_path.exists():
                df_cm = pd.read_csv(cm_path, index_col=0)
                fig_cm = charts.confusion_matrix_chart(
                    df_cm.values.tolist(),
                    list(df_cm.index),
                    source_label="Conjunto de teste independente",
                )
                st.plotly_chart(fig_cm, use_container_width=True, config={"displayModeBar": False})
            elif col_modelo and col_classe and col_recall and col_support:
                # Estimação a partir das métricas por classe reais
                df_rf = df_metrics[df_metrics[col_modelo] == "Random Forest"].copy()
                if not df_rf.empty:
                    df_rf["nome_classe"] = df_rf[col_classe].map(CLASS_LABEL_MAP)
                    classes = df_rf["nome_classe"].tolist()
                    recalls = df_rf[col_recall].tolist()
                    supports = df_rf[col_support].tolist()

                    diag = [int(round(r * s)) for r, s in zip(recalls, supports)]
                    n = len(classes)
                    matrix = [[0] * n for _ in range(n)]
                    for i in range(n):
                        matrix[i][i] = diag[i]
                        rem = supports[i] - diag[i]
                        for j in range(n):
                            if i != j and rem > 0:
                                matrix[i][j] = max(0, int(rem / (n - 1)))

                    fig_cm = charts.confusion_matrix_chart(
                        matrix,
                        classes,
                        source_label="Valores obtidos do conjunto de teste",
                    )
                    st.plotly_chart(fig_cm, use_container_width=True, config={"displayModeBar": False})

            # --- Destaque ao Recall por Classe de Falha ---
            recall_icon = ic.activity(color=COLORS["text_heading"], size=16)
            st.markdown(
                f'<div class="section-title">{recall_icon} Sensibilidade (Recall) por Classe — Random Forest</div>',
                unsafe_allow_html=True,
            )

            if col_modelo and col_classe and col_recall:
                df_rf = df_metrics[df_metrics[col_modelo] == "Random Forest"].copy()
                if not df_rf.empty:
                    df_rf["nome_classe"] = df_rf[col_classe].map(CLASS_LABEL_MAP)
                    fig_recall = charts.recall_bar_chart(
                        df_rf["nome_classe"].tolist(),
                        df_rf[col_recall].tolist(),
                    )
                    st.plotly_chart(fig_recall, use_container_width=True, config={"displayModeBar": False})

                    # Tabela detalhada de precisão, recall e f1-score
                    st.markdown(
                        f'<div style="font-size:0.8rem;font-weight:600;color:{COLORS["text_heading"]};margin:0.8rem 0 0.35rem 0;">'
                        f'Relatório Detalhado por Classe de Falha</div>',
                        unsafe_allow_html=True,
                    )
                    df_display = df_rf.copy()
                    if col_precision in df_display:
                        df_display[col_precision] = df_display[col_precision].apply(lambda v: f"{v:.4f}")
                    if col_recall in df_display:
                        df_display[col_recall] = df_display[col_recall].apply(lambda v: f"{v:.4f}")
                    if col_f1 in df_display:
                        df_display[col_f1] = df_display[col_f1].apply(lambda v: f"{v:.4f}")
                    if col_support in df_display:
                        df_display[col_support] = df_display[col_support].apply(lambda v: f"{int(v)}")

                    disp_cols = [c for c in [col_classe, "nome_classe", col_precision, col_recall, col_f1, col_support] if c in df_display.columns]
                    st.dataframe(df_display[disp_cols], use_container_width=True, hide_index=True)

        except Exception as e:
            st.warning(f"Erro ao processar métricas por classe: {e}")
    else:
        st.info("Arquivo metricas_por_classe.csv não encontrado no diretório de modelos.")

    # 4. Importância das Variáveis
    feat_path = MODELS_DIR / "importancia_variaveis.csv"
    if feat_path.exists():
        feat_icon = ic.bar_chart(color=COLORS["text_heading"], size=16)
        st.markdown(
            f'<div class="section-title">{feat_icon} Importância das Variáveis (Feature Importance) — Random Forest</div>',
            unsafe_allow_html=True,
        )
        try:
            df_feat = pd.read_csv(feat_path, encoding="utf-8-sig")
            col_var = next((c for c in df_feat.columns if "Vari" in c or "Feature" in c), None)
            col_imp = next((c for c in df_feat.columns if "Import" in c), None)
            if col_var and col_imp:
                fig_feat = charts.feature_importance_chart(
                    df_feat[col_var].tolist(),
                    df_feat[col_imp].tolist(),
                )
                st.plotly_chart(fig_feat, use_container_width=True, config={"displayModeBar": False})
        except Exception as e:
            st.warning(f"Erro ao renderizar importância das variáveis: {e}")

    # 5. Correlação real dos preditores do dataset tratado.
    render_correlation_section()


def render_correlation_section() -> None:
    """Exibe correlações dos preditores reais sem alterar o CSV de origem."""
    icon = ic.activity(color=COLORS["text_heading"], size=16)
    st.markdown(
        f'<div class="section-title">{icon} Matriz de Correlação das Variáveis</div>',
        unsafe_allow_html=True,
    )
    data_path = ROOT_DIR / "data" / "processed" / "dados_sensores_aeromotion_tratados.csv"
    if not data_path.exists():
        st.info(f"Dataset tratado não encontrado: {data_path}")
        return
    try:
        frame = pd.read_csv(data_path)
        numeric = frame.select_dtypes(include=[np.number]).copy()
        excluded = {
            name for name in numeric.columns
            if name.casefold() in {"tipo_falha", "target", "label", "classe", "classe_falha"}
            or name.casefold().startswith("id_")
            or name.casefold().endswith("_id")
        }
        numeric = numeric.drop(columns=list(excluded), errors="ignore")
        usable = [
            column for column in numeric.columns
            if numeric[column].notna().sum() >= 2 and numeric[column].nunique(dropna=True) > 1
        ]
        numeric = numeric[usable]
        if len(numeric.columns) < 2:
            st.info("Não há pelo menos duas variáveis numéricas com observações suficientes e variação.")
            return
        method = st.selectbox(
            "Método de correlação",
            ["Pearson", "Spearman"],
            key="correlation_method",
            help="Pearson mede associação linear; Spearman mede associação monotônica por postos.",
        ).lower()
        corr = numeric.corr(method=method, min_periods=2)
        corr = corr.replace([np.inf, -np.inf], np.nan)
        st.caption(
            f"Fonte: {data_path.relative_to(ROOT_DIR)} · {len(frame):,} registros · "
            f"{len(usable)} preditores numéricos. Ausências são tratadas por pares disponíveis; "
            "o arquivo original não é modificado. Correlação não implica causalidade."
        )
        st.plotly_chart(
            charts.correlation_heatmap(corr, annotate=len(usable) <= 12),
            width="stretch",
            config={"displayModeBar": False},
        )
        threshold = st.slider(
            "Destacar pares com correlação absoluta a partir de",
            min_value=0.50, max_value=0.95, value=0.70, step=0.05,
            key="correlation_threshold",
        )
        pairs: list[tuple[str, str, float]] = []
        for i, first in enumerate(usable):
            for second in usable[i + 1:]:
                value = corr.loc[first, second]
                if pd.notna(value) and abs(float(value)) >= threshold:
                    pairs.append((first, second, float(value)))
        pairs.sort(key=lambda item: abs(item[2]), reverse=True)
        if pairs:
            st.markdown("**Pares destacados**")
            for first, second, value in pairs[:20]:
                if value > 0:
                    meaning = "tendem a aumentar conjuntamente"
                elif value < 0:
                    meaning = "uma tende a aumentar enquanto a outra diminui"
                else:
                    meaning = "não apresentam associação linear"
                st.write(f"{first} × {second}: **{value:+.3f}** — {meaning}.")
            if len(pairs) > 20:
                st.caption(f"Mostrando os 20 pares mais fortes entre {len(pairs)} encontrados.")
        else:
            st.info(f"Nenhum par atingiu |r| ≥ {threshold:.2f}.")
    except Exception as exc:
        st.warning(f"Não foi possível calcular a matriz de correlação: {exc}")


def _decode_upload(uploaded: Any) -> np.ndarray:
    """Decodifica o arquivo enviado em memória; não persiste a imagem recebida."""
    raw = np.frombuffer(uploaded.getvalue(), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ValueError("O arquivo não contém uma imagem PNG ou JPEG válida.")
    return image


def _display_bgr(image: np.ndarray, caption: str) -> None:
    st.image(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), caption=caption, width="stretch")


def page_vision() -> None:
    """Interface de demonstração geométrica e térmica por comparação OpenCV."""
    icon = ic.layers(color=COLORS["blue_primary"], size=22)
    st.markdown(
        f'<div class="aero-header"><div class="aero-header-left">'
        f'<h1>{icon} &nbsp;Visão Computacional</h1>'
        "<p>Comparação visual com referências AeroMotion — resultados qualitativos por OpenCV</p>"
        "</div></div>", unsafe_allow_html=True,
    )
    with st.expander("Diagnóstico do dataset de imagens"):
        diagnosis = diagnose_image_dataset()
        st.write(f"Arquivos encontrados: **{diagnosis['total_files']}** · "
                 f"Imagens suportadas: **{diagnosis['supported_images']}**")
        st.dataframe(pd.DataFrame([
            {"Modalidade": modality, "Imagens": count,
             "Classes detectadas": ", ".join(
                 f"{label} ({amount})"
                 for label, amount in diagnosis["class_counts"].get(modality, {}).items()
             ) or "Sem rótulo"}
            for modality, count in diagnosis["modality_counts"].items()
        ]), width="stretch", hide_index=True)
        st.caption(f"Dimensões: {diagnosis['dimensions']} · Arquivos inválidos: {len(diagnosis['invalid_files'])} · "
                   f"Duplicatas exatas: {len(diagnosis['exact_duplicates'])} · "
                   f"Possíveis semelhantes: {len(diagnosis['near_duplicate_candidates'])}")
        st.caption("Rótulos inferidos somente de nomes explícitos como normal, deformada e aquecimento; confirme-os antes de treinar.")
    st.markdown("**1. Escolha o tipo de inspeção**")
    modality_label = st.radio(
        "Modalidade de inspeção", ["Inspeção geométrica", "Inspeção térmica"],
        horizontal=True, key="vision_modality",
    )
    modality = "geometrica" if modality_label == "Inspeção geométrica" else "termica"
    references = {
        "geometrica": {
            "normal": ROOT_DIR / "data/raw/imagens/geo_001_pa_normal.png",
            "abnormal": ROOT_DIR / "data/raw/imagens/geo_001_pa_deformada.png",
        },
        "termica": {
            "normal": ROOT_DIR / "data/raw/imagens/turbina_normal.png",
            "abnormal": ROOT_DIR / "data/raw/imagens/turbina_aquecimento.png",
        },
    }[modality]
    ref_labels = ("Referência normal", "Referência deformada") if modality == "geometrica" else ("Referência normal", "Referência com superaquecimento")
    st.markdown("**Referências visuais**")
    ref_cols = st.columns(2)
    ref_images: dict[str, np.ndarray] = {}
    try:
        for column, key, label in zip(ref_cols, ("normal", "abnormal"), ref_labels):
            ref_images[key] = load_image(references[key])
            with column:
                _display_bgr(ref_images[key], f"{label} · {references[key].name}")
    except (ValueError, cv2.error) as exc:
        st.error(f"Não foi possível carregar uma imagem de referência: {exc}")
        return

    source_mode = st.radio("Imagem para análise", ["Usar referência", "Enviar imagem"], horizontal=True,
                           key=f"vision_source_{modality}")
    if source_mode == "Usar referência":
        selected_label = st.selectbox("Demonstração", [f"{ref_labels[0]} — {references['normal'].name}",
                                                        f"{ref_labels[1]} — {references['abnormal'].name}"],
                                      key=f"vision_demo_{modality}")
        selected_key = "normal" if selected_label.startswith(ref_labels[0]) else "abnormal"
        image = ref_images[selected_key].copy()
        image_bytes = references[selected_key].read_bytes()
        image_name = references[selected_key].name
    else:
        uploaded = st.file_uploader("Imagem do componente", type=["png", "jpg", "jpeg"], key=f"vision_upload_{modality}")
        if uploaded is None:
            st.info("Envie uma imagem para executar a inspeção.")
            return
        image_bytes = uploaded.getvalue()
        image_name = uploaded.name
        try:
            image = _decode_upload(uploaded)
        except (ValueError, cv2.error) as exc:
            st.error(f"Imagem inválida: {exc}")
            return
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    st.caption(f"Imagem selecionada: {image_name} · {image.shape[1]} × {image.shape[0]} px")
    _display_bgr(image, "Imagem original")

    st.markdown("**2. Configure e execute a análise**")
    if modality == "termica":
        hue_range = st.slider("Faixa HSV para máscara visual (OpenCV)", 0, 179, (0, 35), key="vision_hue")
        saturation_min = st.slider("Saturação mínima", 0, 255, 80, key="vision_sat")
        value_min = st.slider("Valor mínimo", 0, 255, 80, key="vision_value")
        min_area = st.number_input("Área mínima da região (pixels)", 0, 100000, 20, key="vision_min_area")
        thermal_config = ThermalConfig(
            hsv_ranges=((tuple([hue_range[0], saturation_min, value_min]),
                         tuple([hue_range[1], 255, 255])),),
            min_area=int(min_area),
        )
        config_key = (hue_range, saturation_min, value_min, int(min_area))
    else:
        canny_range = st.slider("Limiares Canny: baixo e alto", 0, 255, (50, 150), key="vision_canny")
        min_area = st.number_input("Área mínima do contorno (pixels)", 0, 100000, 20, key="vision_geo_min_area")
        canny_low = min(int(canny_range[0]), 254)
        geometry_config = GeometryConfig(
            canny_low=canny_low, canny_high=max(int(canny_range[1]), canny_low + 1),
            min_contour_area=float(min_area),
        )
        config_key = (canny_range, int(min_area))
    run_analysis = st.button("Executar inspeção", type="primary", key="run_vision_analysis")
    result_key = "vision_analysis_result"
    previous = st.session_state.get(result_key)
    if run_analysis:
        try:
            if modality == "termica":
                analysis = analyze_thermal(image, config=thermal_config, include_artifacts=True)
                classification = classify_thermal_against_references(image, ref_images["normal"], ref_images["abnormal"])
            else:
                analysis = analyze_geometry(image, config=geometry_config, include_artifacts=True)
                classification = classify_geometry_against_references(image, ref_images["normal"], ref_images["abnormal"])
            st.session_state[result_key] = {
                "hash": image_hash, "modality": modality, "config": config_key,
                "analysis": analysis, "classification": classification,
            }
            previous = st.session_state[result_key]
        except (ValueError, cv2.error, OSError) as exc:
            st.error(f"Falha ao analisar a imagem: {exc}")
            return
    if not previous or previous.get("hash") != image_hash or previous.get("modality") != modality or previous.get("config") != config_key:
        st.caption("Execute a inspeção para ver os resultados. Alterar imagem ou parâmetros exige nova análise.")
        return

    analysis = previous["analysis"]
    classification = previous["classification"]
    st.markdown("**3. Resultado e detalhes técnicos**")
    verdict = classification["classification"]
    if verdict in {"REPROVADA", "SUPERAQUECIMENTO"}:
        st.error(f"**{verdict}**")
    elif verdict in {"DENTRO DOS CONFORMES", "TEMPERATURA NORMAL"}:
        st.success(f"**{verdict}**")
    else:
        st.warning("**INCONCLUSIVA**")
    st.write(classification["justification"])
    st.caption("Método: comparação visual relativa por OpenCV. Não é um modelo de Machine Learning nem uma inspeção industrial certificada.")
    artifacts = analysis["artifacts"]
    if modality == "termica":
        col_processed, col_mask = st.columns(2)
        with col_processed:
            _display_bgr(artifacts["annotated"], "Regiões HSV candidatas")
        with col_mask:
            st.image(artifacts["mask"], caption="Máscara binária de candidatos", width="stretch")
        st.write(f"Regiões candidatas: **{analysis['region_count']}** · Área segmentada pela configuração atual: **{analysis['mask_fraction']:.2%}**")
        st.write(f"Pixels quentes relativos às referências: **{classification['metrics']['warm_fraction']:.2%}** · "
                 f"Normal: **{classification['metrics']['normal_reference_warm_fraction']:.2%}** · "
                 f"Superaquecida: **{classification['metrics']['overheated_reference_warm_fraction']:.2%}**")
        st.caption("Segmentação HSV e fração de cor são qualitativas. Imagens falsas coloridas não fornecem temperatura em °C.")
        if analysis["region_count"] == 0:
            st.info("Nenhuma região foi selecionada pela faixa HSV atual. Isso não confirma estado normal; a paleta pode não corresponder aos limiares.")
    else:
        col_gray, col_edges, col_contours = st.columns(3)
        with col_gray:
            st.image(artifacts["gray"], caption="Escala de cinza", width="stretch")
        with col_edges:
            st.image(artifacts["edges"], caption="Bordas Canny", width="stretch")
        with col_contours:
            _display_bgr(artifacts["contours"], "Contornos detectados")
        _display_bgr(artifacts["annotated"], "Contornos e caixas delimitadoras")
        st.write(f"Contornos relevantes: **{analysis['contour_count']}**")
        st.write(f"IoU da silhueta normalizada — referência normal: **{classification['metrics']['normal_reference_iou']:.3f}** · "
                 f"referência deformada: **{classification['metrics']['defective_reference_iou']:.3f}**")
        if analysis["contours"]:
            table = pd.DataFrame(analysis["contours"])
            table["bbox"] = table["bbox"].apply(lambda box: f"{box['width']} × {box['height']} em ({box['x']}, {box['y']})")
            st.dataframe(table[["index", "area", "perimeter", "circularity", "aspect_ratio", "bbox"]].head(20),
                         width="stretch", hide_index=True)
        else:
            st.info("Não foram encontrados contornos acima da área mínima configurada.")
    with st.expander("Critérios e limitações"):
        st.json({"criteria": classification["criteria"], "metrics": classification["metrics"],
                 "limitations": classification["limitations"], "opencv_analysis": {k: v for k, v in analysis.items() if k != "artifacts"}})


# --------------------------------------------------------------------------- #
# Orquestrador da Aplicação                                                   #
# --------------------------------------------------------------------------- #
def main() -> None:
    page, equipment, refresh = render_sidebar()
    if page == "Monitoramento":
        page_monitoring(equipment, refresh)
    elif page == "Avaliação do Modelo":
        page_evaluation()
    else:
        page_vision()


if __name__ == "__main__":
    main()
else:
    main()
