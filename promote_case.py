#!/usr/bin/env python3
"""Promueve casos capturados (bucket/local) al golden harness — humano en el loop.

Captura automática (en la app) + promoción MANUAL (este script). Solo lo corres TÚ,
localmente. Revisa cada caso y, si lo apruebas, lo escribe como fixture normalizado en
real_examples/captured/ y registra su ground truth en captured_cases.py, para que
test_real_examples.py lo valide en cada corrida.

Uso:
  python promote_case.py --list
  python promote_case.py --show <broker> <case_id>
  python promote_case.py --promote <broker> <case_id>
  python promote_case.py --promote-all
  python promote_case.py --delete <broker> <case_id>
"""
import os
import json
import argparse
import pprint

import storage

BASE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.join(BASE, "real_examples")
CAPTURED_PY = os.path.join(BASE, "captured_cases.py")


def _load_captured() -> dict:
    if not os.path.exists(CAPTURED_PY):
        return {}
    ns = {}
    with open(CAPTURED_PY, encoding="utf-8") as f:
        exec(f.read(), ns)
    return dict(ns.get("CAPTURED_CASES", {}))


def _write_captured(cases: dict):
    body = "# Generado por promote_case.py — fixtures normalizados PII-free (no versionar).\n"
    body += "CAPTURED_CASES = " + pprint.pformat(cases, width=100, sort_dicts=True) + "\n"
    with open(CAPTURED_PY, "w", encoding="utf-8") as f:
        f.write(body)


def _parse(files: dict):
    meta = json.loads(files.get("meta.json", "{}"))
    gt = json.loads(files.get("ground_truth.json", "{}"))
    q = json.loads(files.get("quality.json", "{}"))
    return meta, gt, q


def show(broker: str, case_id: str):
    files = storage.fetch_case(broker, case_id)
    if not files:
        print(f"  (no encontrado: {broker}/{case_id})")
        return None
    meta, gt, q = _parse(files)
    print(f"\n== {broker}/{case_id} ==")
    print(f"  broker={meta.get('broker')} filas={meta.get('n_rows')} capturado={meta.get('captured_at')}")
    print(f"  tickers={meta.get('tickers')}")
    print(f"  calidad={ {t: v.get('level') for t, v in q.items()} }")
    print(f"  ground_truth={gt}")
    return files


def promote(broker: str, case_id: str) -> bool:
    files = show(broker, case_id)
    if not files:
        return False
    _, gt, q = _parse(files)
    # Solo tickers 'ok' con shares > 0 entran al ground truth de shares del harness.
    shares = {t: v.get("shares") for t, v in gt.items()
              if (q.get(t) or {}).get("level") == "ok" and v.get("shares")}
    unreliable = {t for t, v in q.items() if v.get("level") == "unreliable"}
    if not shares:
        print("  ! sin tickers 'ok' con shares — no se promueve (caso no sólido).")
        return False

    dest_dir = os.path.join(REAL, "captured", broker, case_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "transactions_min.csv"), "w", encoding="utf-8") as f:
        f.write(files.get("transactions_min.csv", ""))

    cases = _load_captured()
    cases[f"cap_{case_id}"] = {
        "glob": f"captured/{broker}/{case_id}/transactions_min.csv",
        "normalized": True,
        "broker": broker,
        "shares": shares,
        "unreliable": unreliable,
    }
    _write_captured(cases)
    print(f"  OK promovido: {len(shares)} ticker(s) ok, {len(unreliable)} unreliable. "
          f"Valida con: pytest test_real_examples.py -k cap_{case_id}")
    return True


def main():
    ap = argparse.ArgumentParser(description="Promotor de casos capturados al golden harness.")
    ap.add_argument("--list", action="store_true", help="lista casos capturados disponibles")
    ap.add_argument("--show", nargs=2, metavar=("BROKER", "CASE_ID"))
    ap.add_argument("--promote", nargs=2, metavar=("BROKER", "CASE_ID"))
    ap.add_argument("--promote-all", action="store_true")
    ap.add_argument("--delete", nargs=2, metavar=("BROKER", "CASE_ID"))
    args = ap.parse_args()

    if not storage.is_enabled():
        print("Storage desactivado. Define CAPTURE_LOCAL_DIR o configura st.secrets['gcs'].")
        return

    if args.delete:
        print("borrado" if storage.delete_case(*args.delete) else "no encontrado")
        return
    if args.show:
        show(*args.show)
        return
    if args.promote:
        promote(*args.promote)
        return
    if args.promote_all:
        for c in storage.list_cases():
            promote(c["broker"], c["case_id"])
        return

    cases = storage.list_cases()
    if not cases:
        print("Sin casos capturados.")
        return
    for c in cases:
        print(f"  {c['broker']}/{c['case_id']}  ({c['backend']})")
    print(f"\nTotal: {len(cases)}. Usa --show / --promote / --promote-all.")


if __name__ == "__main__":
    main()
