"""Backend de almacenamiento para casos de estudio capturados (golden harness).

Tres backends, seleccionados en runtime (orden: local → b2 → gcs → none):
  - Local: si CAPTURE_LOCAL_DIR (env) o st.secrets['capture']['local_dir'] está definido.
            Útil para staging/dev (en Streamlit Cloud el disco es efímero).
  - B2:    si hay credenciales en st.secrets['b2'] (bucket + endpoint + key_id +
            application_key) o en las variables CAPTURE_B2_* (bucket, endpoint,
            key_id, app_key, prefix opcional). Bucket privado de Backblaze B2 vía
            su API compatible con S3 (boto3).
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


def _b2_conf():
    """Configuración de Backblaze B2. Orden: st.secrets['b2'] → env CAPTURE_B2_*.

    Obligatorios: bucket, endpoint, key_id, application_key. Opcional: prefix.
    Si falta cualquiera de los cuatro obligatorios → None.
    """
    try:
        b = _secrets().get('b2')
        if b and b.get('bucket') and b.get('endpoint') and b.get('key_id') and b.get('application_key'):
            return {'bucket': b['bucket'],
                    'endpoint': b['endpoint'],
                    'key_id': b['key_id'],
                    'application_key': b['application_key'],
                    'prefix': b.get('prefix', '')}
    except Exception:
        pass
    bucket = os.getenv('CAPTURE_B2_BUCKET')
    endpoint = os.getenv('CAPTURE_B2_ENDPOINT')
    key_id = os.getenv('CAPTURE_B2_KEY_ID')
    app_key = os.getenv('CAPTURE_B2_APP_KEY')
    if bucket and endpoint and key_id and app_key:
        return {'bucket': bucket,
                'endpoint': endpoint,
                'key_id': key_id,
                'application_key': app_key,
                'prefix': os.getenv('CAPTURE_B2_PREFIX', '')}
    return None


def _b2_region(endpoint: str) -> str:
    """La región es el segmento entre 's3.' y '.backblazeb2.com' del endpoint."""
    host = endpoint.split('://', 1)[-1].split('/', 1)[0]
    return host.removeprefix('s3.').removesuffix('.backblazeb2.com')


def _b2_client():
    import boto3
    from botocore.config import Config
    c = _b2_conf()
    return boto3.client(
        "s3", endpoint_url=c["endpoint"], region_name=_b2_region(c["endpoint"]),
        aws_access_key_id=c["key_id"], aws_secret_access_key=c["application_key"],
        config=Config(request_checksum_calculation="when_required",
                      response_checksum_validation="when_required"))


def backend() -> str:
    if _local_dir():
        return 'local'
    if _b2_conf():
        try:
            import boto3  # noqa: F401
            return 'b2'
        except Exception:
            pass
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

    if be == 'b2':
        client = _b2_client()
        conf = _b2_conf()
        root = '/'.join(p for p in (conf['prefix'], CAPTURE_PREFIX, broker, case_id) if p)
        for name, content in files.items():
            ctype = 'text/csv' if name.endswith('.csv') else 'application/json'
            # Solo put_object: la clave de producción es de SOLO ESCRITURA —
            # cualquier lectura, listado o head_object fallaría allí.
            client.put_object(Bucket=conf['bucket'], Key=f'{root}/{name}',
                              Body=content.encode('utf-8'), ContentType=ctype)
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
    elif be == 'b2':
        client = _b2_client()
        conf = _b2_conf()
        root = '/'.join(p for p in (conf['prefix'], CAPTURE_PREFIX) if p)
        seen = set()
        token = None
        while True:
            kwargs = {'Bucket': conf['bucket'], 'Prefix': root + '/'}
            if token:
                kwargs['ContinuationToken'] = token
            resp = client.list_objects_v2(**kwargs)
            for obj in resp.get('Contents', []):
                parts = obj['Key'][len(root) + 1:].split('/')
                if len(parts) >= 2:
                    key = (parts[0], parts[1])
                    if key not in seen:
                        seen.add(key)
                        out.append({'case_id': parts[1], 'broker': parts[0], 'backend': 'b2'})
            if not resp.get('IsTruncated'):
                break
            token = resp.get('NextContinuationToken')
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
    elif be == 'b2':
        client = _b2_client()
        conf = _b2_conf()
        from botocore.exceptions import ClientError
        root = '/'.join(p for p in (conf['prefix'], CAPTURE_PREFIX, broker, case_id) if p)
        for name in _FILES:
            try:
                resp = client.get_object(Bucket=conf['bucket'], Key=f'{root}/{name}')
                files[name] = resp['Body'].read().decode('utf-8')
            except ClientError as e:
                code = e.response.get('Error', {}).get('Code', '')
                status = e.response.get('ResponseMetadata', {}).get('HTTPStatusCode')
                if code == 'NoSuchKey' or status == 404:
                    continue
                raise
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
    elif be == 'b2':
        # Borrado REAL: B2 versiona los objetos — un delete_object sin VersionId
        # solo añade un delete marker y el dato sigue ahí. Hay que listar TODAS
        # las versiones y marcadores del caso y borrarlos uno por uno.
        client = _b2_client()
        conf = _b2_conf()
        root = '/'.join(p for p in (conf['prefix'], CAPTURE_PREFIX, broker, case_id) if p)
        deleted = False
        token = None
        while True:
            kwargs = {'Bucket': conf['bucket'], 'Prefix': root + '/'}
            if token:
                kwargs['KeyMarker'] = token[0]
                kwargs['VersionIdMarker'] = token[1]
            resp = client.list_object_versions(**kwargs)
            for entrada in resp.get('Versions', []) + resp.get('DeleteMarkers', []):
                client.delete_object(Bucket=conf['bucket'], Key=entrada['Key'],
                                     VersionId=entrada['VersionId'])
                deleted = True
            if not resp.get('IsTruncated'):
                break
            token = (resp.get('NextKeyMarker'), resp.get('NextVersionIdMarker'))
        return deleted
    elif be == 'gcs':
        bucket, prefix = _gcs_bucket()
        root = '/'.join(p for p in (prefix, CAPTURE_PREFIX, broker, case_id) if p)
        deleted = False
        for blob in bucket.list_blobs(prefix=root + '/'):
            blob.delete()
            deleted = True
        return deleted
    return False
