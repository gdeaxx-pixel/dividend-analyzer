#!/usr/bin/env python3
"""Referencia congelada de `logic.analyze_portfolio` para partir su cuerpo (F4, tercera fase).

Los cortes extraen bloques internos a funciones privadas: cambian firmas, meten un `return` y
desempaquetan en el llamador. «Cero tests editados» no basta como prueba de eso. La prueba es
esta: la salida COMPLETA de `analyze_portfolio` sobre todas las entradas conocidas, congelada
antes del corte y comparada con tolerancia cero después.

    python tools/referencia_analyze.py grabar     # con red, UNA vez, sobre el SHA base
    python tools/referencia_analyze.py congelar   # sin red, desde el cassette -> referencia
    python tools/referencia_analyze.py comparar   # sin red; sale con 1 si hay >= 1 diferencia
    python tools/referencia_analyze.py cobertura 1074-1077 1080-1087   # líneas de logic.py

Las corridas: cada caso de `real_examples/` y cada fixture en modo `validate` (sin argumentos,
como `validate_real_cases.py`) y en modo `demo` (con `ib_cost_basis_map` y `position_overrides`
derivados del manifiesto, como `demo_mode._load_bundle`), más `fixtures/ramas_analyze` en modo
demo. Sus manifiestos no se llaman `expected.json` a propósito: llevan acciones que difieren del
CSV para forzar la reconciliación, y un runner que las tomara por ground truth fallaría.

Al reproducir, `fetch_market_data`, `_descargar_benchmark` y `yf.Ticker` leen del cassette; la
red y el reloj quedan bloqueados. `analyze_portfolio` está llena de `try/except Exception`, así
que una clave ausente o un intento de red se anotan en una lista y se comprueban al final: un
error tragado no puede congelar un hueco.

Todo vive FUERA del repo (`~/.local/share/dividend-analyzer/referencia_analyze/<sha>/`): la
salida de los casos reales contiene posiciones privadas.
"""
import argparse
import contextlib
import fnmatch
import glob
import io
import json
import os
import socket
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import logic  # noqa: E402

RAIZ = os.environ.get(
    "DIVIDEND_REFERENCIA_DIR",
    os.path.join(os.path.expanduser("~"), ".local", "share", "dividend-analyzer",
                 "referencia_analyze"))
REAL = os.environ.get("DIVIDEND_REAL_EXAMPLES_DIR", os.path.join(BASE, "real_examples"))
FIXTURES = os.path.join(BASE, "fixtures")
FIXTURES_MANIFIESTO = ("ib_synth_1", "schwab_synth_1", "schwab_synth_2")
FIXTURES_SIN_MANIFIESTO = ("schwab_tda_synth",)
FIXTURE_RAMAS = "ramas_analyze"


class FakeFile:
    def __init__(self, content, name):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


def _ci_glob(case_dir, pattern, exclude=()):
    out = []
    for name in sorted(os.listdir(case_dir)):
        if name.endswith(".json") or name in exclude:
            continue
        if fnmatch.fnmatch(name.lower(), pattern.lower()):
            out.append(os.path.join(case_dir, name))
    return out


# ── Entradas ──────────────────────────────────────────────────────────────────────────

def _cargar(case_dir, manifest):
    income = _ci_glob(case_dir, manifest["income_glob"]) if manifest.get("income_glob") else []
    exclude = tuple(os.path.basename(p) for p in income)
    csvs = _ci_glob(case_dir, manifest.get("csv_glob", "*.csv"), exclude=exclude)
    if not csvs:
        raise RuntimeError(f"sin CSV en {case_dir}")
    with open(csvs[0], "rb") as f:
        df, _ = logic.load_and_detect_csv(FakeFile(f.read(), os.path.basename(csvs[0])))
    return logic.normalize_csv(df)


def _args_demo(df_clean, manifest):
    """Mismo derivado que `demo_mode._load_bundle`."""
    tickers = df_clean["Ticker"].dropna().unique().tolist()
    mmap = logic.classify_tickers(tickers)
    pos = [t for t, m in mmap.items() if m in ("mode_a", "mode_b")]
    ib_map, overrides = {}, {}
    for t, exp in (manifest.get("tickers") or {}).items():
        if t not in pos:
            continue
        co = float(exp.get("cost_basis") or 0)
        sh = float(exp.get("shares") or 0)
        if co > 0:
            ib_map[t] = str(co)
        if co > 0 or sh > 0:
            overrides[t] = {"cost_basis": co or None, "shares": sh or None}
    return {"ib_cost_basis_map": ib_map or None, "position_overrides": overrides or None}


def entradas():
    """[(nombre_corrida, df_clean, kwargs)] en orden fijo."""
    casos = []
    for path in sorted(glob.glob(os.path.join(REAL, "**", "expected.json"), recursive=True)):
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        casos.append((m.get("case_id") or os.path.relpath(os.path.dirname(path), REAL),
                      os.path.dirname(path), m, ("validate", "demo")))
    for nombre in FIXTURES_MANIFIESTO:
        d = os.path.join(FIXTURES, nombre)
        with open(os.path.join(d, "expected.json"), encoding="utf-8") as f:
            casos.append((nombre, d, json.load(f), ("validate", "demo")))
    for nombre in FIXTURES_SIN_MANIFIESTO:
        casos.append((nombre, os.path.join(FIXTURES, nombre),
                      {"csv_glob": "synthetic_transactions.csv"}, ("validate",)))
    d = os.path.join(FIXTURES, FIXTURE_RAMAS)
    with open(os.path.join(d, "overrides.json"), encoding="utf-8") as f:
        casos.append((FIXTURE_RAMAS, d, json.load(f), ("demo",)))

    out = []
    for nombre, d, m, modos in casos:
        df = _cargar(d, m)
        for modo in modos:
            if modo == "validate":
                out.append((f"{nombre}|validate", df, {"version": "VALIDATE"}))
            else:
                out.append((f"{nombre}|demo", df, dict(version="2.0", **_args_demo(df, m))))
    return out


# ── Cassette ──────────────────────────────────────────────────────────────────────────

def _clave_bench(df):
    try:
        primera = pd.to_datetime(df["Date"], errors="coerce").min()
    except (KeyError, TypeError, ValueError):
        return ("bench", "sin-Date")
    return ("bench", str(primera))


def _k(clave):
    return json.dumps(list(clave))


class Cassette:
    def __init__(self, carpeta):
        self.carpeta = carpeta
        self.datos = {}
        self.meta = {}

    def guardar(self):
        os.makedirs(self.carpeta, exist_ok=True)
        indice = []
        for n, (k, v) in enumerate(sorted(self.datos.items())):
            entrada = {"clave": json.loads(k)}
            if k.startswith('["first_trade"'):
                entrada["valor"] = _a_json_simple(v)
            else:
                df, err = v if isinstance(v, tuple) else (v, None)
                entrada["err"] = err
                entrada["tupla"] = isinstance(v, tuple)
                entrada["archivo"] = _guardar_frame(df, os.path.join(self.carpeta, f"{n:04d}"))
            indice.append(entrada)
        with open(os.path.join(self.carpeta, "indice.json"), "w", encoding="utf-8") as f:
            json.dump({"meta": self.meta, "llamadas": indice}, f, indent=1, ensure_ascii=False)

    @classmethod
    def cargar(cls, carpeta):
        c = cls(carpeta)
        with open(os.path.join(carpeta, "indice.json"), encoding="utf-8") as f:
            data = json.load(f)
        c.meta = data["meta"]
        for e in data["llamadas"]:
            k = _k(e["clave"])
            if "valor" in e:
                c.datos[k] = _de_json_simple(e["valor"])
            else:
                df = _cargar_frame(os.path.join(carpeta, e["archivo"]))
                c.datos[k] = (df, e["err"]) if e["tupla"] else df
        return c


def _guardar_frame(df, base):
    """Parquet si el frame vuelve idéntico; pickle si no (lo genera esta herramienta)."""
    try:
        ruta = base + ".parquet"
        df.to_parquet(ruta)
        vuelta = pd.read_parquet(ruta)
        if _canon(vuelta) == _canon(df):
            return os.path.basename(ruta)
        os.remove(ruta)
    except Exception:
        pass
    ruta = base + ".pkl"
    df.to_pickle(ruta)
    return os.path.basename(ruta)


def _cargar_frame(ruta):
    return pd.read_parquet(ruta) if ruta.endswith(".parquet") else pd.read_pickle(ruta)


def _a_json_simple(v):
    if v is None:
        return None
    if isinstance(v, pd.Timestamp):
        return {"ts": v.isoformat()}
    if isinstance(v, (int, float, str, np.integer, np.floating)):
        return {"n": v.item() if hasattr(v, "item") else v}
    raise TypeError(f"first_trade_date de tipo no previsto: {type(v)}")


def _de_json_simple(v):
    if v is None:
        return None
    if "ts" in v:
        return pd.Timestamp(v["ts"])
    return v["n"]


# ── Parches ───────────────────────────────────────────────────────────────────────────

class _FastInfo:
    def __init__(self, valor):
        self.first_trade_date = valor


@contextlib.contextmanager
def _parche(obj, nombre, valor):
    viejo = getattr(obj, nombre)
    setattr(obj, nombre, valor)
    try:
        yield
    finally:
        setattr(obj, nombre, viejo)


@contextlib.contextmanager
def entorno(cassette, grabando, errores, hoy):
    orig_fetch = logic.fetch_market_data
    orig_bench = logic._descargar_benchmark
    orig_ticker = logic.yf.Ticker

    def servir(k):
        v = cassette.datos[k]
        if isinstance(v, tuple):
            return (v[0].copy(deep=True), v[1])
        if isinstance(v, pd.DataFrame):
            return v.copy(deep=True)
        return v

    def fetch(ticker, start_date):
        k = _k(("fetch", str(ticker), str(pd.Timestamp(start_date))))
        if k not in cassette.datos:
            if not grabando:
                errores.append(f"falta en el cassette: {k}")
                raise KeyError(k)
            df, err = orig_fetch(ticker, start_date)
            cassette.datos[k] = (df.copy(deep=True), err)
        return servir(k)

    def bench(df, *a, **kw):
        if a or kw:
            errores.append(f"_descargar_benchmark con argumentos no previstos: {a} {kw}")
        k = _k(_clave_bench(df))
        if k not in cassette.datos:
            if not grabando:
                errores.append(f"falta en el cassette: {k}")
                raise KeyError(k)
            cassette.datos[k] = orig_bench(df, *a, **kw).copy(deep=True)
        return servir(k)

    class Ticker:
        def __init__(self, ticker, *a, **kw):
            self._t = str(ticker)

        @property
        def fast_info(self):
            k = _k(("first_trade", self._t))
            if k not in cassette.datos:
                if not grabando:
                    errores.append(f"falta en el cassette: {k}")
                    raise KeyError(k)
                fi = orig_ticker(self._t).fast_info
                cassette.datos[k] = getattr(fi, "first_trade_date", None)
            return _FastInfo(servir(k))

        def __getattr__(self, nombre):
            errores.append(f"yf.Ticker({self._t}).{nombre}: uso no previsto")
            raise AttributeError(nombre)

    def red(*a, **kw):
        errores.append(f"intento de red: {a[:2]!r}")
        raise ConnectionError("red bloqueada por referencia_analyze")

    @classmethod
    def _hoy(cls, tz=None):
        return hoy

    with contextlib.ExitStack() as pila:
        pila.enter_context(_parche(logic, "fetch_market_data", fetch))
        pila.enter_context(_parche(logic, "_descargar_benchmark", bench))
        pila.enter_context(_parche(logic.yf, "Ticker", Ticker))
        pila.enter_context(_parche(pd.Timestamp, "today", _hoy))
        if not grabando:
            pila.enter_context(_parche(socket.socket, "connect", red))
            pila.enter_context(_parche(socket.socket, "connect_ex", red))
            pila.enter_context(_parche(logic.yf, "download", red))
            pila.enter_context(_parche(logic.crequests.Session, "request", red))
            try:
                import requests
                pila.enter_context(_parche(requests.Session, "request", red))
            except ImportError:
                pass
        yield


# ── Forma canónica ────────────────────────────────────────────────────────────────────

def _canon(x):
    if x is None:
        return None
    if isinstance(x, pd.DataFrame):
        return ["DF", [_canon(c) for c in x.columns], [str(d) for d in x.dtypes],
                _canon(x.index.name), [_canon(i) for i in x.index],
                [[_canon(v) for v in fila] for fila in x.itertuples(index=False, name=None)]]
    if isinstance(x, pd.Series):
        return ["S", str(x.dtype), _canon(x.name), [_canon(i) for i in x.index],
                [_canon(v) for v in x.tolist()]]
    if isinstance(x, pd.Index):
        return ["I", str(x.dtype), [_canon(i) for i in x]]
    if isinstance(x, dict):
        pares = [[_clave_texto(k), _canon(v)] for k, v in x.items()]
        return ["D", sorted(pares, key=lambda p: p[0])]
    if isinstance(x, (list, tuple)):
        return ["L" if isinstance(x, list) else "T", [_canon(v) for v in x]]
    if isinstance(x, np.ndarray):
        return ["A", str(x.dtype), [_canon(v) for v in x.tolist()]]
    if isinstance(x, (bool, np.bool_)):
        return ["b", bool(x)]
    if x is pd.NaT:
        return ["NaT"]
    if isinstance(x, (float, np.floating)):
        f = float(x)
        return ["f", type(x).__name__, "nan" if f != f else f.hex()]
    if isinstance(x, (int, np.integer)):
        return ["i", type(x).__name__, int(x)]
    if isinstance(x, str):
        return x
    if isinstance(x, (pd.Timestamp, pd.Timedelta)):
        return ["ts", type(x).__name__, str(x)]
    if hasattr(x, "isoformat"):
        return ["ts", type(x).__name__, x.isoformat()]
    return ["r", type(x).__name__, repr(x)]


def _clave_texto(k):
    return k if isinstance(k, str) else f"{type(k).__name__}:{k!r}"


def _canon_resultado(res):
    if not isinstance(res, dict):
        return {"__resultado__": {"__valor__": _canon(res)}}
    out = {}
    for t, stats in res.items():
        if isinstance(stats, dict):
            out[_clave_texto(t)] = {_clave_texto(k): _canon(v) for k, v in stats.items()}
        else:
            out[_clave_texto(t)] = {"__valor__": _canon(stats)}
    return out


# ── Corridas ──────────────────────────────────────────────────────────────────────────

def correr(cassette, grabando, hoy, traza=None):
    errores = []
    salida = {}
    llamadas_antes = len(cassette.datos)
    with entorno(cassette, grabando, errores, hoy):
        for nombre, df, kwargs in entradas():
            logic.analyze_portfolio.clear()
            if traza is not None:
                sys.settrace(traza)
            try:
                res = logic.analyze_portfolio(df.copy(), **kwargs)
                salida[nombre] = _canon_resultado(res)
            except Exception as e:
                salida[nombre] = {"__excepcion__": {"__valor__": f"{type(e).__name__}: {e}"}}
            finally:
                if traza is not None:
                    sys.settrace(None)
    return salida, errores, len(cassette.datos) - llamadas_antes


def _sha():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BASE,
                          capture_output=True, text=True).stdout.strip()


def _logic_limpio():
    r = subprocess.run(["git", "status", "--porcelain", "--", "logic.py"], cwd=BASE,
                       capture_output=True, text=True)
    return r.stdout.strip() == ""


def _carpeta(base=None):
    if base:
        return os.path.join(RAIZ, base)
    cands = [d for d in glob.glob(os.path.join(RAIZ, "*"))
             if os.path.isfile(os.path.join(d, "cassette", "indice.json"))]
    if not cands:
        return None
    return max(cands, key=lambda d: os.path.getmtime(os.path.join(d, "cassette", "indice.json")))


def _resumen(salida):
    tickers = sum(1 for r in salida.values() for t, s in r.items()
                  if "__valor__" not in s and not _es_skip(s))
    claves = {len(s) for r in salida.values() for s in r.values()
              if "__valor__" not in s and not _es_skip(s)}
    return f"{len(salida)} corridas, {tickers} tickers válidos, claves por ticker: {sorted(claves)}"


def _es_skip(stats):
    return "skipped" in stats or "error" in stats


def _guardar_json(ruta, obj):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def _leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


# ── Comparación ───────────────────────────────────────────────────────────────────────

def _primera_diferencia(a, b, ruta=""):
    if a == b:
        return None
    if isinstance(a, list) and isinstance(b, list) and a and b and a[0] == b[0] \
            and isinstance(a[0], str) and a[0] in ("DF", "S", "I", "D", "L", "T", "A"):
        if a[0] == "D":
            da, db = dict(map(tuple, a[1])), dict(map(tuple, b[1]))
            for k in sorted(set(da) | set(db)):
                if k not in da or k not in db:
                    return f"{ruta}[{k!r}] {'falta' if k not in db else 'sobra'}"
                d = _primera_diferencia(da[k], db[k], f"{ruta}[{k!r}]")
                if d:
                    return d
        partes = {"DF": ("columnas", "dtypes", "nombre_indice", "indice", "filas"),
                  "S": ("dtype", "nombre", "indice", "valores"),
                  "I": ("dtype", "valores"), "L": ("items",), "T": ("items",),
                  "A": ("dtype", "valores")}.get(a[0], ())
        for nombre, x, y in zip(partes, a[1:], b[1:]):
            if x == y:
                continue
            if isinstance(x, list) and isinstance(y, list) and nombre in ("filas", "indice",
                                                                         "valores", "items"):
                if len(x) != len(y):
                    return f"{ruta}.{nombre} longitud {len(x)} != {len(y)}"
                for i, (u, v) in enumerate(zip(x, y)):
                    d = _primera_diferencia(u, v, f"{ruta}.{nombre}[{i}]")
                    if d:
                        return d
            return f"{ruta}.{nombre}: {_corto(x)} != {_corto(y)}"
    return f"{ruta}: {_corto(a)} != {_corto(b)}"


def _corto(v):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 120 else s[:117] + "..."


def diferencias(ref, nueva):
    """Una diferencia = un campo `corrida|ticker.clave` distinto (o que falta/sobra)."""
    out = []
    for corrida in sorted(set(ref) | set(nueva)):
        if corrida not in ref or corrida not in nueva:
            out.append((f"{corrida}", "corrida " + ("nueva" if corrida not in ref else "ausente")))
            continue
        r, n = ref[corrida], nueva[corrida]
        for t in sorted(set(r) | set(n)):
            if t not in r or t not in n:
                out.append((f"{corrida}|{t}", "ticker " + ("nuevo" if t not in r else "ausente")))
                continue
            for k in sorted(set(r[t]) | set(n[t])):
                ruta = f"{corrida}|{t}.{k}"
                if k not in r[t] or k not in n[t]:
                    out.append((ruta, "clave " + ("nueva" if k not in r[t] else "ausente")))
                    continue
                d = _primera_diferencia(r[t][k], n[t][k])
                if d is not None:
                    out.append((ruta, d))
    return out


def _imprimir_diferencias(difs, limite):
    for ruta, d in difs[:limite]:
        print(f"  {ruta}  {d}")
    if len(difs) > limite:
        print(f"  ... y {len(difs) - limite} más")
    por_clave = {}
    for ruta, d in difs:
        clave = ruta.split(".", 1)[1] if "." in ruta else d
        por_clave[clave] = por_clave.get(clave, 0) + 1
    if difs:
        print("  por clave: " + ", ".join(f"{k}={v}" for k, v in
                                           sorted(por_clave.items(), key=lambda p: -p[1])))


# ── Subcomandos ───────────────────────────────────────────────────────────────────────

def cmd_grabar(args):
    if not _logic_limpio() and not args.forzar:
        sys.exit("logic.py tiene cambios: se graba sobre el SHA base, intacto (--forzar para ignorar)")
    sha = _sha()
    carpeta = os.path.join(RAIZ, sha)
    if os.path.exists(os.path.join(carpeta, "cassette", "indice.json")) and not args.forzar:
        sys.exit(f"ya hay un cassette en {carpeta}: no se regraba (--forzar para pisarlo)")
    hoy = pd.Timestamp.today()
    cas = Cassette(os.path.join(carpeta, "cassette"))
    t0 = time.time()
    salida, errores, n = correr(cas, grabando=True, hoy=hoy)
    dt = time.time() - t0
    if errores:
        sys.exit("errores al grabar:\n  " + "\n  ".join(errores))
    cas.meta = {"sha": sha, "hoy": hoy.isoformat(), "segundos_en_vivo": round(dt, 1),
                "llamadas": n}
    cas.guardar()
    _guardar_json(os.path.join(carpeta, "vivo.json"), salida)
    tipos = {}
    for k in cas.datos:
        tipos[json.loads(k)[0]] = tipos.get(json.loads(k)[0], 0) + 1
    print(f"grabado en {carpeta}")
    print(f"  {_resumen(salida)}")
    print(f"  {n} llamadas externas distintas: {tipos}; {dt:.1f} s en vivo")


def _reproducir(carpeta, traza=None):
    cas = Cassette.cargar(os.path.join(carpeta, "cassette"))
    hoy = pd.Timestamp(cas.meta["hoy"])
    t0 = time.time()
    salida, errores, n = correr(cas, grabando=False, hoy=hoy, traza=traza)
    if n:
        errores.append(f"el cassette creció en {n} entradas durante la reproducción")
    return salida, errores, time.time() - t0


def cmd_congelar(args):
    carpeta = _carpeta(args.base)
    if carpeta is None:
        sys.exit(f"no hay cassette en {RAIZ}: correr `grabar` primero")
    salida, errores, dt = _reproducir(carpeta)
    if errores:
        sys.exit("NO se congela; errores en la reproducción:\n  " + "\n  ".join(errores))
    _guardar_json(os.path.join(carpeta, "referencia.json"), salida)
    with open(os.path.join(carpeta, "referencia.meta.json"), "w", encoding="utf-8") as f:
        json.dump({"sha_congelado": _sha(), "logic_limpio": _logic_limpio(),
                   "congelado": pd.Timestamp.now().isoformat()}, f, indent=1)
    print(f"referencia congelada en {carpeta} (sha {_sha()}, logic.py "
          f"{'intacto' if _logic_limpio() else 'MODIFICADO'}); {dt:.1f} s sin red")
    print(f"  {_resumen(salida)}")
    vivo = os.path.join(carpeta, "vivo.json")
    if os.path.exists(vivo):
        difs = diferencias(_leer_json(vivo), salida)
        print(f"  contra la corrida en vivo de la grabación: {len(difs)} diferencias")
        _imprimir_diferencias(difs, args.limite)


def cmd_comparar(args):
    carpeta = _carpeta(args.base)
    if carpeta is None or not os.path.exists(os.path.join(carpeta, "referencia.json")):
        sys.exit(f"no hay referencia en {RAIZ}: correr `grabar` y `congelar` primero")
    meta = _leer_json(os.path.join(carpeta, "referencia.meta.json"))
    salida, errores, dt = _reproducir(carpeta)
    difs = diferencias(_leer_json(os.path.join(carpeta, "referencia.json")), salida)
    print(f"referencia {carpeta} (congelada sobre {meta['sha_congelado']}); HEAD {_sha()}, "
          f"logic.py {'intacto' if _logic_limpio() else 'MODIFICADO'}")
    print(f"  {_resumen(salida)}; {dt:.1f} s sin red")
    for e in errores:
        print(f"  ERROR {e}")
    print(f"{len(difs)} diferencias")
    _imprimir_diferencias(difs, args.limite)
    sys.exit(1 if difs or errores else 0)


def cmd_cobertura(args):
    carpeta = _carpeta(args.base)
    if carpeta is None:
        sys.exit(f"no hay cassette en {RAIZ}")
    rangos = []
    for r in args.lineas:
        a, _, b = r.partition("-")
        rangos.append((int(a), int(b or a)))
    objetivo = {n for a, b in rangos for n in range(a, b + 1)}
    archivo = os.path.abspath(logic.__file__)
    vistas = set()

    def local(frame, evento, arg):
        if evento == "line" and frame.f_lineno in objetivo:
            vistas.add(frame.f_lineno)
        return local

    def traza(frame, evento, arg):
        if frame.f_code.co_filename == archivo:
            return local
        return None

    _, errores, _ = _reproducir(carpeta, traza=traza)
    for e in errores:
        print(f"  ERROR {e}")
    for a, b in rangos:
        lineas = range(a, b + 1)
        hechas = [n for n in lineas if n in vistas]
        print(f"  {a}-{b}: {len(hechas)} de {len(lineas)} líneas ejecutadas"
              + ("" if len(hechas) == len(lineas) else
                 f" (sin ejecutar: {[n for n in lineas if n not in vistas]})"))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grabar")
    g.add_argument("--forzar", action="store_true")
    for nombre in ("congelar", "comparar"):
        s = sub.add_parser(nombre)
        s.add_argument("--base", help="SHA de la grabación (por defecto, el cassette más reciente)")
        s.add_argument("--limite", type=int, default=400, help="diferencias a listar")
    c = sub.add_parser("cobertura")
    c.add_argument("lineas", nargs="+", help="rangos de logic.py, p. ej. 1074-1077")
    c.add_argument("--base")
    args = p.parse_args()
    {"grabar": cmd_grabar, "congelar": cmd_congelar, "comparar": cmd_comparar,
     "cobertura": cmd_cobertura}[args.cmd](args)


if __name__ == "__main__":
    main()
