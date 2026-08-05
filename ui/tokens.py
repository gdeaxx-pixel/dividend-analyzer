"""Tokens y CSS compartidos del port de Viaje del dinero (solo presentación)."""

LIGHT = {
    "surface": "#fcf9f8",
    "surface_low": "#f6f3f2",
    "surface_high": "#eae7e7",
    "ink": "#1a1a1a",
    "muted": "#5a6670",
    "navy": "#021c36",
    "blue": "#006497",
    "blue_hover": "#004f79",
    "blue_soft": "rgba(0, 100, 151, 0.10)",
    "border": "#d9dee3",
}

DARK = {
    "surface": "#111820",
    "surface_low": "#18232e",
    "surface_high": "#24313d",
    "ink": "#f2f6f8",
    "muted": "#b8c4cc",
    "navy": "#f2f6f8",
    "blue": "#65c5ed",
    "blue_hover": "#9bdcff",
    "blue_soft": "rgba(101, 197, 237, 0.16)",
    "border": "#354755",
}


def base_css(theme: str) -> str:
    """Devuelve CSS responsivo para el tema activo persistido en session_state."""
    tokens = DARK if theme == "Oscuro" else LIGHT
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
      :root {{
        --vd-surface: {tokens['surface']};
        --vd-surface-low: {tokens['surface_low']};
        --vd-surface-high: {tokens['surface_high']};
        --vd-ink: {tokens['ink']};
        --vd-muted: {tokens['muted']};
        --vd-navy: {tokens['navy']};
        --vd-blue: {tokens['blue']};
        --vd-blue-hover: {tokens['blue_hover']};
        --vd-blue-soft: {tokens['blue_soft']};
        --vd-border: {tokens['border']};
      }}
      html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {{
        background: var(--vd-surface); color: var(--vd-ink);
        font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      }}
      [data-testid="stHeader"], [data-testid="stToolbar"], footer {{ visibility: hidden; }}
      .block-container {{ max-width: 1280px; padding-top: 2.25rem; padding-bottom: 3rem; }}
      section[data-testid="stSidebar"] {{ background: var(--vd-surface-low); border-right: 1px solid var(--vd-border); }}
      section[data-testid="stSidebar"] > div {{ padding-top: 1.5rem; }}
      .vd-brand {{ color: var(--vd-navy); font-size: .73rem; font-weight: 800; letter-spacing: .13em; margin: 0 0 .25rem; text-transform: uppercase; }}
      .vd-brand-subtitle {{ color: var(--vd-muted); font-size: .75rem; line-height: 1.45; margin: 0 0 1.5rem; }}
      .vd-nav-label {{ color: var(--vd-muted); font-size: .68rem; font-weight: 800; letter-spacing: .11em; margin: 1rem 0 .35rem; text-transform: uppercase; }}
      [data-testid="stSidebar"] [data-baseweb="select"] > div, [data-testid="stSidebar"] [data-baseweb="radio"] {{ color: var(--vd-ink); }}
      [data-testid="stSidebar"] label[data-baseweb="radio"] {{ border-left: 3px solid transparent; border-radius: 0 .35rem .35rem 0; padding: .42rem .55rem; }}
      [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {{ background: var(--vd-blue-soft); border-left-color: var(--vd-blue); }}
      [data-testid="stSidebar"] label[data-baseweb="radio"] p {{ color: var(--vd-ink); font-size: .82rem; font-weight: 600; }}
      .vd-breadcrumb {{ align-items: center; color: var(--vd-muted); display: flex; flex-wrap: wrap; font-size: .78rem; gap: .45rem; margin-bottom: 1.8rem; }}
      .vd-home {{ color: var(--vd-blue); font-weight: 700; }}
      .vd-crumb-separator {{ color: var(--vd-muted); font-size: 1.05rem; }}
      .vd-eyebrow {{ color: var(--vd-blue); font-size: .69rem; font-weight: 800; letter-spacing: .13em; margin: 0 0 .6rem; text-transform: uppercase; }}
      .vd-title {{ color: var(--vd-navy); font-size: clamp(2rem, 5vw, 3.65rem); font-weight: 800; letter-spacing: -.045em; line-height: .98; margin: 0; }}
      .vd-lede {{ color: var(--vd-muted); font-size: 1.05rem; line-height: 1.65; margin: 1.1rem 0 0; max-width: 43rem; }}
      .vd-divider {{ border: 0; border-top: 1px solid var(--vd-border); margin: 2.25rem 0; }}
      .vd-stage {{ background: var(--vd-surface-low); border-left: 3px solid var(--vd-blue); margin-top: 1.5rem; padding: 1.5rem; }}
      .vd-stage-kicker {{ color: var(--vd-blue); font-size: .69rem; font-weight: 800; letter-spacing: .1em; margin: 0 0 .5rem; text-transform: uppercase; }}
      .vd-stage h2 {{ color: var(--vd-navy); font-size: 1.1rem; letter-spacing: -.02em; margin: 0 0 .45rem; }}
      .vd-stage p {{ color: var(--vd-muted); line-height: 1.55; margin: 0; }}
      @media (max-width: 700px) {{
        .block-container {{ padding: 1.4rem 1rem 2rem; }}
        .vd-breadcrumb {{ margin-bottom: 1.25rem; }}
        .vd-stage {{ padding: 1.15rem; }}
      }}
    </style>
    """
