"""Tokens del sistema visual del artifact (solo presentación).

GENERADO POR `tools/extract_design_system.py` — NO EDITAR A MANO.
Los valores salen del bloque `:root` del demo del artifact. Si hay que cambiarlos,
se cambia el demo y se regenera; así el port no puede divergir de su fuente.
"""

FONTS = {
    'font-display': '"Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, Georgia, "Times New Roman", serif',
    'font-mono': '"JetBrains Mono", "Fira Code", "Space Mono", ui-monospace, "SF Mono", "SFMono-Regular", Menlo, Consolas, monospace',
    'font-sans': 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
}

LIGHT = {
    'ground': '#f4f7fa',
    'panel': '#ffffff',
    'panel-tint': '#eef4f9',
    'ink': '#021C36',
    'ink-2': '#33475a',
    'ink-mut': '#6a7b8a',
    'hair': '#d5e0ea',
    'hair-soft': '#e6edf3',
    'anchor': '#021C36',
    'drip': '#006497',
    'cash': '#1f8a5b',
    'loss': '#A32D2D',
    'loss-soft': '#cf8a8a',
    'loss-bg': 'rgba(163,45,45,0.10)',
    'accent': '#006497',
    'accent-tint': 'rgba(0,100,151,0.10)',
    'warn': '#a06a1a',
    'mark': '#534AB7',
    'sq-off': '#dbe3ea',
    'tip-bg': '#021C36',
    'tip-ink': '#eaf2f8',
}

DARK = {
    'ground': '#0b1420',
    'panel': '#101d2b',
    'panel-tint': '#142639',
    'ink': '#eaf1f7',
    'ink-2': '#c3d1de',
    'ink-mut': '#8598a9',
    'hair': '#26394c',
    'hair-soft': '#1c2c3c',
    'anchor': '#b9c9d8',
    'drip': '#3ea0d6',
    'cash': '#35b07d',
    'loss': '#e07a7a',
    'loss-soft': '#9c5555',
    'loss-bg': 'rgba(224,122,122,0.14)',
    'accent': '#3ea0d6',
    'accent-tint': 'rgba(62,160,214,0.14)',
    'sq-off': '#2b4056',
    'tip-bg': '#eaf1f7',
    'tip-ink': '#0b1420',
    'warn': '#d9a441',
    'mark': '#AFA9EC',
}

THEMES = {"Claro": LIGHT, "Oscuro": DARK}


def css_variables(theme: str = "Claro") -> str:
    """Bloque `:root` con los tokens del tema pedido, listo para inyectar."""
    tokens = THEMES.get(theme, LIGHT)
    lines = [f"        --{k}: {v};" for k, v in {**FONTS, **tokens}.items()]
    return ":root {\n" + "\n".join(lines) + "\n        }"
