"""Backend de almacenamiento para casos de estudio capturados (golden harness).

Dos backends, seleccionados en runtime:
  - Local: si CAPTURE_LOCAL_DIR (env) o st.secrets['capture']['local_dir'] está definido.
            Útil para staging/dev (en Streamlit Cloud el disco es efímero).
  - GCS:   si hay credenciales en st.secrets['gcs'] (bucket + service_account).

Si no hay backend configurado o falta la librería, queda DESACTIVADO: is_enabled()
devuelve False y upload_case() es un no-op. La app NUNCA debe romperse por esto.

Privacidad: solo se suben bundles ya anonimizados por logic.build_capture_bundle
(números/enums/texto genérico). Nunca imágenes, IP ni geo. Ver PRIVACY.md.
"""
import os
import io
import json

CAPTURE_PREFIX = 'captured'
_FILES = ('transactions_min.csv', 'ground_truth.json', 'quality.json',
          'gemini_raw.json', 'meta.json')


def _secrets():
    try:
        import streamlit as st
        return st.secrets
    except Exception:
        return {}


def _local_dir():
    d = os.getenv('CAPTURE_LOCAL_DIR')
    if d:
        return d
    try:
        return _secrets().get('capture', {}).get('local_dir')
    except Exception:
        return None


def _gcs_conf():
    try:
        g = _secrets().get('gcs')
        if g and g.get('bucket') and g.get('service_account'):
            return {'bucket': g['bucket'],
                    'prefix': g.get('prefix', ''),
                    'service_account': dict(g['service_account'])}
    except Exception:
        pass
    return None


def backend() -> str:
    if _local_dir():
        return 'local'
    if _gcs_conf():
        try:
            import google.cloud.storage  # noqa: F401
            return 'gcs'
        except Exception:
            return 'none'
    return 'none'


def is_enabled() -> bool:
    return backend() != 'none'


def _bundle_files(bundle: dict) -> dict:
    return {
        'transactions_min.csv': bundle.get('transactions_min_csv', ''),
        'ground_truth.json': json.dumps(bundle.get('ground_truth', {}), ensure_ascii=False, indent=2),
        'quality.json': json.dumps(bundle.get('quality', {}), ensure_ascii=False, indent=2),
        'gemini_raw.json': json.dumps(bundle.get('gemini_raw', {}), ensure_ascii=False, indent=2),
        'meta.json': json.dumps(bundle.get('meta', {}), ensure_ascii=False, indent=2),
    }


def _gcs_bucket():
    from google.cloud import storage
    conf = _gcs_conf()
    client = storage.Client.from_service_account_info(conf['service_account'])
    return client.bucket(conf['bucket']), conf['prefix']


def upload_case(bundle: dict) -> str:
    """Sube el bundle anónimo. Devuelve case_id si tuvo éxito, None si no.

    Pensado para llamarse dentro de try/except en el caller: si falla, devuelve None
    o lanza, pero nunca debe interrumpir el análisis del usuario.
    """
    if not bundle:
        return None
    case_id = bundle.get('case_id') or (bundle.get('meta') or {}).get('case_id')
    broker = bundle.get('broker', 'generic')
    files = _bundle_files(bundle)
    be = backend()

    if be == 'local':
        base = os.path.join(_local_dir(), CAPTURE_PREFIX, broker, case_id)
        os.makedirs(base, exist_ok=True)
        for name, content in files.items():
            with open(os.path.join(base, name), 'w', encoding='utf-8') as f:
                f.write(content)
        return case_id

    if be == 'gcs':
        bucket, prefix = _gcs_bucket()
        root = '/'.join(p for p in (prefix, CAPTURE_PREFIX, broker, case_id) if p)
        for name, content in files.items():
            ctype = 'text/csv' if name.endswith('.csv') else 'application/json'
            bucket.blob(f'{root}/{name}').upload_from_string(content, content_type=ctype)
        return case_id

    return None


# ── Lectura (para promote_case.py) ───────────────────────────────────────────

def list_cases() -> list:
    """Lista los case_id disponibles como dicts {case_id, broker, backend}."""
    be = backend()
    out = []
    if be == 'local':
        root = os.path.join(_local_dir(), CAPTURE_PREFIX)
        if not os.path.isdir(root):
            return out
        for broker in sorted(os.listdir(root)):
            bdir = os.path.join(root, broker)
            if not os.path.isdir(bdir):
                continue
            for cid in sorted(os.listdir(bdir)):
                if os.path.isdir(os.path.join(bdir, cid)):
                    out.append({'case_id': cid, 'broker': broker, 'backend': 'local'})
    elif be == 'gcs':
        bucket, prefix = _gcs_bucket()
        root = '/'.join(p for p in (prefix, CAPTURE_PREFIX) if p)
        seen = set()
        for blob in bucket.list_blobs(prefix=root + '/'):
            parts = blob.name[len(root) + 1:].split('/')
            if len(parts) >= 2:
                key = (parts[0], parts[1])
                if key not in seen:
                    seen.add(key)
                    out.append({'case_id': parts[1], 'broker': parts[0], 'backend': 'gcs'})
    return out


def fetch_case(broker: str, case_id: str) -> dict:
    """Descarga los archivos de un caso. Devuelve {filename: content_str}."""
    be = backend()
    files = {}
    if be == 'local':
        base = os.path.join(_local_dir(), CAPTURE_PREFIX, broker, case_id)
        for name in _FILES:
            p = os.path.join(base, name)
            if os.path.exists(p):
                with open(p, encoding='utf-8') as f:
                    files[name] = f.read()
    elif be == 'gcs':
        bucket, prefix = _gcs_bucket()
        root = '/'.join(p for p in (prefix, CAPTURE_PREFIX, broker, case_id) if p)
        for name in _FILES:
            blob = bucket.blob(f'{root}/{name}')
            if blob.exists():
                files[name] = blob.download_as_text()
    return files


def delete_case(broker: str, case_id: str) -> bool:
    """Borra un caso (cumplimiento: borrado por case_id a pedido)."""
    be = backend()
    if be == 'local':
        import shutil
        base = os.path.join(_local_dir(), CAPTURE_PREFIX, broker, case_id)
        if os.path.isdir(base):
            shutil.rmtree(base)
            return True
    elif be == 'gcs':
        bucket, prefix = _gcs_bucket()
        root = '/'.join(p for p in (prefix, CAPTURE_PREFIX, broker, case_id) if p)
        deleted = False
        for blob in bucket.list_blobs(prefix=root + '/'):
            blob.delete()
            deleted = True
        return deleted
    return False
