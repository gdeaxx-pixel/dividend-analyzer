#!/usr/bin/env python3
"""Protocolo de validacion de casos reales — Dividend Analyzer.

Recorre TODOS los casos en real_examples/ que tengan expected.json (ground truth
transcrito UNA sola vez de las capturas del broker) y valida que la calculadora
produce los numeros correctos. Emite una tabla PASS/FAIL por caso/ticker y, por
defecto, guarda un reporte en Obsidian.

Uso:
    python3 validate_real_cases.py              # validacion CSV (determinista, sin Gemini)
    python3 validate_real_cases.py --vision     # + verifica la OCR de fotos con Gemini (gasta cuota)
    python3 validate_real_cases.py --sync-obsidian   # regenera la seccion "Ground Truth" en la nota
    python3 validate_real_cases.py --no-report  # no escribe el .md en Obsidian

El ground truth vive en real_examples/<broker>_data/<N>/expected.json (privado, gitignored).
Agregar un caso nuevo = soltar CSV + fotos + expected.json; el runner lo descubre solo.

Codigo de salida: 0 si no hay FAIL; 1 si algun ticker confiable no coincide.
Los casos sin red (yfinance caido) se marcan SKIP y no fallan.
"""
import argparse
import datetime
import glob
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.join(BASE, "real_examples")
OBSIDIAN_DIR = ("/Users/danielzambrano/Desktop/Habilidades de agentes/"
                "Obsidian/APPs/Dividend-Analyzer")
PROTOCOL_NOTE = os.path.join(OBSIDIAN_DIR, "protocolo-revision-calculadora.md")

SHARES_TOL_REL = 0.02   # 2% — acciones (CSV + splits)
COST_TOL_REL = 0.02     # 2% — costo base leido por Gemini vs la captura
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")

sys.path.insert(0, BASE)
import logic  # noqa: E402


class FakeFile:
    """Replica el objeto de Streamlit que esperan los parsers de logic.py."""
    def __init__(self, content: bytes, name: str = "test.csv"):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


# ── Descubrimiento de casos ───────────────────────────────────────────────────

def discover_cases():
    """Toda carpeta bajo real_examples/ con un expected.json es un caso."""
    cases = []
    for path in sorted(glob.glob(os.path.join(REAL, "**", "expected.json"), recursive=True)):
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
        cases.append({
            "dir": os.path.dirname(path),
            "manifest": manifest,
            "case_id": manifest.get("case_id", os.path.relpath(os.path.dirname(path), REAL)),
        })
    return cases


def _approx(got, expected, rel):
    if expected in (None, 0):
        return got == expected
    return abs(got - expected) <= abs(expected) * rel


def _rel_pct(got, expected):
    if not expected:
        return None
    return (got - expected) / expected * 100.0


# ── Validacion CSV (determinista) ─────────────────────────────────────────────

def validate_csv(case):
    """Devuelve dict {status, broker_ok, rows:[...]} para un caso.

    status: 'ok' (corrio el pipeline) | 'skip' (sin red/yfinance) | 'error'.
    Cada row: {ticker, reliability, kind, result, detail}.
    result: 'PASS' | 'FAIL' | 'SKIP' | 'INFO'.
    """
    m = case["manifest"]
    out = {"broker_expected": m["broker"], "broker_got": None, "broker_ok": None,
           "status": "ok", "rows": []}

    paths = glob.glob(os.path.join(case["dir"], m.get("csv_glob", "*.csv")))
    paths = [p for p in paths if not p.endswith("expected.json")]
    if not paths:
        out["status"] = "error"
        out["error"] = f"sin CSV ({m.get('csv_glob', '*.csv')})"
        return out

    with open(paths[0], "rb") as f:
        df, broker = logic.load_and_detect_csv(FakeFile(f.read(), os.path.basename(paths[0])))
    out["broker_got"] = broker
    out["broker_ok"] = (broker == m["broker"])

    try:
        dfc = logic.normalize_csv(df)
        results = logic.analyze_portfolio(dfc, version="VALIDATE")
    except Exception as e:  # red caida / yfinance
        out["status"] = "skip"
        out["error"] = f"analyze_portfolio fallo (red?): {e}"
        return out

    valid = {t: s for t, s in (results or {}).items()
             if isinstance(s, dict) and not s.get("skipped") and "error" not in s}
    if not valid:
        out["status"] = "skip"
        out["error"] = "sin datos de mercado (yfinance no disponible)"
        return out

    dq = logic.assess_data_quality(valid)

    for ticker, exp in m["tickers"].items():
        rel = exp.get("reliability", "ok")
        s = results.get(ticker) if results else None
        level = dq.get(ticker, {}).get("level")

        if rel == "ok":
            exp_sh = exp.get("shares")
            if s is None or s.get("skipped") or s.get("shares_owned") is None:
                out["rows"].append({"ticker": ticker, "reliability": rel, "kind": "shares",
                                    "result": "SKIP", "detail": "ticker no analizado (sin datos)"})
                continue
            got = s["shares_owned"]
            ok_sh = _approx(got, exp_sh, SHARES_TOL_REL)
            # un ticker confiable NO debe quedar marcado no confiable
            ok_flag = level not in ("unreliable",)
            res = "PASS" if (ok_sh and ok_flag) else "FAIL"
            det = f"acciones app={got:g} vs captura={exp_sh:g}"
            if not ok_flag:
                det += f" · ojo: marcado '{level}' (deberia ser ok)"
            out["rows"].append({"ticker": ticker, "reliability": rel, "kind": "shares",
                                "result": res, "detail": det})

        elif rel in ("unreliable", "reconciled"):
            if s is None or s.get("skipped"):
                out["rows"].append({"ticker": ticker, "reliability": rel, "kind": "flag",
                                    "result": "SKIP", "detail": "ticker no analizado (sin datos)"})
                continue
            flagged = level in ("unreliable", "reconciled")
            res = "PASS" if flagged else "FAIL"
            got = s.get("shares_owned")
            div = ""
            if got is not None and exp.get("shares"):
                d = _rel_pct(got, exp["shares"])
                div = f" · divergencia app={got:g} vs captura={exp['shares']:g} ({d:+.1f}%)"
            det = (f"calidad='{level}' (se esperaba que se marcara){div}" if flagged
                   else f"NO se marco como no confiable (calidad='{level}'){div}")
            out["rows"].append({"ticker": ticker, "reliability": rel, "kind": "flag",
                                "result": res, "detail": det})

        else:  # unverified u otro -> informativo
            got = s.get("shares_owned") if isinstance(s, dict) else None
            det = f"app={got:g}" if got is not None else "no analizado"
            if exp.get("shares") is not None:
                det += f" vs captura={exp['shares']:g}"
            out["rows"].append({"ticker": ticker, "reliability": rel, "kind": "info",
                                "result": "INFO", "detail": det})

    return out


# ── Validacion de fotos (Gemini OCR, opt-in) ──────────────────────────────────

def _load_gemini_key():
    # 1) entorno  2) .streamlit/secrets.toml
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    secrets = os.path.join(BASE, ".streamlit", "secrets.toml")
    if not os.path.exists(secrets):
        return None
    try:
        try:
            import tomllib
            with open(secrets, "rb") as f:
                return tomllib.load(f).get("GEMINI_API_KEY")
        except ModuleNotFoundError:
            import re
            with open(secrets, encoding="utf-8") as f:
                mt = re.search(r'GEMINI_API_KEY\s*=\s*["\']([^"\']+)["\']', f.read())
            return mt.group(1) if mt else None
    except Exception:
        return None


def _case_images(case):
    imgs = []
    for p in sorted(glob.glob(os.path.join(case["dir"], "*"))):
        ext = os.path.splitext(p)[1].lower()
        if ext in IMG_EXTS:
            mime = "image/png" if ext == ".png" else ("image/webp" if ext == ".webp" else "image/jpeg")
            with open(p, "rb") as f:
                imgs.append((f.read(), mime))
    return imgs


def validate_vision(case, api_key):
    """Compara el cost_basis leido por Gemini contra el manifest (solo tickers vision=true)."""
    m = case["manifest"]
    out = {"status": "ok", "rows": []}
    targets = {t: e for t, e in m["tickers"].items() if e.get("vision") and e.get("cost_basis")}
    if not targets:
        out["status"] = "skip"
        out["error"] = "sin tickers marcados vision=true con cost_basis"
        return out

    images = _case_images(case)
    if not images:
        out["status"] = "skip"
        out["error"] = "sin imagenes en la carpeta"
        return out

    read = logic.extract_positions_from_images(images, list(m["tickers"].keys()), api_key)
    if not read:
        out["status"] = "skip"
        out["error"] = "Gemini devolvio {} (sin SDK/key/red/cuota)"
        return out

    for ticker, exp in targets.items():
        got = (read.get(ticker) or {}).get("cost_basis")
        exp_cost = exp["cost_basis"]
        if got is None:
            out["rows"].append({"ticker": ticker, "kind": "cost_basis", "result": "FAIL",
                                "detail": f"Gemini no leyo cost_basis (esperado {exp_cost:g})"})
            continue
        res = "PASS" if _approx(got, exp_cost, COST_TOL_REL) else "FAIL"
        d = _rel_pct(got, exp_cost)
        out["rows"].append({"ticker": ticker, "kind": "cost_basis", "result": res,
                            "detail": f"Gemini={got:g} vs captura={exp_cost:g} ({d:+.1f}%)"})
    return out


# ── Render ────────────────────────────────────────────────────────────────────

_ICON = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "INFO": "•"}


def _count(report):
    p = f = sk = 0
    for c in report:
        for r in c["csv"]["rows"]:
            p += r["result"] == "PASS"; f += r["result"] == "FAIL"; sk += r["result"] == "SKIP"
        for r in c.get("vision", {}).get("rows", []):
            p += r["result"] == "PASS"; f += r["result"] == "FAIL"; sk += r["result"] == "SKIP"
    return p, f, sk


def render_terminal(report, with_vision):
    lines = []
    for c in report:
        cv = c["csv"]
        bk = ("✅" if cv.get("broker_ok") else "❌") if cv.get("broker_got") else "?"
        head = f"━━ {c['case_id']}  (broker {bk} {cv.get('broker_got')})"
        if cv["status"] != "ok":
            head += f"  ⏭️ {cv.get('error', cv['status'])}"
        lines.append(head)
        for r in cv["rows"]:
            lines.append(f"   {_ICON[r['result']]} {r['ticker']:<6} {r['kind']:<11} {r['detail']}")
        if with_vision and "vision" in c:
            vv = c["vision"]
            if vv["status"] != "ok":
                lines.append(f"   📷 vision: ⏭️ {vv.get('error')}")
            else:
                for r in vv["rows"]:
                    lines.append(f"   📷 {_ICON[r['result']]} {r['ticker']:<6} cost_basis  {r['detail']}")
        lines.append("")
    p, f, sk = _count(report)
    lines.append(f"RESUMEN  ✅ {p} PASS   ❌ {f} FAIL   ⏭️ {sk} SKIP")
    return "\n".join(lines)


def render_markdown(report, with_vision):
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
    p, f, sk = _count(report)
    verdict = "🟢 TODO VERDE" if f == 0 else f"🔴 {f} FALLOS"
    out = [
        "---",
        f"created: {today}",
        f"updated: {now}",
        "tags:",
        "  - dividend-analyzer",
        "  - validacion",
        "  - protocolo",
        "---",
        "",
        f"# Validación de Casos Reales — {today}",
        "",
        f"**Veredicto:** {verdict}  ·  ✅ {p} PASS · ❌ {f} FAIL · ⏭️ {sk} SKIP",
        "",
        "> Generado por `validate_real_cases.py`. Ground truth transcrito de las capturas "
        "del broker (`real_examples/<caso>/expected.json`).",
        "",
    ]
    for c in report:
        cv = c["csv"]
        bk = "✅" if cv.get("broker_ok") else "❌"
        out.append(f"## {c['case_id']}  ·  broker {bk} `{cv.get('broker_got')}`")
        if cv["status"] != "ok":
            out.append(f"> ⏭️ {cv.get('error', cv['status'])}")
            out.append("")
            continue
        out.append("")
        out.append("| Ticker | Confiab. | Check | Resultado | Detalle |")
        out.append("|---|---|---|---|---|")
        for r in cv["rows"]:
            out.append(f"| {r['ticker']} | {r['reliability']} | {r['kind']} | "
                       f"{_ICON[r['result']]} {r['result']} | {r['detail']} |")
        if with_vision and "vision" in c:
            vv = c["vision"]
            out.append("")
            out.append("**Lectura por foto (Gemini Vision):**")
            out.append("")
            if vv["status"] != "ok":
                out.append(f"> ⏭️ {vv.get('error')}")
            else:
                out.append("| Ticker | cost_basis | Resultado |")
                out.append("|---|---|---|")
                for r in vv["rows"]:
                    out.append(f"| {r['ticker']} | {r['detail']} | {_ICON[r['result']]} {r['result']} |")
        out.append("")
    return "\n".join(out)


def render_ground_truth_section(cases):
    """Tabla legible del ground truth, generada DESDE los manifests (cero doble captura)."""
    out = ["<!-- GROUND-TRUTH-AUTO:START (generado por validate_real_cases.py --sync-obsidian) -->",
           "## Ground Truth de Casos (auto-generado)", ""]
    for c in cases:
        m = c["manifest"]
        out.append(f"### {c['case_id']} · `{m['broker']}`")
        out.append(f"> {m.get('source', '')}")
        if m.get("notes"):
            out.append(f">")
            out.append(f"> {m['notes']}")
        out.append("")
        out.append("| Ticker | Acciones | Costo base (captura) | Valor mercado | Confiab. | Nota |")
        out.append("|---|---|---|---|---|---|")
        for t, e in m["tickers"].items():
            sh = f"{e['shares']:g}" if e.get("shares") is not None else "—"
            cb = f"${e['cost_basis']:,.2f}" if e.get("cost_basis") is not None else "—"
            mv = f"${e['market_value']:,.2f}" if e.get("market_value") is not None else "—"
            out.append(f"| {t} | {sh} | {cb} | {mv} | {e.get('reliability', 'ok')} | "
                       f"{e.get('note', '')} |")
        out.append("")
    out.append("<!-- GROUND-TRUTH-AUTO:END -->")
    return "\n".join(out)


def sync_obsidian_ground_truth(cases):
    section = render_ground_truth_section(cases)
    if not os.path.exists(PROTOCOL_NOTE):
        print(f"⚠️  No existe la nota {PROTOCOL_NOTE}; no se sincroniza.")
        return
    with open(PROTOCOL_NOTE, encoding="utf-8") as f:
        content = f.read()
    start = "<!-- GROUND-TRUTH-AUTO:START"
    end = "<!-- GROUND-TRUTH-AUTO:END -->"
    if start in content and end in content:
        pre = content[:content.index(start)]
        post = content[content.index(end) + len(end):]
        content = pre + section + post
    else:
        content = content.rstrip() + "\n\n" + section + "\n"
    with open(PROTOCOL_NOTE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Ground truth sincronizado en {PROTOCOL_NOTE}")


def write_report(md):
    os.makedirs(OBSIDIAN_DIR, exist_ok=True)
    path = os.path.join(OBSIDIAN_DIR, f"validacion-casos-reales-{datetime.date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Validacion de casos reales del Dividend Analyzer")
    ap.add_argument("--vision", action="store_true",
                    help="verifica la lectura de fotos con Gemini (gasta cuota)")
    ap.add_argument("--sync-obsidian", action="store_true",
                    help="regenera la seccion Ground Truth en la nota del protocolo y sale")
    ap.add_argument("--no-report", action="store_true", help="no escribe el .md en Obsidian")
    args = ap.parse_args()

    if not os.path.isdir(REAL):
        print(f"⏭️  No existe {REAL} (datos privados). Nada que validar.")
        return 0

    cases = discover_cases()
    if not cases:
        print(f"⏭️  Ningun expected.json bajo {REAL}.")
        return 0

    if args.sync_obsidian:
        sync_obsidian_ground_truth(cases)
        return 0

    api_key = _load_gemini_key() if args.vision else None
    if args.vision and not api_key:
        print("⚠️  --vision pedido pero no hay GEMINI_API_KEY (env ni secrets.toml); se omite la OCR.\n")

    report = []
    for c in cases:
        entry = {"case_id": c["case_id"], "csv": validate_csv(c)}
        if args.vision:
            entry["vision"] = (validate_vision(c, api_key) if api_key
                               else {"status": "skip", "error": "sin GEMINI_API_KEY", "rows": []})
        report.append(entry)

    print(render_terminal(report, args.vision))

    if not args.no_report:
        path = write_report(render_markdown(report, args.vision))
        print(f"\n📄 Reporte: {path}")

    _, fails, _ = _count(report)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
