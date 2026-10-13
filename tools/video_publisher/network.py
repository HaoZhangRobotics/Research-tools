"""Reuse an existing HTTP proxy without changing system network settings."""
import os
import re
import subprocess
import sys
from urllib.parse import unquote, urlparse


def proxy_url():
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.environ.get(key)
        if value:
            return value
    if sys.platform != "darwin":
        return None
    try:
        output = subprocess.check_output(["scutil", "--proxy"], text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    def field(name):
        match = re.search(rf"^\s*{name}\s*:\s*(\S+)", output, re.MULTILINE)
        return match.group(1) if match else None
    for prefix in ("HTTPS", "HTTP"):
        host, port = field(prefix + "Proxy"), field(prefix + "Port")
        if field(prefix + "Enable") == "1" and host and port and port.isdigit():
            if ":" in host:
                host = f"[{host}]"
            return f"http://{host}:{port}"
    return None


def browser_proxy():
    value = proxy_url()
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.hostname:
        return None
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    result = {"server": f"{parsed.scheme}://{host}:{parsed.port or 80}"}
    if parsed.username:
        result["username"] = unquote(parsed.username)
        result["password"] = unquote(parsed.password or "")
    return result
