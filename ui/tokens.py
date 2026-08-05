"""Tokens y CSS compartidos del port de Viaje del dinero.

Este módulo no contiene cálculos ni acceso a datos: solo define la base visual
que las fases posteriores reutilizarán.
"""

SURFACE = "#fcf9f8"
SURFACE_LOW = "#f6f3f2"
SURFACE_HIGH = "#eae7e7"
INK = "#1a1a1a"
MUTED = "#5a6670"
NAVY = "#021c36"
BLUE = "#006497"
BLUE_HOVER = "#004f79"
BLUE_SOFT = "rgba(0, 100, 151, 0.10)"
BORDER = "#d9dee3"
SUCCESS = "#1f8a5b"
WARNING = "#c9821f"
DANGER = "#a32d2d"


def base_css() -> str:
    """Devuelve el CSS fundacional para la primera fase del port."""
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

      :root {{
        --vd-surface: {SURFACE};
        --vd-surface-low: {SURFACE_LOW};
        --vd-surface-high: {SURFACE_HIGH};
        --vd-ink: {INK};
        --vd-muted: {MUTED};
        --vd-navy: {NAVY};
        --vd-blue: {BLUE};
        --vd-blue-hover: {BLUE_HOVER};
        --vd-blue-soft: {BLUE_SOFT};
        --vd-border: {BORDER};
      }}

      html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {{
        background: var(--vd-surface);
        color: var(--vd-ink);
        font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      }}
      [data-testid="stHeader"], [data-testid="stToolbar"], footer {{
        visibility: hidden;
      }}
      .block-container {{
        max-width: 1280px;
        padding-top: 2.25rem;
        padding-bottom: 3rem;
      }}
      section[data-testid="stSidebar"] {{
        background: var(--vd-surface-low);
        border-right: 1px solid var(--vd-border);
      }}
      section[data-testid="stSidebar"] > div {{
        padding-top: 1.5rem;
      }}
      .vd-brand {{
        color: var(--vd-navy);
        font-size: 0.73rem;
        font-weight: 800;
        letter-spacing: 0.13em;
        margin: 0 0 0.25rem;
        text-transform: uppercase;
      }}
      .vd-brand-subtitle {{
        color: var(--vd-muted);
        font-size: 0.75rem;
        line-height: 1.45;
        margin: 0 0 1.5rem;
      }}
      [data-testid="stSidebar"] [role="radiogroup"] {{ gap: 0.25rem; }}
      [data-testid="stSidebar"] label[data-baseweb="radio"] {{
        border-left: 3px solid transparent;
        padding: 0.48rem 0.6rem;
      }}
      [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {{
        background: var(--vd-blue-soft);
        border-left-color: var(--vd-blue);
      }}
      [data-testid="stSidebar"] label[data-baseweb="radio"] p {{
        color: var(--vd-ink);
        font-size: 0.82rem;
        font-weight: 600;
      }}
      .vd-eyebrow {{
        color: var(--vd-blue);
        font-size: 0.69rem;
        font-weight: 800;
        letter-spacing: 0.13em;
        margin: 0 0 0.6rem;
        text-transform: uppercase;
      }}
      .vd-title {{
        color: var(--vd-navy);
        font-size: clamp(2rem, 5vw, 3.65rem);
        font-weight: 800;
        letter-spacing: -0.045em;
        line-height: 0.98;
        margin: 0;
      }}
      .vd-lede {{
        color: var(--vd-muted);
        font-size: 1.05rem;
        line-height: 1.65;
        margin: 1.1rem 0 0;
        max-width: 43rem;
      }}
      .vd-divider {{
        border: 0;
        border-top: 1px solid var(--vd-border);
        margin: 2.25rem 0;
      }}
      .vd-stage {{
        background: var(--vd-surface-low);
        border-left: 3px solid var(--vd-blue);
        margin-top: 1.5rem;
        padding: 1.5rem;
      }}
      .vd-stage h2 {{
        color: var(--vd-navy);
        font-size: 1.1rem;
        letter-spacing: -0.02em;
        margin: 0 0 0.45rem;
      }}
      .vd-stage p {{
        color: var(--vd-muted);
        line-height: 1.55;
        margin: 0;
      }}
      @media (max-width: 700px) {{
        .block-container {{ padding: 1.4rem 1rem 2rem; }}
        .vd-stage {{ padding: 1.15rem; }}
      }}
    </style>
    """
