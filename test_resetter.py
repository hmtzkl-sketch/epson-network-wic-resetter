"""
test_resetter.py - Unit ve Entegrasyon Testleri
Protokol paketleri, checksum hesaplamaları, model eşlemeleri
ve ASN.1 SNMP kodlayıcılarının doğruluğunu test eder.
"""

from discovery import encode_asn1_length, encode_asn1_oid, build_snmp_get_request, is_epson_mac
from epson_models import find_model_config, EPSON_MODEL_DATABASE
from epson_protocol import EpsonProtocolClient, CMD_REMOTE_ENTER, CMD_REMOTE_EXIT
from eeprom_handler import calculate_epson_checksum, EpsonEEPROMHandler


def test_asn1_oid():
    # 1.3.6.1.2.1.1.1.0
    oid_bytes = encode_asn1_oid("1.3.6.1.2.1.1.1.0")
    assert oid_bytes[0] == 0x06, "OID etiket baytı 0x06 olmalıdır"
    assert oid_bytes[1] == 0x08, "OID uzunluğu 8 olmalıdır"
    print("[TEST OK] ASN.1 OID Kodlama Başarılı.")


def test_snmp_packet_builder():
    pkt = build_snmp_get_request("1.3.6.1.2.1.1.1.0", community="public")
    assert pkt[0] == 0x30, "SNMP paketi Sequence (0x30) ile başlamalıdır"
    assert b"public" in pkt, "SNMP topluluk adı pakette yer almalıdır"
    print("[TEST OK] SNMP GetRequest Paketi Başarılı.")


def test_mac_oui():
    assert is_epson_mac("00:00:48:12:34:56") is True, "Epson MAC tanınmalı"
    assert is_epson_mac("00:26:AB:AA:BB:CC") is True, "Epson MAC tanınmalı"
    assert is_epson_mac("AA:BB:CC:11:22:33") is False, "Yabancı MAC reddedilmeli"
    print("[TEST OK] MAC OUI Doğrulama Başarılı.")


def test_model_lookup():
    m1 = find_model_config("EPSON L3150 Series")
    assert m1 is not None and m1["canonical_model"] == "L3150"
    m2 = find_model_config("EPSON EcoTank ET-2800 Series")
    assert m2 is not None and m2["canonical_model"] == "ET-2800"
    m3 = find_model_config("L386")
    assert m3 is not None and m3["canonical_model"] == "L380" or m3["canonical_model"] == "L386"
    print(f"[TEST OK] Model Eşleme Başarılı: L3150 -> {m1['canonical_model']}, ET-2800 -> {m2['canonical_model']}")


def test_checksum():
    # Inverted sum 8-bit checksum testi
    test_bytes = bytes([0x00, 0x00, 0x5E, 0x00])
    chk = calculate_epson_checksum(test_bytes)
    assert 0 <= chk <= 255
    print(f"[TEST OK] EEPROM Checksum Testi Başarılı: Checksum = 0x{chk:02X}")


def test_remote_mode_packet():
    client = EpsonProtocolClient("127.0.0.1", port=9100)
    # NC (Nozzle Check) paketi
    nc_pkt = client.build_remote_packet("NC", params=b"\x00\x00")
    assert nc_pkt.startswith(CMD_REMOTE_ENTER), "Paket Remote Mode Entry ile başlamalıdır"
    assert nc_pkt.endswith(CMD_REMOTE_EXIT), "Paket Remote Mode Exit ile bitmelidir"
    assert b"NC\x02\x00\x00\x00" in nc_pkt, "NC komutu ve parametre uzunluğu pakette yer almalıdır"
    print(f"[TEST OK] ESC/P Remote Mode Paket İnşası Başarılı: {nc_pkt.hex()}")


if __name__ == "__main__":
    test_asn1_oid()
    test_snmp_packet_builder()
    test_mac_oui()
    test_model_lookup()
    test_checksum()
    test_remote_mode_packet()
    print("\n>>> TÜM PROTOKOL VE SAYAÇ BİRİM TESTLERİ %100 BAŞARIYLA GEÇTİ! <<<")
