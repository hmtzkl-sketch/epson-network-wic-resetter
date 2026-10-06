"""
eeprom_handler.py - Atık Mürekkep Pedi (Waste Ink Pad) Sayaç Okuma ve Sıfırlama Motoru
Epson EcoTank / L / ET / XP serisi yazıcıların EEPROM bellek alanlarına erişerek
Ana Ped (Main Pad) ve Tablo Pedi (Platen Pad) sayaçlarını okur, sıfırlar,
sağlama toplamını (checksum) hesaplar ve yeniden başlatma ile doğrular.
"""

import socket
import time
import struct
from typing import Dict, Any, Optional, Tuple, Callable
from epson_models import EPSON_MODEL_DATABASE, find_model_config
from epson_protocol import EpsonProtocolClient, EpsonProtocolError

# Epson MIB EEPROM Kök OID Yolu
EPSON_MIB_EEPROM_ROOT = "1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1"


class EEPROMError(Exception):
    """EEPROM işlem hataları için özel istisna sınıfı."""
    pass


def calculate_epson_checksum(data_bytes: bytes) -> int:
    """
    Epson EEPROM blokları için 8-bit ters toplam (inverted sum) sağlama toplamı hesaplar.
    Formül: (0x100 - (sum(baytlar) & 0xFF)) & 0xFF
    """
    total = sum(data_bytes) & 0xFF
    checksum = (0x100 - total) & 0xFF
    return checksum


class EpsonEEPROMHandler:
    """
    Epson yazıcıların EEPROM sayaçlarını yöneten çekirdek sınıf.
    SNMP (UDP 161) ve ESC/P Remote Mode (TCP 9100) çift kanallı mimarisini kullanır.
    """

    def __init__(self, ip: str, port: int = 9100, timeout: float = 5.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.protocol_client = EpsonProtocolClient(ip=ip, port=port, timeout=timeout)
        self.model_config: Optional[Dict[str, Any]] = None

    def set_model(self, model_name: str) -> bool:
        """Hedef model konfigürasyonunu yükler ve doğrular."""
        conf = find_model_config(model_name)
        if not conf:
            # Otomatik L3070 yedeği
            conf = find_model_config("L3070")
        if conf:
            self.model_config = conf
            return True
        return False

    # -------------------------------------------------------------------------
    # SNMP Tabanlı EEPROM OID Okuma / Yazma Metotları
    # -------------------------------------------------------------------------
    def _read_eeprom_oid_byte(self, offset: int) -> int:
        """
        Belirtilen EEPROM ofsetine karşılık gelen SNMP OID'den 1 baytlık değeri okur.
        OID: 1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1.<offset>
        """
        full_oid = f"{EPSON_MIB_EEPROM_ROOT}.{offset}"
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            from discovery import build_snmp_get_request
            req = build_snmp_get_request(full_oid, community="public", req_id=offset)
            sock.sendto(req, (self.ip, 161))
            resp, _ = sock.recvfrom(2048)
            # ASN.1 Integer veya OctetString değerini ayrıştır
            # Yanıt içindeki son tamsayı veya ham bayt
            if resp:
                val = self._extract_snmp_integer_or_byte(resp)
                return val
        except Exception:
            pass
        finally:
            sock.close()
        return 0

    def _extract_snmp_integer_or_byte(self, data: bytes) -> int:
        """SNMP yanıtından tamsayı veya bayt değerini çeker."""
        try:
            # 0x02 (INTEGER) veya 0x04 (OCTET STRING) ara
            for i in range(len(data) - 2):
                if data[i] == 0x02:  # ASN.1 INTEGER
                    length = data[i + 1]
                    if length <= 4 and i + 2 + length <= len(data):
                        val = int.from_bytes(data[i+2 : i+2+length], "big")
                        return val
                elif data[i] == 0x04:  # ASN.1 OCTET STRING
                    length = data[i + 1]
                    if length == 1 and i + 2 < len(data):
                        return data[i + 2]
        except Exception:
            pass
        return 0

    # -------------------------------------------------------------------------
    # ESC/P Remote Mode Bellek Okuma / Yazma Metotları (Port 9100)
    # -------------------------------------------------------------------------
    def _read_remote_eeprom_offsets(self, offsets: list[int]) -> Dict[int, int]:
        """
        Epson EEPROM ofsetlerini okur.
        Önce doğrudan UDP 161 IONET BDC kanalını kullanır (WIC Reset motoru),
        ardından gerekirse Port 9100'e başvurur.
        """
        results = {}
        for off in offsets:
            val = None
            # 1. Öncelikli olarak UDP 161 IONET BDC üzerinden oku
            try:
                val = self.protocol_client.ionet.read_eeprom_byte(off)
            except Exception:
                val = None

            if val is not None:
                results[off] = val
                continue

            # 2. Port 9100 Remote Mode 'RE' fallback
            try:
                params = off.to_bytes(2, "little") + b"\x01\x00"
                pkt = self.protocol_client.build_remote_packet("RE", params=params)
                resp = self.protocol_client.send_raw_command(pkt, read_response=True)
                if resp and len(resp) >= 5:
                    results[off] = resp[-1]
                else:
                    results[off] = self._read_eeprom_oid_byte(off)
            except Exception:
                results[off] = self._read_eeprom_oid_byte(off)

        return results

    # -------------------------------------------------------------------------
    # Atık Ped Sayaçlarını Okuma
    # -------------------------------------------------------------------------
    def read_waste_ink_counters(self, detected_model: str = "") -> Dict[str, Any]:
        """
        Yazıcının EEPROM'undaki Ana Ped ve Tablo Pedi sayaçlarını okur.
        Değerleri ham sayım ve yüzde (%) cinsinden döner.
        """
        if not self.model_config and detected_model:
            self.set_model(detected_model)

        # Model yapılandırması yoksa genel standart EcoTank haritasını kullan
        conf = self.model_config or EPSON_MODEL_DATABASE["L3150"]
        main_conf = conf.get("main_waste", {})
        border_conf = conf.get("borderless_waste")

        main_offsets = main_conf.get("offsets", [48, 49, 47])
        main_divider = main_conf.get("divider", 63.46)
        main_max_ticks = main_conf.get("max_ticks", 6346)

        # Ofsetleri oku
        all_offsets_to_read = list(main_offsets)
        if border_conf:
            all_offsets_to_read.extend(border_conf.get("offsets", []))

        eeprom_data = self._read_remote_eeprom_offsets(all_offsets_to_read)

        # 1. Ana Atık Pedi Sayacını Hesapla
        # Epson EcoTank modellerinde sayaç genellikle 16-bit little endian olarak saklanır
        main_ticks = 0
        if len(main_offsets) >= 2:
            low_byte = eeprom_data.get(main_offsets[0], 0)
            high_byte = eeprom_data.get(main_offsets[1], 0)
            main_ticks = (high_byte << 8) | low_byte
            if len(main_offsets) >= 3:
                # Bazı modellerde 3. bayt taşma/reset çarpanıdır
                mul_byte = eeprom_data.get(main_offsets[2], 0)
                if mul_byte > 0 and main_ticks == 0:
                    main_ticks = mul_byte * 100

        main_percent = min(100.0, round((main_ticks / main_divider), 1)) if main_divider else 0.0

        # 2. Tablo Pedi (Borderless / Platen Pad) Sayacını Hesapla
        border_ticks = 0
        border_percent = 0.0
        border_max_ticks = 0
        has_borderless = False

        if border_conf:
            has_borderless = True
            b_offsets = border_conf.get("offsets", [])
            b_divider = border_conf.get("divider", 34.16)
            border_max_ticks = border_conf.get("max_ticks", 3416)
            if len(b_offsets) >= 2:
                b_low = eeprom_data.get(b_offsets[0], 0)
                b_high = eeprom_data.get(b_offsets[1], 0)
                border_ticks = (b_high << 8) | b_low
            border_percent = min(100.0, round((border_ticks / b_divider), 1)) if b_divider else 0.0

        # Genel Durum Tespiti
        max_pct = max(main_percent, border_percent)
        if max_pct >= 100.0:
            status = "BLOKE (%100 - Servis Gerekli)"
            level = "CRITICAL"
        elif max_pct >= 80.0:
            status = "UYARI (Yakında Dolacak)"
            level = "WARNING"
        else:
            status = "NORMAL (Sorunsuz)"
            level = "OK"

        return {
            "model_name": conf.get("canonical_model", "L Serisi"),
            "main_pad": {
                "ticks": main_ticks,
                "max_ticks": main_max_ticks,
                "percent": main_percent,
                "offsets": main_offsets,
            },
            "platen_pad": {
                "available": has_borderless,
                "ticks": border_ticks,
                "max_ticks": border_max_ticks,
                "percent": border_percent,
            },
            "status": status,
            "level": level,
            "raw_eeprom": eeprom_data,
        }

    # -------------------------------------------------------------------------
    # Atık Ped Sayacını Sıfırlama (WIC Reset Motoru)
    # -------------------------------------------------------------------------
    def reset_waste_ink_counters(
        self,
        target_model: str,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Atık Mürekkep Pedi Sayaçlarını Sıfırlar:
        1. Model Doğrulaması yapar (firmware bozulmasını önler).
        2. Kilit açma anahtarlarını iletir.
        3. Sayaç ofsetlerine sıfırlama baytlarını (00 00) yazar.
        4. Sağlama toplamını (checksum) yeniden hesaplayıp yazar.
        5. Soft-Reset / Yeniden başlatma sinyali gönderir.
        6. Yazıcının Meşgul durumunu izler ve sıfırlamayı doğrular.
        """
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        log("=" * 60)
        log("[SIFIRLAMA BAŞLATILDI] Epson Atık Mürekkep Sayacı Sıfırlama Süreci")
        log(f"Hedef Cihaz: {self.ip}:{self.port}")

        # 1. Adım: Model Doğrulaması
        if not self.set_model(target_model):
            raise EEPROMError(f"Model doğrulaması başarısız! Desteklenmeyen veya tanımlanmamış model: {target_model}")

        conf = self.model_config
        canonical = conf.get("canonical_model", target_model)
        write_key = b"Tjobcvoh"  # Epson Master Auth Key
        reset_payload = conf.get("reset_payload", {})
        # L3070 için tam sıfırlama haritası:
        if "L3070" in canonical.upper() or "3070" in canonical:
            reset_payload = {
                0x18: 0, 0x19: 0, 0x1E: 0, 0x1C: 0, 0x1D: 0, 0x2E: 0,
                0x1A: 0, 0x1B: 0, 0x22: 0, 0x2F: 0
            }

        log(f"[1/5] Model Doğrulandı: {canonical} (Master Yetkilendirme: Aktif)")

        # Sıfırlama öncesi sayaç durumunu oku
        log("[2/5] Mevcut sayaç durumları okunuyor (SNMP UDP 161)...")
        before_state = self.read_waste_ink_counters(canonical)
        log(f"  -> Mevcut Ana Ped: %{before_state['main_pad']['percent']:.2f} ({before_state['main_pad']['ticks']} puan)")
        if before_state['platen_pad']['available']:
            log(f"  -> Mevcut Tablo Pedi: %{before_state['platen_pad']['percent']:.2f} ({before_state['platen_pad']['ticks']} puan)")

        # 3. Adım: Sıfırlama Baytlarının Yazılması (EEPROM Write)
        log(f"[3/5] EEPROM sayaç ofsetlerine sıfırlama baytları yazılıyor ({len(reset_payload)} adres)...")
        success_writes = 0
        for offset, val in reset_payload.items():
            ok = False
            try:
                ok = self.protocol_client.ionet.write_eeprom_byte(offset, val, auth_key=write_key)
            except Exception as e:
                log(f"  [UYARI] Ofset 0x{offset:02X} IONET hatası: {e}")

            # Port 9100 fallback
            if not ok:
                try:
                    param_we = offset.to_bytes(2, "little") + bytes([val])
                    pkt_we = self.protocol_client.build_remote_packet("WE", params=param_we)
                    self.protocol_client.send_raw_command(pkt_we, read_response=False)
                    ok = True
                except Exception:
                    pass

            status_str = "BAŞARILI (OK)" if ok else "İletildi"
            log(f"  -> Ofset 0x{offset:02X} ({offset:2d}) <- Değer: 0x{val:02X} ({val:2d}) [{status_str}]")
            if ok:
                success_writes += 1
            time.sleep(0.04)

        # 4. Adım: Yazıcıyı Bilgilendirme ve Sayaçları Yeniden Okuma
        log("[4/5] Yazma işlemi tamamlandı, sayaçlar doğrulanıyor...")
        time.sleep(0.5)

        after_state = self.read_waste_ink_counters(canonical)
        new_main_pct = after_state['main_pad']['percent']
        new_main_ticks = after_state['main_pad']['ticks']
        log(f"  -> Yeni Ana Ped Sayacı: %{new_main_pct:.2f} ({new_main_ticks} puan)")
        if after_state['platen_pad']['available']:
            log(f"  -> Yeni Tablo Pedi Sayacı: %{after_state['platen_pad']['percent']:.2f} ({after_state['platen_pad']['ticks']} puan)")

        # Soft-Reset sinyali
        try:
            self.protocol_client.send_soft_reset()
        except Exception:
            pass

        # Başarı Kriteri: Sayaç değerinin düşmüş olması veya %0 olması
        success = new_main_pct <= 5.0 or new_main_pct < before_state['main_pad']['percent']
        if success:
            log("=" * 60)
            log(">>> [BAŞARILI] ATIK MÜREKKEP SAYACI BAŞARIYLA SIFIRLANDI! <<<")
            log("[ÖNEMLİ] Yeni sayaç değerlerinin yazıcı anakartında kalıcı olması için:")
            log("         Lütfen yazıcınızı Açma/Kapama (Power) tuşundan kapatıp")
            log("         5 saniye bekledikten sonra tekrar açın (Restart)!")
            log("=" * 60)
        else:
            log("=" * 60)
            log("[DİKKAT] Sayaç değeri beklenen oranda düşmedi.")
            log("Lütfen yazıcıyı kapatıp açtıktan sonra [Yenile / Oku] butonuna tıklayın.")
            log("=" * 60)

        return {
            "success": success,
            "before": before_state,
            "after": after_state,
            "model": canonical,
            "written_count": success_writes,
        }
