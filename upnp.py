"""UPnP (IGD): descobre o IP WAN do roteador e abre/fecha portas automaticamente.

Só com a biblioteca padrão. Funciona em roteadores com UPnP ligado (a maioria dos de operadora).
Com CGNAT o IP WAN é da faixa 100.64.0.0/10: a porta abre no roteador, mas só clientes da mesma
operadora conseguem chegar até ele.
"""
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SSDP_ADDR = ("239.255.255.250", 1900)
SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2",
            "urn:schemas-upnp-org:service:WANIPConnection:1",
            "urn:schemas-upnp-org:service:WANPPPConnection:1")


class UPnPError(Exception):
    pass


class Gateway:
    def __init__(self, control_url, service, local_ip):
        self.control_url = control_url
        self.service = service
        self.local_ip = local_ip

    def _soap(self, action, args=None, timeout=4):
        args = args or {}
        body = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
        envelope = ('<?xml version="1.0"?>'
                    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                    f'<u:{action} xmlns:u="{self.service}">{body}</u:{action}>'
                    '</s:Body></s:Envelope>').encode()
        req = urllib.request.Request(self.control_url, data=envelope, method="POST", headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{self.service}#{action}"',
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            code = re.search(r"<errorCode>(\d+)</errorCode>", text)
            desc = re.search(r"<errorDescription>([^<]*)</errorDescription>", text)
            raise UPnPError(f"{code.group(1) if code else e.code} {desc.group(1) if desc else ''}".strip())

    def external_ip(self):
        xml = self._soap("GetExternalIPAddress")
        m = re.search(r"<NewExternalIPAddress>([^<]*)</NewExternalIPAddress>", xml)
        return m.group(1).strip() if m and m.group(1).strip() else None

    def add_port(self, port, proto="TCP", description="PS2Online", internal_port=None):
        self._soap("AddPortMapping", {
            "NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": proto,
            "NewInternalPort": internal_port or port, "NewInternalClient": self.local_ip,
            "NewEnabled": 1, "NewPortMappingDescription": description, "NewLeaseDuration": 0,
        })

    def delete_port(self, port, proto="TCP"):
        self._soap("DeletePortMapping", {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": proto})

    def get_port(self, port, proto="TCP"):
        """Retorna (ip_interno, descrição) do mapeamento existente, ou None."""
        try:
            xml = self._soap("GetSpecificPortMappingEntry",
                             {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": proto})
        except UPnPError:
            return None
        ip = re.search(r"<NewInternalClient>([^<]*)</NewInternalClient>", xml)
        desc = re.search(r"<NewPortMappingDescription>([^<]*)</NewPortMappingDescription>", xml)
        return (ip.group(1) if ip else "", desc.group(1) if desc else "")


def _local_ip_towards(host):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, 9))
        return s.getsockname()[0]
    finally:
        s.close()


def discover(timeout=2.5) -> Gateway:
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
           "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n").encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(timeout)
    locations = []
    try:
        sock.sendto(msg, SSDP_ADDR)
        sock.sendto(msg.replace(b"device:InternetGatewayDevice:1", b"ssdp:all"), SSDP_ADDR)
        while True:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                break
            m = re.search(rb"(?im)^location:\s*(\S+)", data)
            if m:
                loc = m.group(1).decode()
                if loc not in locations:
                    locations.append(loc)
    finally:
        sock.close()
    for loc in locations:
        try:
            with urllib.request.urlopen(loc, timeout=3) as r:
                root = ET.fromstring(r.read())
        except Exception:
            continue
        for svc in root.iter():
            if not svc.tag.endswith("service"):
                continue
            fields = {c.tag.split("}")[-1]: (c.text or "").strip() for c in svc}
            if fields.get("serviceType") in SERVICES and fields.get("controlURL"):
                url = urllib.parse.urljoin(loc, fields["controlURL"])
                local_ip = _local_ip_towards(urllib.parse.urlparse(loc).hostname)
                return Gateway(url, fields["serviceType"], local_ip)
    raise UPnPError("nenhum roteador com UPnP encontrado")


def describe_wan(ip: str) -> str:
    a = ipaddress.ip_address(ip)
    if a in ipaddress.ip_network("100.64.0.0/10"):
        return "CGNAT — só funciona para quem é da mesma operadora"
    if a.is_private:
        return "rede privada da operadora/roteador"
    return "IP público"
