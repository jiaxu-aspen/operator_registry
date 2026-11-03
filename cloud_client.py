"""HTTPS registry transport shared verbatim with ATP and SW Load.

Desktop credentials are Windows-user-bound DPAPI ciphertext on disk. Network
errors never fall back to a local card list. No request is automatically retried:
an upload timeout may mean publication succeeded, so retrieve before retrying.
"""
import base64
import ctypes
from ctypes import wintypes
import json
import re
import ssl
from pathlib import Path
from urllib import request, error, parse


class CloudError(ValueError):
    """An operator-readable error that deliberately excludes credentials."""


def protect_token(value, decrypt=False):
    """Use Windows DPAPI with UI disabled; only the same Windows user can read."""
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value, validate=True) if decrypt else value.encode('utf-8')
    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise CloudError('Cannot unlock cloud credentials for this Windows user. Configure them again.')
    try:
        result = ctypes.string_at(target.data, target.size)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:
        kernel.LocalFree(target.data)


def validate_url(url):
    """Accept an HTTPS origin only, never embedded credentials or redirect URLs."""
    parts = parse.urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ('', '/')):
        raise CloudError('Enter the HTTPS Worker address without a path or credentials.')
    return url.rstrip('/')


def save_config(path, url, token):
    """Replace configuration atomically after validating and encrypting the token."""
    url = validate_url(url.strip())
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}\.[A-Za-z0-9_-]{43,128}', token.strip()):
        raise CloudError('Enter a provisioned registry client token (client ID plus secret).')
    data = {'url': url, 'token_dpapi': protect_token(token.strip()), 'mode': 'cloud'}
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(path)


def validate_records(records):
    """Validate snapshots before changing SQLite; reject duplicate or broken cards."""
    if not isinstance(records, list) or len(records) > 1000:
        raise CloudError('Invalid cloud registry record count.')
    seen = set(); result = []
    for row in records:
        if (not isinstance(row, dict) or not isinstance(row.get('uid'), str)
                or not re.fullmatch(r'(?:[0-9A-F]{2}){1,256}', row['uid'])
                or row['uid'] in seen or not isinstance(row.get('name'), str)
                or not 1 <= len(row['name'].strip()) <= 100
                or not isinstance(row.get('initials'), str)
                or not re.fullmatch(r'[A-Z]{1,10}', row['initials'])
                or type(row.get('active')) is not int or row['active'] not in (0, 1)):
            raise CloudError('Invalid or duplicate operator in cloud registry.')
        seen.add(row['uid'])
        result.append({k: row[k] for k in ('uid', 'name', 'initials', 'active')})
    return sorted(result, key=lambda r: r['uid'])


class NoRedirect(request.HTTPRedirectHandler):
    """Prevent a redirected endpoint from receiving our Authorization header."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CloudError('Registry redirect rejected. Check the configured address.')


class CloudClient:
    def __init__(self, path):
        """Load private station configuration; malformed files fail closed."""
        try:
            cfg = json.loads(Path(path).read_text(encoding='utf-8'))
            if cfg.get('mode') != 'cloud':
                raise CloudError('Invalid registry cloud mode.')
            self.url = validate_url(cfg['url'])
            self.token = protect_token(cfg['token_dpapi'], decrypt=True)
        except CloudError:
            raise
        except Exception as exc:
            raise CloudError('Cloud registry configuration is missing or invalid.') from exc

    def call(self, method, path, body=None):
        """Bound network waits and response size, and surface only safe error text."""
        data = None if body is None else json.dumps(body).encode('utf-8')
        req = request.Request(self.url + path, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
            # Identify this client explicitly; Cloudflare's edge can reject the
            # generic Python-urllib agent before our authenticated API runs.
            'User-Agent': 'OperatorRegistry/1.0', 'Accept': 'application/json',
            'Cache-Control': 'no-cache'})
        opener = request.build_opener(NoRedirect(), request.HTTPSHandler(context=ssl.create_default_context()))
        try:
            with opener.open(req, timeout=5) as response:
                raw = response.read(512001)
                if len(raw) > 512000:
                    raise CloudError('Cloud registry response is too large.')
                return json.loads(raw)
        except error.HTTPError as exc:
            messages = {401: 'Cloud credentials rejected. Reconfigure this station.',
                        403: 'Card disabled or this credential lacks permission.',
                        404: 'Card not registered or registry endpoint not found.',
                        409: 'Cloud registry changed. Download latest before uploading.',
                        400: 'Cloud rejected the upload. Check records; disable cards instead of removing them.'}
            raise CloudError(messages.get(exc.code, 'Cloud registry unavailable. New runs are blocked.')) from exc
        except CloudError:
            raise
        except Exception as exc:
            raise CloudError('Cloud registry could not be checked. Check the connection. '
                             'If uploading, download latest before retrying; the upload may have succeeded.') from exc

    def download(self):
        """Return only a complete, validated versioned snapshot."""
        result = self.call('GET', '/v1/registry')
        if not isinstance(result, dict) or type(result.get('version')) is not int or result['version'] < 0:
            raise CloudError('Invalid cloud registry version.')
        result['records'] = validate_records(result.get('records'))
        return result

    def upload(self, records, base_version):
        """Publish against the last retrieved version; stale edits cannot overwrite."""
        records = validate_records(records)
        result = self.call('PUT', '/v1/registry', {'records': records, 'base_version': base_version})
        if not isinstance(result, dict) or type(result.get('version')) is not int or result['version'] != base_version + 1:
            raise CloudError('Upload result could not be confirmed. Download latest before retrying.')
        return result

    def check(self, uid):
        """Fresh card lookup, including immutable report evidence of the revision."""
        result = self.call('POST', '/v1/check', {'uid': uid})
        try:
            row = validate_records([result['record']])[0]
            if (row['uid'] != uid or row['active'] != 1 or type(result['version']) is not int
                    or result['version'] < 1 or not isinstance(result['checked_utc'], str)):
                raise ValueError()
            return {'operator_name': row['name'], 'tester_initials': row['initials'],
                    'operator_card_uid': uid, 'operator_registry_version': result['version'],
                    'operator_registry_checked_utc': result['checked_utc'], 'operator_registry_source': 'cloud'}
        except (KeyError, TypeError, ValueError) as exc:
            raise CloudError('Cloud returned an invalid or inactive operator record.') from exc
