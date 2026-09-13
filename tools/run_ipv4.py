"""SOLO LOCAL. Fuerza IPv4 antes de arrancar Streamlit.

En la red de Daniel, IPv6 hacia Auth0 no responde y `requests` lo intenta
primero: el login se cuelga sin timeout y parece roto. No es código de
producción — no se despliega, no se importa desde `app.py`.
"""
import socket

_getaddrinfo_original = socket.getaddrinfo


def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _getaddrinfo_original(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _getaddrinfo_ipv4

import streamlit.web.cli as stcli

if __name__ == "__main__":
    stcli.main(["run", "app.py", "--server.port", "8765"])
