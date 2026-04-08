"""
XUI Panel Client for VPN key management.
Uses py3xui library to interact with XUI panel.
"""
import logging
import json
import time
import asyncio
from urllib.parse import quote, urlencode, urlparse
from functools import lru_cache

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import py3xui
from py3xui.client.client import Client

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

api = None
api_host = None

# Кэш для inbounds (TTL 60 секунд)
_inbounds_cache = {"data": None, "timestamp": 0}
_INBOUNDS_CACHE_TTL = 60  # секунд


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


_DEFAULT_TIMEOUT = 30  # seconds
_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds


def _retry_on_timeout(func, *args, **kwargs):
    """Execute function with retry on timeout errors."""
    last_exception = None
    
    for attempt in range(_MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            error_message = str(exc).lower()
            # Проверяем, является ли ошибка таймаутом
            is_timeout = any(keyword in error_message for keyword in [
                'timeout', 'timed out', 'connection timed out', 'connecttimeouterror'
            ])
            
            if is_timeout and attempt < _MAX_RETRIES - 1:
                logger.warning(
                    "Request timed out (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    _RETRY_DELAY,
                    exc,
                )
                time.sleep(_RETRY_DELAY)
                last_exception = exc
            elif not is_timeout:
                # Не таймаут - сразу пробрасываем
                raise
            else:
                # Последняя попытка не удалась
                last_exception = exc
    
    # Все попытки не удались
    logger.error("All %d retries exhausted. Last error: %s", _MAX_RETRIES, last_exception)
    raise last_exception


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


def test_xui_login_direct(host: str) -> bool:
    """Test XUI login using direct HTTP request to API."""
    import requests
    
    # Пробуем разные варианты login endpoint
    login_urls = [
        f"{host}/login",
        f"{host.rstrip('/')}/login",
    ]
    
    for login_url in login_urls:
        try:
            # Пробуем с form data (как делает py3xui)
            response = requests.post(
                login_url,
                data={
                    "username": settings.XUI_USERNAME,
                    "password": settings.XUI_PASSWORD,
                },
                verify=False,
                timeout=10,
            )
            
            if response.status_code == 200:
                try:
                    json_resp = response.json()
                    if json_resp.get("success") or json_resp.get("msg") == "Login successful":
                        logger.info("Direct login successful at %s", host)
                        return True
                except:
                    pass
            
            logger.warning(
                "Direct login attempt at %s failed with status %d, response: %s",
                login_url,
                response.status_code,
                response.text[:200],
            )
        except Exception as exc:
            logger.debug("Direct login at %s failed: %s", login_url, exc)
    
    return False


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
            
            # Пробуем стандартный логин py3xui
            try:
                api.login()
                logger.info("Successfully logged in to XUI at %s", host)
                return api
            except Exception as login_error:
                # Если стандартный логин не сработал, пробуем прямой запрос
                error_msg = str(login_error).lower()
                if "invalid username or password" in error_msg:
                    # Логируем детали для отладки
                    logger.error(
                        "XUI login failed with credentials. "
                        "Host: %s, Username: %s. "
                        "Check if 3X-UI API credentials are correct.",
                        host,
                        settings.XUI_USERNAME,
                    )
                raise
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
    """Get all inbounds from XUI panel with detailed status (cached)."""
    global _inbounds_cache
    
    # Проверяем кэш
    current_time = time.time()
    if _inbounds_cache["data"] is not None and (current_time - _inbounds_cache["timestamp"]) < _INBOUNDS_CACHE_TTL:
        return _inbounds_cache["data"]
    
    try:
        api_client = ensure_login()
        inbounds = api_client.inbound.get_list()
        inbounds = inbounds or []
        if not inbounds:
            result = {
                "success": False,
                "inbounds": [],
                "error": "No inbounds found in 3X-UI panel",
            }
        else:
            result = {
                "success": True,
                "inbounds": inbounds,
                "error": None,
            }
        
        # Сохраняем в кэш
        _inbounds_cache["data"] = result
        _inbounds_cache["timestamp"] = current_time
        
        return result
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
        def _get_inbound():
            api_client = ensure_login()
            return api_client.inbound.get_by_id(inbound_id)
        
        return _retry_on_timeout(_get_inbound)
    except Exception as exc:
        logger.exception('Error getting inbound %s: %s', inbound_id, exc)
        return None


def get_clients(inbound_id: int) -> list:
    """Get all clients from specific inbound."""
    try:
        def _get_clients():
            api_client = ensure_login()
            inbound = api_client.inbound.get_by_id(inbound_id)
            if inbound and hasattr(inbound, 'settings') and inbound.settings:
                clients = inbound.settings.get('clients', [])
                return clients or []
            return []
        
        return _retry_on_timeout(_get_clients)
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
        
        # Логируем для отладки
        logger.info("Created client: email=%s, link_length=%d", email, len(link))
        if 'pbk=' in link:
            pbk_start = link.index('pbk=') + 4
            pbk_end = link.find('&', pbk_start)
            if pbk_end == -1:
                pbk_end = link.find('#', pbk_start)
            pbk_value = link[pbk_start:pbk_end] if pbk_end > pbk_start else link[pbk_start:]
            if not pbk_value:
                logger.warning("Generated link has EMPTY pbk! Link: %s", link[:200])
        
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
        def _delete_client():
            api_client = ensure_login()
            api_client.client.delete(inbound_id, client_id)
            return True
        
        return _retry_on_timeout(_delete_client)
    except Exception as exc:
        logger.exception('Error deleting client %s: %s', client_id, exc)
        return False


def get_client_by_email(email: str):
    """Get a client by email across all inbounds."""
    try:
        def _get_client():
            api_client = ensure_login()
            return api_client.client.get_by_email(email)
        
        return _retry_on_timeout(_get_client)
    except Exception as exc:
        logger.exception("Error getting client by email %s: %s", email, exc)
        return None


def delete_client_by_email(email: str) -> bool:
    """Delete a client by email, automatically resolving inbound and UUID."""
    try:
        def _delete_by_email():
            api_client = ensure_login()
            client = api_client.client.get_by_email(email)
            if not client:
                # Клиент не найден - считаем это успешным удалением
                logger.info("Client with email %s not found in XUI, considering it already deleted", email)
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
        
        return _retry_on_timeout(_delete_by_email)
    except ValueError as exc:
        # Обработка ошибок "Inbound Not Found" и подобных
        error_message = str(exc)
        if "Inbound Not Found" in error_message or "Error getting traffics" in error_message:
            logger.warning(
                "Client with email %s not found in XUI (inbound error), considering it already deleted: %s",
                email,
                error_message,
            )
            return True
        # Другие ошибки ValueError
        logger.exception("ValueError deleting client by email %s: %s", email, exc)
        return False
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
        def _get_traffic():
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
        
        return _retry_on_timeout(_get_traffic)
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
                
                # Пробуем разные варианты ключей (XUI может отдавать по-разному)
                pbk = (settings.VPN_PBK or 
                       reality.get('publicKey', '') or 
                       reality.get('public_key', '') or
                       reality.get('dest', '').split(':')[0] if ':' in reality.get('dest', '') else '')
                
                sid = (settings.VPN_SID or 
                       reality.get('shortId', '') or 
                       reality.get('short_id', ''))
                
                sni = (settings.VPN_SNI or 
                       first_non_empty(
                           server_names[0] if isinstance(server_names, list) and server_names else '',
                           reality.get('serverName', ''),
                           reality.get('server_names', [''])[0] if isinstance(reality.get('server_names', []), list) else '',
                       ))
                
                # Логируем для отладки
                logger.debug("Reality settings: pbk=%s, sid=%s, sni=%s", 
                           pbk[:20] if pbk else 'EMPTY', 
                           sid, 
                           sni)
                
                params['pbk'] = pbk
                params['fp'] = settings.VPN_FP or reality.get('fingerprint', 'chrome')
                params['sni'] = sni
                params['sid'] = sid
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
