"""Tema CSS e estilos visuais do dashboard AeroMotion Dynamics.

Identidade visual industrial moderna:
- Predominantemente branco (#FFFFFF) e fundo neutro (#F7F9FC)
- Textos em tons de azul-escuro (#102A43, #183B56, #334E68)
- Textos auxiliares com contraste adequado (#627D98)
- Bordas e divisórias discretas (#D9E2EC, #DCE4EE)
- Azul institucional para botões e interações (#1565C0)
- Indicadores semânticos de falhas:
    - Verde (#16803C) para operação normal
    - Amarelo / âmbar (#B77900) para alertas / desgaste
    - Laranja (#C05621) para desbalanceamento
    - Vermelho (#C62828) para falhas críticas / cavitação
- Zero emojis: apenas ícones SVG consistentes da biblioteca Lucide.
"""

PLOTLY_TEMPLATE = "plotly_white"

COLORS = {
    # Fundos
    "bg_page": "#F7F9FC",
    "bg_card": "#FFFFFF",
    "bg_sidebar": "#FFFFFF",
    "bg_secondary": "#FFFFFF",
    "bg_hover": "#F0F4F8",
    "bg_header": "#FFFFFF",

    # Bordas e divisórias
    "border": "#D9E2EC",
    "border_sidebar": "#DCE4EE",
    "border_light": "#EDF2F7",
    "border_accent": "#E7EDF4",

    # Tipografia / Textos
    "text_title": "#102A43",        # Títulos principais (~26-30px, ~16-19px)
    "text_primary": "#102A43",      # Compatibilidade
    "text_heading": "#183B56",      # Títulos secundários
    "text_body": "#334E68",         # Texto comum (~14-16px)
    "text_secondary": "#627D98",    # Textos auxiliares (~12-13px)
    "text_muted": "#829AB1",        # Rótulos discretos com contraste garantido

    # Azul institucional
    "blue_primary": "#1565C0",      # Botões e elementos interativos principais
    "blue_hover": "#0D47A1",        # Hover
    "blue_light": "#1E88E5",        # Linhas de dados e destaques
    "blue_pale": "#E3F0FF",         # Fundo de seleção ativa
    "blue_border": "#B9D7FB",       # Borda de seleção

    # Estados semânticos operacionais
    "green": "#16803C",             # Operação normal / limites seguros
    "green_bg": "#ECFDF5",
    "green_border": "#A7F3D0",

    "yellow": "#B77900",            # Alertas / Desgaste
    "yellow_bg": "#FFFBEB",
    "yellow_border": "#FDE68A",

    "orange": "#E65100",            # Vibração RMS e Desbalanceamento
    "orange_bg": "#FFF7ED",
    "orange_border": "#FFEDD5",

    "purple": "#6A1B9A",            # Pressão do óleo e variáveis secundárias
    "teal": "#00796B",              # Destaque de variáveis e séries adicionais
    "slate": "#526579",             # Eixos e rótulos auxiliares

    "red": "#C62828",               # Falhas críticas / fora da faixa
    "red_bg": "#FEF2F2",
    "red_border": "#FECACA",

    # Classes do modelo
    "normal": "#16803C",
    "desgaste": "#B77900",
    "desbalanceamento": "#E65100",
    "cavitacao": "#C62828",

    # Paleta Oficial Plotly (Alto Contraste no Fundo Branco)
    "chart_bg": "#FFFFFF",
    "chart_grid": "#D9E2EC",
    "chart_blue": "#1565C0",        # Temperatura do mancal e séries principais
    "chart_orange": "#E65100",      # Vibração RMS e séries secundárias
    "chart_purple": "#6A1B9A",      # Pressão do óleo
    "chart_green": "#16803C",       # Condição normal e faixa segura
    "chart_amber": "#B77900",       # Alertas e atenção
    "chart_red": "#C62828",         # Falhas críticas e fora dos limites
    "chart_teal": "#00796B",        # Destaque de variáveis
    "chart_slate": "#526579",       # Eixos e rótulos auxiliares
    "chart_line": "#1565C0",
    "chart_line_secondary": "#1E88E5",
    "chart_line_vib": "#E65100",
    "chart_pres": "#6A1B9A",
}

CLASS_COLORS = {
    "Normal": COLORS["normal"],
    "Desgaste_Rolamento": COLORS["desgaste"],
    "Desbalanceamento_Rotor": COLORS["desbalanceamento"],
    "Cavitacao_Superaquecimento": COLORS["cavitacao"],
}


def inject_css() -> str:
    """Retorna o CSS institucional injetado no Streamlit."""
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap');

/* ── Resets globais ── */
html, body, [class*="css"], .stApp {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    color: {COLORS['text_body']};
    background-color: {COLORS['bg_page']} !important;
}}

/* ── Container principal ── */
.main .block-container {{
    padding-top: 1rem !important;
    padding-bottom: 2.5rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    max-width: 1440px;
    background-color: {COLORS['bg_page']};
}}

/* ── Barra Lateral (Sidebar) ── */
section[data-testid="stSidebar"] {{
    background-color: {COLORS['bg_sidebar']} !important;
    border-right: 1px solid {COLORS['border_sidebar']} !important;
}}
section[data-testid="stSidebar"] > div:first-child {{
    background-color: {COLORS['bg_sidebar']} !important;
}}
section[data-testid="stSidebar"] .block-container {{
    padding-top: 1.25rem !important;
    padding-bottom: 1.5rem !important;
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
}}

/* Seções e Títulos da Sidebar */
.sidebar-brand {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.5rem 0.25rem 1rem 0.25rem;
    margin-bottom: 0.5rem;
    border-bottom: 1px solid {COLORS['border_light']};
}}
.sidebar-brand-title {{
    font-size: 1rem;
    font-weight: 700;
    color: {COLORS['text_title']};
    letter-spacing: -0.01em;
}}
.sidebar-section-title {{
    display: flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {COLORS['text_heading']};
    margin: 1.15rem 0 0.5rem 0;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid {COLORS['border_light']};
}}

/* Rótulos e textos da Sidebar */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] .stNumberInput label {{
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    color: {COLORS['text_heading']} !important;
    margin-bottom: 0.25rem !important;
}}

/* Controles de Navegação (stRadio na sidebar) */
section[data-testid="stSidebar"] [data-testid="stRadio"] > div[role="radiogroup"] {{
    gap: 0.35rem;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 0.55rem 0.85rem;
    margin-bottom: 0.2rem;
    transition: all 0.15s ease-in-out;
    cursor: pointer;
    display: flex;
    align-items: center;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
    background: {COLORS['bg_hover']};
    border-color: {COLORS['blue_border']};
}}
/* Item ativo da navegação: fundo azul-claro, texto azul-escuro, borda esquerda azul */
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {{
    background: {COLORS['blue_pale']} !important;
    border-color: {COLORS['blue_border']} !important;
    border-left: 3.5px solid {COLORS['blue_primary']} !important;
    font-weight: 600 !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p,
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) span {{
    color: {COLORS['text_title']} !important;
    font-weight: 600 !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label p {{
    font-size: 0.86rem !important;
    color: {COLORS['text_body']} !important;
    margin: 0 !important;
}}

/* Sliders e Controles Numéricos com alto contraste */
.stSlider [data-testid="stTickBar"] span,
.stSlider div[data-testid="stThumbValue"] {{
    color: {COLORS['text_heading']} !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
}}
.stSlider p {{
    color: {COLORS['text_secondary']} !important;
    font-size: 0.75rem !important;
}}
.stNumberInput input {{
    color: {COLORS['text_title']} !important;
    font-weight: 600 !important;
    background: {COLORS['bg_card']} !important;
    border-color: {COLORS['border']} !important;
}}

/* Selectbox padronizado */
div[data-baseweb="select"] > div {{
    background-color: {COLORS['bg_card']} !important;
    border-color: {COLORS['border']} !important;
    border-radius: 6px !important;
    color: {COLORS['text_title']} !important;
    font-size: 0.85rem !important;
    min-height: 38px !important;
}}
div[data-baseweb="select"] > div:hover {{
    border-color: {COLORS['blue_primary']} !important;
}}

/* Botões da Sidebar (Iniciar / Parar) */
.stButton > button {{
    border-radius: 6px !important;
    font-size: 0.84rem !important;
    font-weight: 600 !important;
    padding: 0.5rem 0.9rem !important;
    min-height: 38px !important;
    transition: all 0.15s ease-in-out !important;
    box-shadow: 0 1px 2px rgba(16,42,67,0.04) !important;
}}
/* Botão Iniciar (type="primary") */
button[kind="primary"],
button[data-testid="baseButton-primary"] {{
    background-color: {COLORS['blue_primary']} !important;
    border: 1px solid {COLORS['blue_primary']} !important;
    color: #FFFFFF !important;
}}
button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover {{
    background-color: {COLORS['blue_hover']} !important;
    border-color: {COLORS['blue_hover']} !important;
    color: #FFFFFF !important;
}}
/* Botão secundário padrão (regimes inativos e ações neutras) */
button[kind="secondary"],
button[data-testid="baseButton-secondary"] {{
    background-color: #FFFFFF !important;
    border: 1px solid {COLORS['border']} !important;
    color: {COLORS['text_heading']} !important;
}}
button[kind="secondary"]:hover,
button[data-testid="baseButton-secondary"]:hover {{
    background-color: {COLORS['blue_pale']} !important;
    border-color: {COLORS['blue_border']} !important;
    color: {COLORS['blue_primary']} !important;
}}
/* Botão Parar do simulador */
.st-key-stop_simulator button {{
    background-color: #FFFFFF !important;
    border: 1px solid {COLORS['red_border']} !important;
    color: {COLORS['red']} !important;
}}
.st-key-stop_simulator button:hover {{
    background-color: {COLORS['red_bg']} !important;
    border-color: {COLORS['red']} !important;
    color: {COLORS['red']} !important;
}}
/* Regime ativo: botão primário azul institucional */
.st-key-regime_cruzeiro button[kind="primary"],
.st-key-regime_carga_media button[kind="primary"],
.st-key-regime_carga_alta button[kind="primary"] {{
    box-shadow: 0 0 0 2px {COLORS['blue_pale']} !important;
}}

/* Ícones dos botões de regime */
.regime-icon-row {{
    display: flex;
    justify-content: center;
    margin: 0.15rem 0 0.3rem 0;
}}
.regime-icon-box {{
    width: 30px;
    height: 30px;
    border-radius: 6px;
    background: {COLORS['bg_page']};
    border: 1px solid {COLORS['border']};
    display: flex;
    align-items: center;
    justify-content: center;
}}
.regime-icon-box.active {{
    background: {COLORS['blue_pale']};
    border-color: {COLORS['blue_border']};
}}
.regime-active-note {{
    display: flex;
    align-items: center;
    gap: 0.45rem;
    margin-top: 0.55rem;
    padding: 0.5rem 0.7rem;
    border-radius: 6px;
    background: {COLORS['blue_pale']};
    border: 1px solid {COLORS['blue_border']};
    font-size: 0.78rem;
    font-weight: 600;
    color: {COLORS['text_title']};
}}

/* Painel de status do simulador */
.sim-status-box {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 7px;
    padding: 0.55rem 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.55rem;
    font-size: 0.78rem;
    margin-top: 0.6rem;
}}
.sim-status-box.active {{
    background: {COLORS['green_bg']};
    border-color: {COLORS['green_border']};
    color: {COLORS['green']};
}}
.sim-status-box.idle {{
    background: {COLORS['bg_page']};
    border-color: {COLORS['border']};
    color: {COLORS['text_secondary']};
}}
.sim-status-box strong {{
    font-weight: 600;
}}

/* ── Cartão de Regime Operacional ── */
.regime-card {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-left: 3.5px solid {COLORS['blue_primary']};
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin-bottom: 1.1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.25rem;
    box-shadow: 0 1px 3px rgba(16,42,67,0.04);
}}
.regime-card-left {{
    display: flex;
    align-items: center;
    gap: 0.9rem;
    min-width: 0;
}}
.regime-card-icon {{
    width: 42px;
    height: 42px;
    border-radius: 8px;
    background: {COLORS['bg_page']};
    border: 1px solid {COLORS['border']};
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}}
.regime-card-tag {{
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {COLORS['text_secondary']};
    margin-bottom: 0.15rem;
}}
.regime-card-name {{
    font-size: 1.15rem;
    font-weight: 700;
    color: {COLORS['text_title']};
    line-height: 1.2;
}}
.regime-card-meta {{
    font-size: 0.75rem;
    color: {COLORS['text_secondary']};
    margin-top: 0.25rem;
}}
.regime-card-meta strong {{
    color: {COLORS['text_heading']};
    font-weight: 600;
}}
.regime-card-right {{
    text-align: right;
    flex-shrink: 0;
}}
.regime-card-status {{
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.76rem;
    color: {COLORS['text_body']};
    background: {COLORS['bg_page']};
    border: 1px solid {COLORS['border']};
    border-radius: 16px;
    padding: 0.3rem 0.7rem;
}}
.regime-card-note {{
    font-size: 0.7rem;
    color: {COLORS['text_muted']};
    margin-top: 0.3rem;
    max-width: 430px;
}}

/* ── Indicadores de Telemetria ── */
.telemetry-grid {{
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 0.8rem;
    margin-bottom: 1.1rem;
}}
@media (max-width: 1200px) {{
    .telemetry-grid {{ grid-template-columns: repeat(3, 1fr); }}
}}
@media (max-width: 700px) {{
    .telemetry-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
.telemetry-card {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 0.8rem 0.9rem;
    box-shadow: 0 1px 3px rgba(16,42,67,0.04);
}}
.telemetry-top {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
    margin-bottom: 0.35rem;
}}
.telemetry-label {{
    font-size: 0.7rem;
    font-weight: 600;
    color: {COLORS['text_heading']};
    line-height: 1.25;
}}
.telemetry-icon {{
    display: flex;
    flex-shrink: 0;
}}
.telemetry-value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.25rem;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.02em;
}}
.telemetry-unit {{
    font-size: 0.66rem;
    font-weight: 600;
    color: {COLORS['text_secondary']};
    margin-left: 0.25rem;
    font-family: 'Inter', sans-serif;
}}

/* ── Cabeçalho Principal ── */
.aero-header {{
    background: {COLORS['bg_header']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 1.1rem 1.6rem;
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.5rem;
    box-shadow: 0 1px 3px rgba(16,42,67,0.04);
}}
.aero-header-left h1 {{
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    color: {COLORS['text_title']} !important;
    margin: 0 0 0.2rem 0 !important;
    line-height: 1.2 !important;
    letter-spacing: -0.02em !important;
}}
.aero-header-left p {{
    font-size: 0.84rem !important;
    color: {COLORS['text_secondary']} !important;
    margin: 0 !important;
    font-weight: 500 !important;
}}
.aero-header-left strong {{
    color: {COLORS['text_title']};
    font-weight: 600;
}}
.aero-header-right {{
    display: flex;
    align-items: center;
    gap: 0.65rem;
    flex-wrap: wrap;
    justify-content: flex-end;
}}
.aero-status-badge, .aero-status-chip {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    background: {COLORS['bg_page']};
    border: 1px solid {COLORS['border']};
    border-radius: 20px;
    padding: 0.35rem 0.75rem;
    font-size: 0.74rem;
    font-weight: 500;
    color: {COLORS['text_secondary']};
    white-space: nowrap;
}}
.aero-status-badge .badge-title,
.aero-status-chip .chip-title {{
    color: {COLORS['text_heading']};
    font-weight: 600;
}}
.aero-status-badge .label,
.aero-status-chip .label {{
    color: {COLORS['text_body']};
    font-weight: 600;
}}
.aero-status-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
}}
.dot-green  {{ background-color: {COLORS['green']}; box-shadow: 0 0 0 2px {COLORS['green_border']}; }}
.dot-red    {{ background-color: {COLORS['red']}; box-shadow: 0 0 0 2px {COLORS['red_border']}; }}
.dot-yellow {{ background-color: {COLORS['yellow']}; box-shadow: 0 0 0 2px {COLORS['yellow_border']}; }}
.dot-gray   {{ background-color: {COLORS['text_muted']}; }}

/* ── Títulos de Seção ── */
.section-title {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.82rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {COLORS['text_heading']};
    margin: 1.4rem 0 0.8rem 0;
    padding-bottom: 0.45rem;
    border-bottom: 1px solid {COLORS['border_light']};
}}

/* ── Cartões de Probabilidade de Falha (KPI Cards) ── */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.25rem;
}}
@media (max-width: 1024px) {{
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 600px) {{
    .kpi-grid {{ grid-template-columns: 1fr; }}
}}
.kpi-card {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 1.15rem 1.25rem 1.1rem 1.25rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(16,42,67,0.04);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.kpi-card:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(16,42,67,0.08);
}}
.kpi-card .kpi-top {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 0.75rem;
}}
.kpi-card .kpi-label {{
    font-size: 0.82rem;
    font-weight: 600;
    color: {COLORS['text_heading']};
    line-height: 1.3;
    flex: 1;
    padding-right: 0.5rem;
}}
.kpi-card .kpi-icon {{
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.kpi-card .kpi-value {{
    font-size: 1.95rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    line-height: 1.1;
    margin-bottom: 0.4rem;
    letter-spacing: -0.02em;
}}
.kpi-card .kpi-sub {{
    font-size: 0.72rem;
    color: {COLORS['text_secondary']};
    line-height: 1.3;
}}
.kpi-card .kpi-bar,
.kpi-card .kpi-accent-bar {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 3px;
}}

/* ── Seção de Classe Predominante ── */
.predicted-class-box {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 1.1rem 1.4rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.25rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 1px 3px rgba(16,42,67,0.04);
}}
.predicted-class-box .pclass-left {{
    display: flex;
    align-items: center;
    gap: 1rem;
    flex: 1;
    min-width: 0;
}}
.predicted-class-box .pclass-icon-wrapper {{
    width: 44px;
    height: 44px;
    border-radius: 8px;
    background: {COLORS['bg_page']};
    border: 1px solid {COLORS['border']};
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}}
.predicted-class-box .pclass-main {{
    flex: 1;
    min-width: 0;
}}
.predicted-class-box .pclass-tag {{
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {COLORS['text_secondary']};
    margin-bottom: 0.2rem;
}}
.predicted-class-box .pclass-name {{
    font-size: 1.18rem;
    font-weight: 700;
    color: {COLORS['text_title']};
    line-height: 1.25;
}}
.predicted-class-box .pclass-meta {{
    font-size: 0.76rem;
    color: {COLORS['text_secondary']};
    margin-top: 0.25rem;
}}
.predicted-class-box .pclass-prob-wrapper {{
    text-align: right;
    flex-shrink: 0;
}}
.predicted-class-box .pclass-prob-label {{
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {COLORS['text_secondary']};
    margin-bottom: 0.2rem;
}}
.predicted-class-box .pclass-prob {{
    font-size: 1.75rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1;
}}

/* ── Avisos e Notificações ── */
.failure-notice, .notice-error {{
    background: {COLORS['red_bg']};
    border: 1px solid {COLORS['red_border']};
    border-left: 3.5px solid {COLORS['red']};
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-size: 0.82rem;
    color: {COLORS['text_title']};
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.85rem;
    line-height: 1.4;
}}
.warmup-notice, .notice-warning {{
    background: {COLORS['yellow_bg']};
    border: 1px solid {COLORS['yellow_border']};
    border-left: 3.5px solid {COLORS['yellow']};
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-size: 0.82rem;
    color: {COLORS['text_title']};
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.85rem;
    line-height: 1.4;
}}
.notice-info {{
    background: {COLORS['blue_pale']};
    border: 1px solid {COLORS['blue_border']};
    border-left: 3.5px solid {COLORS['blue_primary']};
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-size: 0.82rem;
    color: {COLORS['text_title']};
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.85rem;
    line-height: 1.4;
}}

/* ── Detector de Anomalias ── */
.anomaly-container {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 0.85rem 1.1rem;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}}
.anomaly-indicator {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.78rem;
    padding: 0.35rem 0.85rem;
    border-radius: 20px;
    font-weight: 600;
    border: 1px solid;
}}
.anomaly-yes {{
    background: {COLORS['red_bg']};
    color: {COLORS['red']};
    border-color: {COLORS['red_border']};
}}
.anomaly-no {{
    background: {COLORS['green_bg']};
    color: {COLORS['green']};
    border-color: {COLORS['green_border']};
}}
.anomaly-unknown {{
    background: {COLORS['bg_page']};
    color: {COLORS['text_secondary']};
    border-color: {COLORS['border']};
}}

/* ── Tabela de Dados e Dataframe ── */
[data-testid="stDataFrame"] {{
    background: {COLORS['bg_card']} !important;
    border: 1px solid {COLORS['border']} !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 3px rgba(16,42,67,0.03) !important;
}}
[data-testid="stDataFrame"] th {{
    background-color: #F8FAFC !important;
    color: {COLORS['text_heading']} !important;
    font-weight: 600 !important;
    font-size: 0.8rem !important;
    border-bottom: 1px solid {COLORS['border']} !important;
}}
[data-testid="stDataFrame"] td {{
    color: {COLORS['text_body']} !important;
    font-size: 0.82rem !important;
}}

/* ── Cartões de Estatísticas (Página de Avaliação) ── */
.stat-row {{
    display: flex;
    gap: 1rem;
    margin-bottom: 1.4rem;
    flex-wrap: wrap;
}}
.stat-box {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 0.95rem 1.25rem;
    flex: 1;
    min-width: 150px;
    box-shadow: 0 1px 3px rgba(16,42,67,0.04);
}}
.stat-box .stat-label {{
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {COLORS['text_secondary']};
    margin-bottom: 0.35rem;
    font-weight: 600;
}}
.stat-box .stat-value {{
    font-size: 1.4rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: {COLORS['blue_primary']};
    line-height: 1.2;
}}

/* ── Gráficos Plotly: Container Card com SVG Transparente ── */
div[data-testid="stPlotlyChart"] {{
    background-color: #FFFFFF !important;
    border: 1px solid #D9E2EC !important;
    border-radius: 8px !important;
    padding: 0.5rem 0.5rem 0.25rem 0.5rem !important;
    box-shadow: 0 1px 3px rgba(16, 42, 67, 0.04) !important;
    margin-bottom: 0.75rem !important;
}}

/* O SVG interno do Plotly DEVE ser transparente para não cobrir as curvas e dados */
div[data-testid="stPlotlyChart"] svg,
div[data-testid="stPlotlyChart"] .main-svg {{
    background: transparent !important;
}}

/* Ocultar barra de ferramentas flutuante do Plotly para visual limpo */
.modebar-container {{
    display: none !important;
}}
</style>
"""
