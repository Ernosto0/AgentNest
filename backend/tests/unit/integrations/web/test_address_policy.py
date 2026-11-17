import pytest

from app.integrations.web.address_policy import is_public_address


@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",  # noqa: S104 - explicitly blocked address
        "0.1.2.3",
        "10.1.1.1",
        "100.64.1.1",
        "127.0.0.1",
        "169.254.169.254",
        "169.254.170.2",
        "172.16.0.1",
        "192.0.0.9",
        "192.0.2.1",
        "192.88.99.1",
        "192.168.0.1",
        "198.18.0.1",
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1%eth0",
        "fc00::1",
        "fd00:ec2::254",
        "ff02::1",
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
        "::10.0.0.1",
        "2002:a00:1::",
        "64:ff9b::a00:1",
        "2001::1",
        "2001:db8::1",
        "100::1",
        "fec0::1",
        "2001:10::1",
        "64:ff9b:1::808:808",
        "garbage",
    ],
)
def test_blocked(address):
    assert not is_public_address(address)


@pytest.mark.parametrize(
    "address",
    [
        "93.184.216.34",
        "1.1.1.1",
        "2606:4700:4700::1111",
        "::ffff:8.8.8.8",
        "::8.8.8.8",
        "2002:808:808::",
        "64:ff9b::808:808",
    ],
)
def test_public(address):
    assert is_public_address(address)
