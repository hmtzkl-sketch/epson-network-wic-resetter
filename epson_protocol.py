"""
epson_protocol.py - Epson İletişim Protokolü ve Komut Enjeksiyon Motoru
Epson ESC/P2, ESC/P-R, BDC (Bi-Directional Communication) ve Remote Mode komutlarını
TCP Port 9100 (RAW) ve Port 80 (HTTP EWS) soket düzeyinde doğrudan yönetir.
"""

import socket
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple, List

# Epson Standart Kaçış ve Protokol Başlatma Sekansları
ESC = b"\x1b"
CMD_REMOTE_ENTER = ESC + b"(R\x08\x00REMOTE1"        # Uzak Bakım Moduna Giriş (Remote Mode 1)
CMD_REMOTE_EXIT  = ESC + b"\x00\x00\x00"              # Uzak Bakım Modundan Çıkış
CMD_BDC_ENTER    = ESC + b"\x01@BDC PS\r\n"           # Epson BDC Packet Stream Giriş
CMD_BDC_STATUS   = ESC + b"\x01@BDC ST\r\n"           # Epson BDC Durum Sorgusu
CMD_BDC_RESET    = ESC + b"\x01@BDC RESET\r\n"        # Epson BDC Donanımsal/Yazılımsal Yeniden Başlatma
CMD_ESCP_RESET   = ESC + b"@"                         # Standart ESC/P Yazıcı Sıfırlama

EPSON_MIB_ROOT = "1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1"


class EpsonProtocolError(Exception):
    """Epson protokol ve soket haberleşme hataları için özel istisna sınıfı."""
    pass


def encode_asn1_len(length: int) -> bytes:
    """ASN.1 BER uzunluk alanını kodlar."""
    if length < 128:
        return bytes([length])
    elif length < 256:
        return bytes([0x81, length])
    else:
        return bytes([0x82, (length >> 8) & 0xFF, length & 0xFF])


def encode_asn1_integer(val: int) -> bytes:
    """ASN.1 BER INTEGER kodlar."""
    if val == 0:
        return b"\x02\x01\x00"
    b = []
    v = val
    while v > 0:
        b.insert(0, v & 0xFF)
        v >>= 8
    if b[0] & 0x80:
        b.insert(0, 0)
    return bytes([0x02, len(b)]) + bytes(b)


def encode_asn1_string(s: bytes | str) -> bytes:
    """ASN.1 BER OCTET STRING kodlar."""
    if isinstance(s, str):
        s = s.encode("latin1")
    return bytes([0x04]) + encode_asn1_len(len(s)) + s


def encode_asn1_oid(oid_str: str) -> bytes:
    """Noktalı OID dizesini ASN.1 BER OID baytlarına çevirir."""
    parts = [int(p) for p in oid_str.split(".")]
    b = [parts[0] * 40 + parts[1]]
    for p in parts[2:]:
        if p < 128:
            b.append(p)
        else:
            sub = []
            v = p
            while v > 0:
                sub.insert(0, v & 0x7F)
                v >>= 7
            for i in range(len(sub) - 1):
                sub[i] |= 0x80
            b.extend(sub)
    return bytes([0x06]) + encode_asn1_len(len(b)) + bytes(b)


class EpsonIONETClient:
    """
    Epson yazıcıların UDP 161 üzerindeki özel SNMP-BDC servis tünelini yöneten istemci.
    WIC Reset ve Epson Adjustment Program araçlarının ağ modunda kullandığı yerel protokoldür.
    Komutlar, OID sonuna alt tanımlayıcı (sub-identifier) olarak eklenerek GetRequest ile iletilir.
    """

    def __init__(self, ip: str, port: int = 161, timeout: float = 3.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout

    def send_command(self, cmd_bytes: bytes, timeout: Optional[float] = None) -> bytes:
        """
        Ham komut baytlarını SNMP OID alt dizisi olarak paketler ve yazıcıya iletir.
        Yazıcı yanıtındaki OCTET STRING alanını ayrıştırarak ham yanıtı döner.
        """
        oid_suffix = ".".join(str(b) for b in cmd_bytes)
        full_oid = f"{EPSON_MIB_ROOT}.{oid_suffix}"
        oid_b = encode_asn1_oid(full_oid)
        val_b = b"\x05\x00"  # NULL

        varbind = bytes([0x30]) + encode_asn1_len(len(oid_b) + len(val_b)) + oid_b + val_b
        varbind_list = bytes([0x30]) + encode_asn1_len(len(varbind)) + varbind
        pdu_body = encode_asn1_integer(1) + encode_asn1_integer(0) + encode_asn1_integer(0) + varbind_list
        pdu = bytes([0xA0]) + encode_asn1_len(len(pdu_body)) + pdu_body
        msg_body = encode_asn1_integer(0) + encode_asn1_string("public") + pdu
        packet = bytes([0x30]) + encode_asn1_len(len(msg_body)) + msg_body

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout or self.timeout)
        try:
            sock.sendto(packet, (self.ip, self.port))
            data, _ = sock.recvfrom(4096)
            
            # Yanıt içindeki OID'den sonra gelen OCTET STRING (0x04) değerini ayıkla
            oid_idx = data.find(oid_b)
            if oid_idx != -1:
                val_idx = oid_idx + len(oid_b)
                if val_idx < len(data) and data[val_idx] == 0x04:
                    l = data[val_idx + 1]
                    if l & 0x80:
                        len_bytes = l & 0x7F
                        total_len = int.from_bytes(data[val_idx + 2 : val_idx + 2 + len_bytes], "big")
                        payload = data[val_idx + 2 + len_bytes : val_idx + 2 + len_bytes + total_len]
                    else:
                        payload = data[val_idx + 2 : val_idx + 2 + l]
                    # Genellikle ilk bayt 0x00 null bayttır, temizle
                    if payload and payload[0] == 0:
                        payload = payload[1:]
                    return payload
            return data
        except socket.timeout:
            raise EpsonProtocolError(f"Epson IONET zaman aşımı ({self.timeout}s): {self.ip}:{self.port}")
        except Exception as e:
            raise EpsonProtocolError(f"Epson IONET soket hatası ({self.ip}): {str(e)}")
        finally:
            sock.close()

    def get_status_packet(self) -> bytes:
        """st\\x01\\x00\\x01 durum paketini sorgular."""
        return self.send_command(bytes.fromhex("73 74 01 00 01"))

    def get_version_packet(self) -> bytes:
        """vi\\x01\\x00\\x00 firmware versiyon paketini sorgular."""
        return self.send_command(bytes.fromhex("76 69 01 00 00"))

    def read_eeprom_byte(self, offset: int) -> Optional[int]:
        """
        EEPROM'dan tek bayt okur:
        Paket: 7C 7C 07 00 10 08 41 BE A0 <offset> 00
        Yanıt: @BDC PS\\r\\nEE:00<offset><hex>;\\x0c
        """
        cmd = bytes.fromhex("7C 7C 07 00 10 08 41 BE A0") + bytes([offset, 0])
        resp = self.send_command(cmd)
        m = re.search(rb"EE:[0-9A-Fa-f]{4}([0-9A-Fa-f]{2});", resp)
        if m:
            return int(m.group(1), 16)
        return None

    def write_eeprom_byte(self, offset: int, value: int, auth_key: bytes = b"Tjobcvoh") -> bool:
        """
        EEPROM'a tek bayt yazar:
        Paket: 7C 7C 10 00 10 08 42 BD 21 <offset> 00 <value> <auth_key>
        Yanıt: ||:42:OK;\\x0c
        """
        cmd = bytes.fromhex("7C 7C 10 00 10 08 42 BD 21") + bytes([offset, 0, value]) + auth_key
        resp = self.send_command(cmd)
        return b"OK" in resp or b":42:OK" in resp


class EpsonProtocolClient:
    """
    Epson yazıcılarıyla doğrudan soket düzeyinde haberleşen protokol yöneticisi.
    Her istekte 5.0 saniyelik katı zaman aşımı uygular ve soket kilitlenmelerini önler.
    SNMP BDC (UDP 161) ve Port 9100 / 80 protokollerini entegre yönetir.
    """

    def __init__(self, ip: str, port: int = 9100, timeout: float = 5.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.ionet = EpsonIONETClient(ip=ip, port=161, timeout=timeout)

    def send_raw_command(self, payload: bytes, read_response: bool = True, buffer_size: int = 4096) -> bytes:
        """
        Port 9100 (RAW JetDirect) üzerine bayt dizisi iletir ve varsa yanıtı okur.
        Katı timeout yönetimi ile soketi daima güvenle kapatır.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        response = bytearray()
        try:
            sock.connect((self.ip, self.port))
            sock.sendall(payload)

            if read_response:
                # Yazıcı yanıt verene kadar veya timeout süresince veri topla
                sock.settimeout(1.5)
                while True:
                    try:
                        chunk = sock.recv(buffer_size)
                        if not chunk:
                            break
                        response.extend(chunk)
                        # Yeterli veri geldiyse veya paket tamamlandıysa
                        if len(chunk) < buffer_size:
                            time.sleep(0.05)
                            break
                    except socket.timeout:
                        break
        except socket.timeout as e:
            raise EpsonProtocolError(f"Yazıcı soket zaman aşımı ({self.timeout}s): {self.ip}:{self.port}") from e
        except ConnectionRefusedError as e:
            raise EpsonProtocolError(f"Bağlantı reddedildi. Port {self.port} kapalı: {self.ip}") from e
        except Exception as e:
            raise EpsonProtocolError(f"Ağ soket hatası ({self.ip}): {str(e)}") from e
        finally:
            sock.close()

        return bytes(response)

    # -------------------------------------------------------------------------
    # Uzak Bakım Modu (Remote Mode) Komut İnşası
    # Format: [2 Bayt Komut Adı] + [2 Bayt Uzunluk (Little Endian)] + [Parametre]
    # -------------------------------------------------------------------------
    def build_remote_packet(self, cmd_name: str, params: bytes = b"") -> bytes:
        """
        ESC ( R ... REMOTE1 ile sarmalanmış standart Epson Remote komut paketi üretir.
        """
        if len(cmd_name) != 2:
            raise ValueError("Epson Remote komut adı tam olarak 2 karakter olmalıdır (ör. 'VI', 'CH', 'NC').")
        cmd_bytes = cmd_name.encode("ascii")
        param_len = len(params).to_bytes(2, byteorder="little")
        packet_body = cmd_bytes + param_len + params
        return CMD_REMOTE_ENTER + packet_body + CMD_REMOTE_EXIT

    def get_version_info(self) -> Dict[str, str]:
        """
        'VI' (Version Information) komutu ile yazıcının firmware kimliğini sorgular.
        Önce UDP 161 IONET servis modunu dener, ardından TCP 9100'e başvurur.
        """
        info = {"raw": "", "parsed": "", "version_str": ""}
        try:
            raw_ionet = self.ionet.get_version_packet()
            if raw_ionet:
                text = raw_ionet.decode("latin1", errors="ignore").strip()
                info["raw"] = raw_ionet.hex()
                info["parsed"] = text
                m = re.search(r'vi:[0-9]+:([A-Za-z0-9]+);', text, re.IGNORECASE)
                if m:
                    info["version_str"] = m.group(1).strip()
                    return info
        except Exception:
            pass

        try:
            packet = self.build_remote_packet("VI")
            raw = self.send_raw_command(packet, read_response=True)
            if raw:
                text = raw.decode("latin1", errors="ignore").strip()
                info["raw"] = raw.hex()
                info["parsed"] = text
                m = re.search(r'([A-Za-z0-9\-_\.\s]{4,})', text)
                if m:
                    info["version_str"] = m.group(1).strip()
        except Exception:
            pass

        return info

    def get_printer_status(self) -> Dict[str, Any]:
        """
        IONET ST2 ve BDC ST komutları ile yazıcının güncel durumunu sorgular.
        Yazıcının Meşgul (Busy), Hata, Seri No ve Ped uyarısı durumunu döner.
        """
        status_info = {
            "online": False,
            "busy": False,
            "ink_warning": False,
            "fatal_error": False,
            "error_message": "Hazır",
            "serial_number": "",
            "raw_status": b""
        }
        # 1. Öncelikli olarak UDP 161 IONET ST2 dene
        try:
            resp_ionet = self.ionet.get_status_packet()
            if resp_ionet and b"@BDC ST2" in resp_ionet:
                status_info["online"] = True
                status_info["raw_status"] = resp_ionet
                
                # Seri No ayıkla (Örn: @\nXXXXXXXXXX)
                m_serial = re.search(rb'@\n([A-Za-z0-9]{10})', resp_ionet)
                if not m_serial:
                    m_serial = re.search(rb'\b([A-Z0-9]{4}[0-9]{6})\b', resp_ionet)
                if m_serial:
                    status_info["serial_number"] = m_serial.group(1).decode("ascii", errors="ignore").strip()

                resp_str = resp_ionet.decode("latin1", errors="ignore")
                if "overflow" in resp_str.lower() or "pad" in resp_str.lower():
                    status_info["fatal_error"] = True
                    status_info["error_message"] = "Atık Mürekkep Pedi Doluluk Uyarısı (Servis Gerekli)"
                else:
                    status_info["error_message"] = "Yazdırmaya Hazır"
                return status_info
        except Exception:
            pass

        # 2. Port 9100 fallback
        try:
            bdc_query = CMD_BDC_STATUS
            resp = self.send_raw_command(bdc_query, read_response=True)
            if resp:
                status_info["online"] = True
                status_info["raw_status"] = resp
                resp_text = resp.decode("latin1", errors="ignore")
                if "BUSY" in resp_text.upper() or "PRINTING" in resp_text.upper():
                    status_info["busy"] = True
                    status_info["error_message"] = "Yazıcı Meşgul (İşlem Yapılıyor)"
                if "FATAL" in resp_text.upper() or "ERROR" in resp_text.upper():
                    status_info["fatal_error"] = True
                    status_info["error_message"] = "Kritik Donanım / Bakım Hatası"
            else:
                remote_st = self.build_remote_packet("ST")
                resp2 = self.send_raw_command(remote_st, read_response=True)
                if resp2:
                    status_info["online"] = True
                    status_info["raw_status"] = resp2
        except Exception as e:
            status_info["error_message"] = f"Hata: {str(e)}"

        return status_info

    # -------------------------------------------------------------------------
    # Bakım ve Tanılama İşlemleri
    # -------------------------------------------------------------------------
    def trigger_nozzle_check(self) -> bool:
        """
        'NC' (Nozzle Check) komutunu göndererek püskürtme kanalı kontrol desenini bastırır.
        """
        # NC komutu: Parametre uzunluğu 2 bayt, değer: 0x00 0x00
        packet = self.build_remote_packet("NC", params=b"\x00\x00")
        self.send_raw_command(packet, read_response=False)
        return True

    def trigger_head_cleaning(self, power_flush: bool = False) -> bool:
        """
        'CH' (Clean Head) komutunu gönderir.
        power_flush=False: Standart kafa temizleme (Normal Cleaning)
        power_flush=True : Derin kafa temizleme (Power Ink Flushing)
        """
        if power_flush:
            # Derin Temizleme: param baytları 0x00 0x01
            params = b"\x00\x01"
        else:
            # Normal Temizleme: param baytları 0x00 0x00
            params = b"\x00\x00"

        packet = self.build_remote_packet("CH", params=params)
        self.send_raw_command(packet, read_response=False)
        return True

    def send_soft_reset(self) -> bool:
        """
        Yazıcıya Soft-Reset / Yeniden Başlatma sinyali gönderir (@BDC RESET ve ESC @).
        """
        try:
            # BDC Reset
            self.send_raw_command(CMD_BDC_RESET, read_response=False)
        except Exception:
            pass

        try:
            # Standart ESC/P Reset
            self.send_raw_command(CMD_ESCP_RESET, read_response=False)
        except Exception:
            pass

        return True

    # -------------------------------------------------------------------------
    # HTTP EWS (Gömülü Web Sunucusu) Ağ Ayarları ve Cihaz Bilgisi Okuma (Port 80)
    # -------------------------------------------------------------------------
    def fetch_http_diagnostics(self) -> Dict[str, str]:
        """
        Port 80 (HTTP) üzerinden gömülü web arayüzünü sorgulayarak
        seri no, firmware ve ağ yapılandırma detaylarını okur.
        """
        results = {
            "model": "",
            "serial_number": "",
            "firmware_version": "",
            "ip_address": self.ip,
            "mac_address": "",
            "gateway": "",
            "dns": "",
            "hostname": "",
            "page_count": "",
        }

        urls = [
            f"http://{self.ip}/PRESENTATION/ADVANCED/INFO_PRTINFO.HTM",
            f"http://{self.ip}/AIRPRINT/status.xml",
            f"http://{self.ip}/PRESENTATION/HTML/TOP/PRTINFO.HTML",
            f"http://{self.ip}/api/system/status",
        ]

        for url in urls:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "EpsonNet-Config-Manager/2.0"}
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    content = resp.read().decode("latin1", errors="ignore")

                    # Model Adı Ayrıştırma
                    m_model = re.search(r'(EPSON\s+[A-Za-z0-9\-]+)', content, re.IGNORECASE)
                    if m_model and not results["model"]:
                        results["model"] = m_model.group(1).upper()

                    # Seri Numarası Ayrıştırma (10 haneli alfanümerik kod)
                    m_serial = re.search(r'Serial\s*Number[^:]*:\s*([A-Za-z0-9]{10})', content, re.IGNORECASE)
                    if not m_serial:
                        m_serial = re.search(r'<serial_number>([A-Za-z0-9]{10})</serial_number>', content, re.IGNORECASE)
                    if not m_serial:
                        m_serial = re.search(r'\b([A-Z0-9]{4}[0-9]{6})\b', content)
                    if m_serial and not results["serial_number"]:
                        results["serial_number"] = m_serial.group(1).strip()

                    # Firmware Sürümü
                    m_fw = re.search(r'Firmware\s*Version[^:]*:\s*([A-Za-z0-9\._\-]+)', content, re.IGNORECASE)
                    if m_fw and not results["firmware_version"]:
                        results["firmware_version"] = m_fw.group(1).strip()

                    # MAC Adresi
                    m_mac = re.search(r'([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})', content)
                    if m_mac and not results["mac_address"]:
                        results["mac_address"] = m_mac.group(1).replace("-", ":").upper()

                    # Toplam Baskı Sayısı (Page count)
                    m_pages = re.search(r'Total\s*Pages?[^:]*:\s*([0-9,]+)', content, re.IGNORECASE)
                    if m_pages and not results["page_count"]:
                        results["page_count"] = m_pages.group(1).replace(",", "").strip()

                    # Ağ Geçidi / DNS / Hostname
                    m_gw = re.search(r'Default\s*Gateway[^:]*:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', content, re.IGNORECASE)
                    if m_gw and not results["gateway"]:
                        results["gateway"] = m_gw.group(1)

                    m_dns = re.search(r'DNS\s*Server[^:]*:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', content, re.IGNORECASE)
                    if m_dns and not results["dns"]:
                        results["dns"] = m_dns.group(1)

                    m_host = re.search(r'Host\s*Name[^:]*:\s*([A-Za-z0-9\-]+)', content, re.IGNORECASE)
                    if m_host and not results["hostname"]:
                        results["hostname"] = m_host.group(1)

            except Exception:
                continue

        # SNMP / IONET üzerinden eksik bilgileri tamamla
        try:
            st = self.get_printer_status()
            if st.get("serial_number") and not results["serial_number"]:
                results["serial_number"] = st["serial_number"]
        except Exception:
            pass

        try:
            vi = self.get_version_info()
            if vi.get("version_str") and not results["firmware_version"]:
                results["firmware_version"] = vi["version_str"]
        except Exception:
            pass

        # SNMP ile MAC ve Hostname sorgula (1.3.6.1.4.1.1248.1.1.3.1.1.5.0 ve 1.0)
        try:
            from discovery import build_snmp_get_request
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1.5)
            # MAC OID
            if not results["mac_address"]:
                s.sendto(build_snmp_get_request("1.3.6.1.4.1.1248.1.1.3.1.1.5.0"), (self.ip, 161))
                d, _ = s.recvfrom(1024)
                if len(d) >= 6:
                    mac_bytes = d[-6:]
                    results["mac_address"] = ":".join(f"{b:02X}" for b in mac_bytes)
            # Hostname OID
            if not results["hostname"]:
                s.sendto(build_snmp_get_request("1.3.6.1.4.1.1248.1.1.3.1.1.1.0"), (self.ip, 161))
                d2, _ = s.recvfrom(1024)
                m_h = re.search(rb'\x04([\x01-\x1f])([A-Za-z0-9\-]+)', d2)
                if m_h:
                    results["hostname"] = m_h.group(2).decode("ascii", errors="ignore")
            s.close()
        except Exception:
            pass

        return results
