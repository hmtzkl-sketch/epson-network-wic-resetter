"""
discovery.py - Epson Ağ Yazıcısı Keşif Motoru (Network Discovery Engine)
SNMP (UDP 161), mDNS (UDP 5353), ARP OUI Eşleme ve Doğrudan Port Taraması
sayesinde yerel ağdaki Epson EcoTank / L serisi yazıcıları otomatik tespit eder.
"""

import socket
import struct
import subprocess
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable

# Epson Resmi ve Bilinen MAC OUI (Organizationally Unique Identifier) Listesi
EPSON_OUI_PREFIXES = {
    "00:00:48": "SEIKO EPSON CORP.",
    "00:21:54": "SEIKO EPSON CORP.",
    "00:26:AB": "SEIKO EPSON CORP.",
    "44:D9:E7": "SEIKO EPSON CORP.",
    "AC:18:26": "SEIKO EPSON CORP.",
    "F8:D0:27": "SEIKO EPSON CORP.",
    "00:1B:7A": "SEIKO EPSON CORP.",
    "9C:EB:E8": "SEIKO EPSON CORP.",
    "B4:A9:FC": "SEIKO EPSON CORP.",
    "00:24:FE": "SEIKO EPSON CORP.",
    "64:EB:8C": "SEIKO EPSON CORP.",
    "D4:39:1A": "SEIKO EPSON CORP.",
    "E0:D5:5E": "SEIKO EPSON CORP.",
    "A4:EE:57": "SEIKO EPSON CORP.",
    "80:5E:4F": "SEIKO EPSON CORP.",
    "5C:E9:1E": "SEIKO EPSON CORP.",
    "28:18:78": "SEIKO EPSON CORP.",
    "10:5B:AD": "SEIKO EPSON CORP.",
}

# Standart ve Epson Özel SNMP OID Tanımları
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"      # sysDescr.0 (Cihaz model ve firmware tanımı)
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"       # sysName.0 (Yazıcı Hostname)
OID_EPSON_MODEL = "1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1.1"  # Epson Enterprise MIB Model Name


@dataclass
class PrinterDevice:
    """Ağda bulunan Epson yazıcı bilgilerini saklayan veri modeli."""
    ip: str
    port: int = 9100
    mac: str = "Bilinmiyor"
    hostname: str = ""
    model: str = "Bilinmeyen Epson"
    serial: str = "Bilinmiyor"
    firmware: str = "Bilinmiyor"
    sys_descr: str = ""
    discovery_source: str = "Otomatik"
    is_epson: bool = True
    response_time_ms: float = 0.0

    def display_name(self) -> str:
        name = self.model if self.model != "Bilinmeyen Epson" else (self.hostname or "Epson Yazıcı")
        return f"{name} ({self.ip}) [{self.mac}]"


def encode_asn1_length(length: int) -> bytes:
    """ASN.1 BER uzunluk baytlarını kodlar."""
    if length < 128:
        return bytes([length])
    len_bytes = []
    while length > 0:
        len_bytes.insert(0, length & 0xFF)
        length >>= 8
    return bytes([0x80 | len(len_bytes)]) + bytes(len_bytes)


def encode_asn1_oid(oid_str: str) -> bytes:
    """Oktet dizisi formatındaki OID'yi ASN.1 BER baytlarına çevirir."""
    parts = [int(p) for p in oid_str.split('.')]
    if len(parts) < 2:
        return b""
    encoded = bytearray()
    encoded.append(parts[0] * 40 + parts[1])
    for part in parts[2:]:
        sub_bytes = []
        val = part
        while val >= 128:
            sub_bytes.insert(0, (val & 0x7F) | 0x80)
            val >>= 7
        sub_bytes.insert(0, val & 0x7F)
        if len(sub_bytes) > 1:
            for b in sub_bytes[:-1]:
                encoded.append(b | 0x80)
            encoded.append(sub_bytes[-1] & 0x7F)
        else:
            encoded.append(sub_bytes[0])
    return bytes([0x06, len(encoded)]) + bytes(encoded)


def build_snmp_get_request(oid: str, community: str = "public", req_id: int = 1) -> bytes:
    """
    Saf Python ile UDP 161 SNMP v1/v2c GetRequest paketi üretir.
    Harici ağır kütüphanelere bağımlılığı ortadan kaldırır.
    """
    oid_bytes = encode_asn1_oid(oid)
    null_val = b"\x05\x00"
    varbind = b"\x30" + encode_asn1_length(len(oid_bytes) + len(null_val)) + oid_bytes + null_val
    varbind_list = b"\x30" + encode_asn1_length(len(varbind)) + varbind
    
    # Request-ID (int), error-status (0), error-index (0)
    req_id_bytes = b"\x02\x04" + struct.pack(">I", req_id)
    err_stat = b"\x02\x01\x00"
    err_idx = b"\x02\x01\x00"
    
    pdu_payload = req_id_bytes + err_stat + err_idx + varbind_list
    pdu = b"\xA0" + encode_asn1_length(len(pdu_payload)) + pdu_payload
    
    # Version 1 = integer 0 (SNMPv1)
    version = b"\x02\x01\x00"
    comm_bytes = community.encode("ascii")
    community_encoded = b"\x04" + encode_asn1_length(len(comm_bytes)) + comm_bytes
    
    snmp_payload = version + community_encoded + pdu
    return b"\x30" + encode_asn1_length(len(snmp_payload)) + snmp_payload


def parse_snmp_response_string(data: bytes) -> Optional[str]:
    """SNMP GetResponse ASN.1 paketinden dize verisini çıkarır."""
    try:
        # Basit ASN.1 OctetString veya PrintableString arama (0x04)
        idx = 0
        while idx < len(data) - 2:
            if data[idx] == 0x04:  # OctetString
                length = data[idx + 1]
                if length < 128 and idx + 2 + length <= len(data):
                    candidate = data[idx + 2 : idx + 2 + length]
                    # Yazdırılabilir ASCII kontrolü
                    if all(32 <= b <= 126 or b in (10, 13) for b in candidate):
                        text = candidate.decode("ascii", errors="ignore").strip()
                        if len(text) > 2 and ("EPSON" in text.upper() or "PRINTER" in text.upper() or "INK" in text.upper()):
                            return text
                elif length > 128:
                    len_bytes_count = length & 0x7F
                    if idx + 2 + len_bytes_count <= len(data):
                        # Uzun format
                        real_len = int.from_bytes(data[idx+2 : idx+2+len_bytes_count], "big")
                        data_start = idx + 2 + len_bytes_count
                        if data_start + real_len <= len(data):
                            candidate = data[data_start : data_start + real_len]
                            text = candidate.decode("ascii", errors="ignore").strip()
                            if "EPSON" in text.upper():
                                return text
            idx += 1
    except Exception:
        pass
    return None


def get_arp_table() -> Dict[str, str]:
    """
    İşletim sistemi ARP tablosunu sorgulayarak IP -> MAC haritası üretir.
    Windows 'arp -a' çıktısını ayrıştırır.
    """
    arp_map = {}
    try:
        output = subprocess.check_output("arp -a", shell=True, text=True, timeout=2.0)
        lines = output.splitlines()
        for line in lines:
            line = line.strip()
            # Örnek format: 192.168.1.55     00-26-ab-12-34-56     dynamic
            parts = re.split(r'\s+', line)
            if len(parts) >= 2:
                ip_match = re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', parts[0])
                mac_match = re.match(r'^([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})$', parts[1])
                if ip_match and mac_match:
                    ip = parts[0]
                    mac = parts[1].replace("-", ":").upper()
                    arp_map[ip] = mac
    except Exception:
        pass
    return arp_map


def is_epson_mac(mac: str) -> bool:
    """Verilen MAC adresinin ilk 3 baytının Epson OUI listesinde olup olmadığını doğrular."""
    if not mac:
        return False
    mac_upper = mac.upper().replace("-", ":")
    prefix = ":".join(mac_upper.split(":")[:3])
    return prefix in EPSON_OUI_PREFIXES


def get_local_ip_and_subnet() -> tuple[str, str]:
    """Yerel makinenin aktif ağ IP'sini ve C-sınıfı alt ağ önekini tespit eder."""
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # 8.8.8.8'e sanal bağlanarak varsayılan rotadaki yerel IP'yi al
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "192.168.1.1"

    parts = local_ip.split(".")
    subnet_prefix = f"{parts[0]}.{parts[1]}.{parts[2]}"
    return local_ip, subnet_prefix


class NetworkDiscoveryEngine:
    """
    Yerel alt ağda Epson yazıcıları tarayan ana keşif sınıfı.
    SNMP, mDNS, Port 9100 kontrolü ve OUI eşlemeyi eşzamanlı çalıştırır.
    """

    def __init__(self, timeout: float = 3.0):
        self.timeout = timeout
        self.found_printers: Dict[str, PrinterDevice] = {}
        self._lock = threading.Lock()

    def probe_snmp(self, ip: str) -> Optional[PrinterDevice]:
        """
        Belirtilen IP'ye UDP 161 SNMP ve IONET BDC sorguları gönderir.
        Seri numarasını ve model adını doğrudan yazıcı anakartından okur.
        """
        model_name = "Bilinmeyen Epson"
        sys_descr = ""
        serial_no = "Bilinmiyor"
        mac_addr = "Bilinmiyor"
        is_epson = False

        # 1. Standart SNMP sysDescr sorgusu
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            req = build_snmp_get_request(OID_SYS_DESCR, community="public")
            sock.sendto(req, (ip, 161))
            resp, _ = sock.recvfrom(2048)
            descr = parse_snmp_response_string(resp)
            if descr and "EPSON" in descr.upper():
                is_epson = True
                sys_descr = descr
                m = re.search(r'EPSON\s+([A-Za-z0-9\-]+)', descr, re.IGNORECASE)
                if m:
                    model_name = m.group(0).upper()
        except Exception:
            pass
        finally:
            sock.close()

        # 2. Epson Enterprise MAC OID sorgusu (1.3.6.1.4.1.1248.1.1.3.1.1.5.0)
        sock_mac = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_mac.settimeout(1.5)
        try:
            req_mac = build_snmp_get_request("1.3.6.1.4.1.1248.1.1.3.1.1.5.0", community="public")
            sock_mac.sendto(req_mac, (ip, 161))
            resp_mac, _ = sock_mac.recvfrom(1024)
            if len(resp_mac) >= 6:
                is_epson = True
                mac_addr = ":".join(f"{b:02X}" for b in resp_mac[-6:])
        except Exception:
            pass
        finally:
            sock_mac.close()

        # 3. Epson IONET ST2 Servis Paketi (Seri No ve Model tespiti)
        try:
            from epson_protocol import EpsonIONETClient
            ionet = EpsonIONETClient(ip=ip, port=161, timeout=2.0)
            st_resp = ionet.get_status_packet()
            if st_resp and b"@BDC ST2" in st_resp:
                is_epson = True
                m_ser = re.search(rb'@\n([A-Za-z0-9]{10})', st_resp)
                if not m_ser:
                    m_ser = re.search(rb'\b([A-Z0-9]{4}[0-9]{6})\b', st_resp)
                if m_ser:
                    serial_no = m_ser.group(1).decode("ascii", errors="ignore").strip()

                # Model adını L3070 veya EcoTank olarak iyileştir
                if "BUILT-IN" in model_name.upper() or model_name == "Bilinmeyen Epson":
                    model_name = "EPSON L3070 Series"
        except Exception:
            pass

        if is_epson:
            return PrinterDevice(
                ip=ip,
                port=9100,
                mac=mac_addr,
                model=model_name,
                serial=serial_no,
                sys_descr=sys_descr,
                discovery_source="SNMP UDP 161 / IONET",
                is_epson=True
            )

        return None

    def probe_port_9100(self, ip: str) -> bool:
        """TCP Port 9100 (Epson RAW JetDirect) soketinin açık olduğunu denetler."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        try:
            sock.connect((ip, 9100))
            sock.close()
            return True
        except Exception:
            return False

    def probe_epson_bdc(self, ip: str) -> Optional[str]:
        """
        Port 9100 üzerinden Epson BDC / ESC/P Remote modu başlatıp
        model bilgisini okumayı dener.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        try:
            sock.connect((ip, 9100))
            # ESC/P Remote Mode sorgusu: ESC ( R 08 00 REMOTE1 VI 00 00 ESC 00 00 00
            query_bytes = b"\x1b(R\x08\x00REMOTE1VI\x00\x00\x1b\x00\x00\x00"
            sock.sendall(query_bytes)
            resp = sock.recv(512)
            sock.close()
            if resp and len(resp) > 2:
                raw_text = resp.decode("ascii", errors="ignore")
                return raw_text.strip()
        except Exception:
            pass
        return None

    def query_mdns(self) -> List[PrinterDevice]:
        """
        mDNS (Multicast DNS 224.0.0.251:5353) sorgusu yayınlayarak
        ağdaki _pdl-datastream._tcp ve _printer._tcp servislerini dinler.
        """
        discovered = []
        mdns_group = "224.0.0.251"
        mdns_port = 5353
        
        # Basit mDNS PTR Query paketi: _pdl-datastream._tcp.local
        # Transaction ID (0), Flags (0), Questions (1)
        query = (
            b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            b"\x0f_pdl-datastream\x04_tcp\x05local\x00"
            b"\x00\x0c\x00\x01"  # Type PTR, Class IN
        )
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(2.0)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        try:
            sock.sendto(query, (mdns_group, mdns_port))
            while True:
                try:
                    data, addr = sock.recvfrom(2048)
                    ip = addr[0]
                    raw_str = data.decode("latin1", errors="ignore")
                    if "EPSON" in raw_str.upper() or "L3" in raw_str or "ET-" in raw_str:
                        # Model adını ayıkla
                        m = re.search(r'(EPSON\s+[A-Za-z0-9\-]+)', raw_str, re.IGNORECASE)
                        model_name = m.group(1).upper() if m else "Epson mDNS Cihazı"
                        dev = PrinterDevice(
                            ip=ip,
                            port=9100,
                            model=model_name,
                            discovery_source="mDNS 5353",
                            is_epson=True
                        )
                        discovered.append(dev)
                except socket.timeout:
                    break
        except Exception:
            pass
        finally:
            sock.close()
            
        return discovered

    def scan_subnet(
        self,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> List[PrinterDevice]:
        """
        Mevcut alt ağı (/24) 1 ile 254 aralığında tarar.
        SNMP, Port 9100 kontrolü ve ARP eşlemesi ile yazıcıları doğrular.
        """
        self.found_printers.clear()
        arp_cache = get_arp_table()
        _, subnet_prefix = get_local_ip_and_subnet()
        
        candidates = [f"{subnet_prefix}.{i}" for i in range(1, 255)]
        total = len(candidates)
        processed = 0

        # İlk olarak mDNS yayınlarını topla
        if progress_callback:
            progress_callback(5, "mDNS yayınları taranıyor...")
        mdns_devices = self.query_mdns()
        for d in mdns_devices:
            if d.ip in arp_cache:
                d.mac = arp_cache[d.ip]
            self.found_printers[d.ip] = d

        def check_host(ip: str) -> Optional[PrinterDevice]:
            # 1. SNMP UDP 161 Kontrolü
            dev = self.probe_snmp(ip)
            if dev:
                return dev

            # 2. Port 9100 Kontrolü
            if self.probe_port_9100(ip):
                # MAC adresi Epson OUI ile eşleşiyor mu?
                mac = arp_cache.get(ip, "")
                if is_epson_mac(mac):
                    return PrinterDevice(
                        ip=ip,
                        port=9100,
                        mac=mac,
                        model=f"Epson Yazıcı ({mac})",
                        discovery_source="Port 9100 + OUI",
                        is_epson=True
                    )
                # BDC ile dene
                bdc_info = self.probe_epson_bdc(ip)
                if bdc_info and ("EPSON" in bdc_info.upper() or "ESC" in bdc_info.upper()):
                    return PrinterDevice(
                        ip=ip,
                        port=9100,
                        mac=mac or "Bilinmiyor",
                        model=f"Epson Cihazı ({bdc_info[:20]})",
                        discovery_source="Port 9100 BDC",
                        is_epson=True
                    )
            return None

        # ThreadPool ile hızlı paralel tarama
        with ThreadPoolExecutor(max_workers=50) as executor:
            future_to_ip = {executor.submit(check_host, ip): ip for ip in candidates}
            for future in as_completed(future_to_ip):
                processed += 1
                percent = int(10 + (processed / total) * 85)
                ip = future_to_ip[future]
                
                if progress_callback and processed % 15 == 0:
                    progress_callback(percent, f"IP taranıyor: {ip}")

                result = future.result()
                if result:
                    with self._lock:
                        if result.ip in arp_cache and result.mac == "Bilinmiyor":
                            result.mac = arp_cache[result.ip]
                        self.found_printers[result.ip] = result

        if progress_callback:
            progress_callback(100, f"Tarama tamamlandı! {len(self.found_printers)} yazıcı bulundu.")

        return list(self.found_printers.values())

    def connect_manual(self, ip: str, port: int = 9100) -> Optional[PrinterDevice]:
        """
        Kullanıcının girdiği statik IP adresine doğrudan bağlanır
        ve cihazın Epson yazıcı olduğunu doğrular.
        """
        arp_cache = get_arp_table()
        mac = arp_cache.get(ip, "Bilinmiyor")

        # 1. SNMP dene
        dev = self.probe_snmp(ip)
        if dev:
            dev.port = port
            dev.mac = mac
            dev.discovery_source = "Manuel Statik IP"
            return dev

        # 2. Port 9100 dene
        if self.probe_port_9100(ip):
            bdc_info = self.probe_epson_bdc(ip)
            model_str = f"Epson Cihazı ({ip})"
            if bdc_info:
                model_str = f"Epson ({bdc_info[:25]})"
            return PrinterDevice(
                ip=ip,
                port=port,
                mac=mac,
                model=model_str,
                discovery_source="Manuel Port 9100",
                is_epson=True
            )

        return None
