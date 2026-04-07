"""
XUI Panel Client for VPN key management.
Uses py3xui library to interact with XUI panel.
"""
import logging
import json
from urllib.parse import quote, urlencode, urlparse

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import py3xui
from py3xui.client.client import Client

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

api = None
api_host = None


def candidate_hosts() -> list[str]:
    """Return possible 3X-UI base URLs."""
    base = settings.XUI_HOST.rstrip("/")
    if base.endswith("/login"):
        base = base[:-6].rstrip("/")

    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else base
    hosts = [base, origin]

    if not parsed.path or parsed.path == "":
        hosts.append(f"{origin}/panel")
        hosts.append(f"{origin}/xui")
    else:
        hosts.append(f"{origin}/panel")
        hosts.append(f"{origin}/xui")

    unique_hosts = []
    for host in hosts:
        if host not in unique_hosts:
            unique_hosts.append(host)
    return unique_hosts


_DEFAULT_TIMEOUT = 15  # seconds


def _patch_timeout(api_obj: py3xui.Api) -> None:
    """Patch py3xui Api sub-apis to pass a default timeout on every request."""
    import functools

    for sub in (api_obj.client, api_obj.inbound, api_obj.database, api_obj.server):
        original = sub._request_with_retry

        @functools.wraps(original)
        def _with_timeout(method, url, headers, _orig=original, **kwargs):
            kwargs.setdefault("timeout", _DEFAULT_TIMEOUT)
            return _orig(method, url, headers, **kwargs)

        sub._request_with_retry = _with_timeout


def build_xui_api(host: str) -> py3xui.Api:
    xui = py3xui.Api(
        host=host,
        username=settings.XUI_USERNAME,
        password=settings.XUI_PASSWORD,
        use_tls_verify=False,
    )
    _patch_timeout(xui)
    return xui


def get_xui_api() -> py3xui.Api:
    """Get or create XUI API client."""
    global api, api_host
    if api is None:
        api_host = candidate_hosts()[0]
        api = build_xui_api(api_host)
    return api


def ensure_login() -> py3xui.Api:
    """Ensure authenticated session exists before any XUI operation."""
    global api, api_host

    last_error = None
    for host in candidate_hosts():
        try:
            if api is None or api_host != host:
                api_host = host
                api = build_xui_api(host)
            api.login()
            return api
        except Exception as exc:
            last_error = exc
            logger.warning("XUI login failed for host %s: %s", host, exc)

    raise RuntimeError(
        "Failed to login to 3X-UI using hosts %s. Last error: %s"
        % (candidate_hosts(), last_error)
    )


def login() -> bool:
    """Login to XUI panel."""
    try:
        ensure_login()
        logger.info('XUI Panel connected successfully')
        return True
    except Exception as exc:
        logger.exception('XUI Panel connection failed: %s', exc)
        return False


def get_inbounds() -> list:
    """Get all inbounds from XUI panel."""
    result = get_inbounds_result()
    return result["inbounds"]


def get_inbounds_result() -> dict:
    """Get all inbounds from XUI panel with detailed status."""
    try:
        api_client = ensure_login()
        inbounds = api_client.inbound.get_list()
        inbounds = inbounds or []
        if not inbounds:
            return {
                "success": False,
                "inbounds": [],
                "error": "No inbounds found in 3X-UI panel",
            }
        return {
            "success": True,
            "inbounds": inbounds,
            "error": None,
        }
    except Exception as exc:
        logger.exception('Error getting inbounds: %s', exc)
        return {
            "success": False,
            "inbounds": [],
            "error": str(exc),
        }


def get_inbound_by_id(inbound_id: int):
    """Get specific inbound by ID."""
    try:
        api_client = ensure_login()
        return api_client.inbound.get_by_id(inbound_id)
    except Exception as exc:
        logger.exception('Error getting inbound %s: %s', inbound_id, exc)
        return None


def get_clients(inbound_id: int) -> list:
    """Get all clients from specific inbound."""
    try:
        api_client = ensure_login()
        inbound = api_client.inbound.get_by_id(inbound_id)
        if inbound and hasattr(inbound, 'settings') and inbound.settings:
            clients = inbound.settings.get('clients', [])
            return clients or []
        return []
    except Exception as exc:
        logger.exception('Error getting clients for inbound %s: %s', inbound_id, exc)
        return []


def add_client(
    inbound_id: int,
    email: str,
    uuid: str = None,
    limit_ip: int = 0,
    total_gb: int = 0,
    expire_time: int = 0,
    enable: bool = True,
    flow: str = '',
) -> dict:
    """Add a new client to an inbound."""
    try:
        import uuid as uuid_module

        api_client = ensure_login()
        inbound = api_client.inbound.get_by_id(inbound_id)

        if not inbound:
            return {'error': f'Inbound {inbound_id} not found'}

        client_uuid = uuid or str(uuid_module.uuid4())
        client = Client(
            id=client_uuid,
            email=email,
            enable=enable,
            inboundId=inbound_id,
            limitIp=limit_ip,
            totalGB=total_gb * 1024 * 1024 * 1024 if total_gb > 0 else 0,
            expiryTime=expire_time,
            flow=flow or "",
            tgId="",
            subId="",
            reset=0,
        )

        api_client.client.add(inbound_id, [client])
        created_client = api_client.client.get_by_email(email) or client
        link = generate_client_link(inbound, created_client.model_dump(by_alias=True, exclude_defaults=False))
        return {
            'success': True,
            'email': email,
            'uuid': str(created_client.uuid or created_client.id or client_uuid),
            'link': link,
            'subscription_url': f"{api_host or settings.XUI_HOST}/subscription/{created_client.sub_id}",
        }
    except Exception as exc:
        logger.exception('Error adding client to inbound %s: %s', inbound_id, exc)
        return {'error': str(exc)}


def delete_client(inbound_id: int, client_id: str) -> bool:
    """Delete a client from an inbound."""
    try:
        api_client = ensure_login()
        api_client.client.delete(inbound_id, client_id)
        return True
    except Exception as exc:
        logger.exception('Error deleting client %s: %s', client_id, exc)
        return False


def get_client_by_email(email: str):
    """Get a client by email across all inbounds."""
    try:
        api_client = ensure_login()
        return api_client.client.get_by_email(email)
    except Exception as exc:
        logger.exception("Error getting client by email %s: %s", email, exc)
        return None


def delete_client_by_email(email: str) -> bool:
    """Delete a client by email, automatically resolving inbound and UUID."""
    try:
        api_client = ensure_login()
        client = api_client.client.get_by_email(email)
        if not client:
            return True

        inbound_id = getattr(client, "inbound_id", None)
        client_uuid = getattr(client, "uuid", None) or getattr(client, "id", None)
        if inbound_id is None or not client_uuid:
            logger.warning(
                "Cannot delete client by email %s because inbound_id or uuid is missing",
                email,
            )
            return False

        api_client.client.delete(int(inbound_id), str(client_uuid))
        return True
    except Exception as exc:
        logger.exception("Error deleting client by email %s: %s", email, exc)
        return False


def update_client(
    inbound_id: int,
    client_id: str,
    email: str = None,
    limit_ip: int = None,
    total_gb: int = None,
    expire_time: int = None,
    enable: bool = None,
) -> bool:
    """Update client settings."""
    try:
        api_client = ensure_login()
        inbound = api_client.inbound.get_by_id(inbound_id)
        if not inbound:
            return False

        clients = inbound.settings.get('clients', [])
        client = next((c for c in clients if c.get('id') == client_id), None)
        if not client:
            return False

        if email is not None:
            client['email'] = email
        if limit_ip is not None:
            client['limitIp'] = limit_ip
        if total_gb is not None:
            client['totalGB'] = total_gb * 1024 * 1024 * 1024
        if expire_time is not None:
            client['expiryTime'] = expire_time
        if enable is not None:
            client['enable'] = enable

        api_client.client.update(
            client_id,
            Client.model_validate({**client, "inboundId": inbound_id}),
        )
        return True
    except Exception as exc:
        logger.exception('Error updating client %s: %s', client_id, exc)
        return False


def get_client_traffic(inbound_id: int, client_id: str) -> dict:
    """Get client traffic statistics."""
    try:
        api_client = ensure_login()
        client = api_client.client.get_by_email(client_id)
        if not client:
            return {'error': 'Client not found'}

        return {
            'email': client.email,
            'upload': client.up,
            'download': client.down,
            'total': client.up + client.down,
            'total_gb': client.total_gb,
            'expiry_time': client.expiry_time,
            'enable': client.enable,
        }
    except Exception as exc:
        logger.exception('Error getting traffic for client %s: %s', client_id, exc)
        return {'error': str(exc)}


def generate_client_link(inbound, client: dict) -> str:
    """Generate VPN connection link for client."""
    try:
        def as_dict(value):
            if value is None:
                return {}
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return {}
            if hasattr(value, "model_dump"):
                return value.model_dump()
            if hasattr(value, "__dict__"):
                return {k: v for k, v in vars(value).items() if not k.startswith("_")}
            return {}

        def first_non_empty(*values):
            for value in values:
                if value not in (None, "", 0, "0.0.0.0", "::"):
                    return value
            return ""

        protocol = inbound.protocol
        client_email = client.get('email', 'VPN')
        remark_prefix = settings.VPN_LINK_REMARK or 'KRUTOY_VPN'
        remark = f"{remark_prefix}-{client_email}"

        if protocol == 'vless':
            uuid = client.get('uuid') or client.get('id', '')
            port = settings.VPN_PUBLIC_PORT or inbound.port
            host = settings.VPN_PUBLIC_HOST or urlparse(settings.XUI_HOST).hostname or '127.0.0.1'
            stream = as_dict(getattr(inbound, 'stream_settings', None))
            reality = as_dict(stream.get('reality_settings'))
            network = settings.VPN_NETWORK or first_non_empty(stream.get('network'), 'tcp')
            security = settings.VPN_SECURITY or first_non_empty(stream.get('security'), 'none')

            params = {
                'type': network,
                'encryption': 'none',
            }

            if network == 'grpc':
                params['serviceName'] = settings.VPN_SERVICE_NAME
                params['authority'] = settings.VPN_AUTHORITY

            if security != 'none':
                params['security'] = security

            if security == 'reality':
                server_names = reality.get('serverNames', [])
                params['pbk'] = settings.VPN_PBK or reality.get('publicKey', '')
                params['fp'] = settings.VPN_FP or reality.get('fingerprint', 'chrome')
                params['sni'] = settings.VPN_SNI or first_non_empty(
                    server_names[0] if isinstance(server_names, list) and server_names else '',
                    reality.get('serverName', ''),
                )
                params['sid'] = settings.VPN_SID or reality.get('shortId', '')
                params['spx'] = settings.VPN_SPX or reality.get('spiderX', '/')

            query = urlencode(params, doseq=True, quote_via=quote)
            link = f'vless://{uuid}@{host}:{port}?{query}'
            if remark:
                link += f'#{remark}'
            return link

        if protocol == 'vmess':
            uuid = client.get('id', '')
            port = inbound.port
            host = inbound.listen or '0.0.0.0'

            import base64
            import json

            config = {
                'v': '2',
                'ps': remark,
                'add': host,
                'port': str(port),
                'id': uuid,
                'aid': '0',
                'net': 'tcp',
                'type': 'none',
                'host': '',
                'path': '',
                'tls': '',
            }
            return f"vmess://{base64.b64encode(json.dumps(config).encode()).decode()}"

        if protocol == 'trojan':
            password = client.get('password', '')
            port = inbound.port
            host = inbound.listen or '0.0.0.0'
            return f'trojan://{password}@{host}:{port}#{remark}'

        if protocol == 'shadowsocks':
            password = client.get('password', '')
            port = inbound.port
            host = inbound.listen or '0.0.0.0'
            method = inbound.settings.get('method', 'none')

            import base64

            userinfo = base64.b64encode(f'{method}:{password}'.encode()).decode()
            return f'ss://{userinfo}@{host}:{port}#{remark}'

        return ''
    except Exception as exc:
        logger.exception('Error generating client link: %s', exc)
        return ''


def get_server_stats() -> dict:
    """Get overall server statistics."""
    try:
        api_client = ensure_login()
        inbounds = api_client.inbound.get_list() or []

        total_clients = 0
        active_clients = 0
        total_upload = 0
        total_download = 0

        for inbound in inbounds:
            clients = inbound.settings.get('clients', []) if hasattr(inbound, 'settings') and inbound.settings else []
            total_clients += len(clients)
            active_clients += sum(1 for c in clients if c.get('enable', True))
            total_upload += sum(c.get('up', 0) for c in clients)
            total_download += sum(c.get('down', 0) for c in clients)

        return {
            'inbounds': len(inbounds),
            'total_clients': total_clients,
            'active_clients': active_clients,
            'total_upload': total_upload,
            'total_download': total_download,
            'total_traffic': total_upload + total_download,
        }
    except Exception as exc:
        logger.exception('Error getting server stats: %s', exc)
        return {'error': str(exc)}


def reset_client_traffic(inbound_id: int, client_id: str) -> bool:
    """Reset client traffic statistics."""
    try:
        api_client = ensure_login()
        api_client.client.reset_stats(inbound_id, client_id)
        return True
    except Exception as exc:
        logger.exception('Error resetting client traffic %s: %s', client_id, exc)
        return False
