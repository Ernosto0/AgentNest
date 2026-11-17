"""Public unicast policy, including IPv4 tunnel and translation forms."""

import ipaddress

_V4 = tuple(
    ipaddress.ip_network(s)
    for s in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
    )
)
_V6 = tuple(
    ipaddress.ip_network(s)
    for s in (
        "::/128",
        "::1/128",
        "fc00::/7",
        "fd00:ec2::254/128",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
        "100::/64",
        "2001::/32",
        "2001:db8::/32",
        "2001:10::/28",
        "64:ff9b:1::/48",
        "::ffff:0:0/96",
    )
)


def is_public_address(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
        elif int(ip) >> 32 == 0 or ip in ipaddress.ip_network("64:ff9b::/96"):
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    blocked = _V4 if isinstance(ip, ipaddress.IPv4Address) else _V6
    return ip.is_global and not ip.is_multicast and not any(ip in net for net in blocked)
