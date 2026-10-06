"""
main.py - Epson WIC Reset ve Ağ Yönetim Uygulaması Giriş Noktası
Hem Modern PyQt6 Masaüstü Grafik Arayüzünü (GUI) hem de
Komut Satırı (CLI) otomasyon parametrelerini destekler.
"""

import sys
import argparse
import time

from discovery import NetworkDiscoveryEngine
from epson_protocol import EpsonProtocolClient
from eeprom_handler import EpsonEEPROMHandler
from epson_models import EPSON_MODEL_DATABASE, find_model_config


def run_cli_scan():
    """Komut satırından alt ağ taraması yapar."""
    print("=" * 70)
    print("[TARAMA] Yerel Ağdaki Epson Yazıcılar Aranıyor...")
    print("=" * 70)
    engine = NetworkDiscoveryEngine(timeout=2.5)

    def on_prog(percent, text):
        sys.stdout.write(f"\rİlerleme: %{percent} - {text[:40]:<40}")
        sys.stdout.flush()

    devices = engine.scan_subnet(progress_callback=on_prog)
    print("\n" + "=" * 70)
    if not devices:
        print("Ağda otomatik keşfedilen Epson yazıcı bulunamadı.")
        print("Yazıcının açık, aynı Wi-Fi/LAN ağında olduğundan emin olun.")
    else:
        print(f"Tespit Edilen Epson Yazıcı Sayısı: {len(devices)}\n")
        for i, dev in enumerate(devices, 1):
            print(f"[{i}] Model    : {dev.model}")
            print(f"    IP       : {dev.ip}:{dev.port}")
            print(f"    MAC      : {dev.mac}")
            print(f"    Protokol : {dev.discovery_source}")
            print("-" * 50)


def run_cli_info(ip: str, port: int):
    """Belirtilen IP'deki yazıcının durumunu ve bilgilerini gösterir."""
    print("=" * 70)
    print(f"[BİLGİ] {ip}:{port} Epson Yazıcı Tanılama Raporu")
    print("=" * 70)
    client = EpsonProtocolClient(ip=ip, port=port, timeout=4.0)
    handler = EpsonEEPROMHandler(ip=ip, port=port, timeout=4.0)

    try:
        http_data = client.fetch_http_diagnostics()
        status = client.get_printer_status()
        model_name = http_data.get("model") or "EPSON L3070 Series"
        counters = handler.read_waste_ink_counters(detected_model=model_name)

        serial_no = status.get('serial_number') or http_data.get('serial_number') or 'Bilinmiyor'
        fw_ver = http_data.get('firmware_version') or 'Bilinmiyor'

        print(f"Model Adı       : {model_name}")
        print(f"Seri Numarası   : {serial_no}")
        print(f"Firmware Sürümü : {fw_ver}")
        print(f"MAC Adresi      : {http_data.get('mac_address') or 'Bilinmiyor'}")
        print(f"Toplam Baskı    : {http_data.get('page_count') or 'Bilinmiyor'} sayfa")
        print(f"Ağ Geçidi (GW)  : {http_data.get('gateway') or '-'}")
        print(f"Yazıcı Durumu   : {status.get('error_message', 'Hazır')}")
        print("-" * 50)
        print("Atık Mürekkep Pedi Sayaçları (EEPROM):")
        main_pad = counters['main_pad']
        print(f"  * Ana Ped (Main Pad)   : %{main_pad['percent']} ({main_pad['ticks']} / {main_pad['max_ticks']} puan)")
        if counters['platen_pad']['available']:
            platen = counters['platen_pad']
            print(f"  * Tablo Pedi (Platen)  : %{platen['percent']} ({platen['ticks']} / {platen['max_ticks']} puan)")
        print(f"  * Genel Kilit Durumu   : {counters['status']}")
        print("=" * 70)
    except Exception as e:
        print(f"[HATA] Yazıcı sorgulanamadı: {e}")


def run_cli_reset(ip: str, port: int, model: str):
    """Belirtilen yazıcının atık ped sayacını komut satırından sıfırlar."""
    print("=" * 70)
    print(f"[SIFIRLAMA] Hedef: {ip}:{port} | Model: {model}")
    print("=" * 70)
    handler = EpsonEEPROMHandler(ip=ip, port=port, timeout=5.0)

    def print_log(msg):
        print(msg)

    try:
        res = handler.reset_waste_ink_counters(target_model=model, log_callback=print_log)
        if res.get("success"):
            print("\n>>> SIFIRLAMA BAŞARIYLA TAMAMLANDI! <<<")
        else:
            print("\n[UYARI] Sıfırlama işlemi doğrulanamadı.")
    except Exception as e:
        print(f"\n[KRİTİK HATA] Sıfırlama başarısız oldu: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Epson Ağ Yönetim ve Atık Mürekkep Pedi Sıfırlama Aracı (WIC Reset Alternatifi)"
    )
    parser.add_argument("--gui", action="store_true", help="PyQt6 Grafik Arayüzünü Başlat (Varsayılan)")
    parser.add_argument("--scan", action="store_true", help="Ağdaki Epson yazıcıları ara")
    parser.add_argument("--ip", type=str, help="Hedef Epson yazıcı IP adresi")
    parser.add_argument("--port", type=int, default=9100, help="RAW JetDirect portu (Varsayılan: 9100)")
    parser.add_argument("--model", type=str, default="", help="Hedef yazıcı modeli (Örn: L3150, L386, ET-2800)")
    parser.add_argument("--info", action="store_true", help="Yazıcı durum ve sayaç bilgilerini oku")
    parser.add_argument("--reset", action="store_true", help="Atık mürekkep sayacını sıfırla")
    parser.add_argument("--clean", action="store_true", help="Kafa temizleme döngüsü başlat")
    parser.add_argument("--power-flush", action="store_true", help="Derin kafa temizleme (Power Flush) başlat")
    parser.add_argument("--nozzle", action="store_true", help="Püskürtme kontrol testi deseni bastır")
    parser.add_argument("--reboot", action="store_true", help="Yazıcıya Soft-Reset sinyali gönder")

    args = parser.parse_args()

    # CLI komutları kontrolü
    if args.scan:
        run_cli_scan()
        return

    if args.ip:
        if args.info:
            run_cli_info(args.ip, args.port)
            return
        elif args.reset:
            model = args.model or "L3150"
            run_cli_reset(args.ip, args.port, model)
            return
        elif args.clean:
            client = EpsonProtocolClient(ip=args.ip, port=args.port)
            client.trigger_head_cleaning(power_flush=False)
            print(f"[BAŞARILI] {args.ip} için kafa temizleme komutu iletildi.")
            return
        elif args.power_flush:
            client = EpsonProtocolClient(ip=args.ip, port=args.port)
            client.trigger_head_cleaning(power_flush=True)
            print(f"[BAŞARILI] {args.ip} için Güçlü Mürekkep Püskürtme komutu iletildi.")
            return
        elif args.nozzle:
            client = EpsonProtocolClient(ip=args.ip, port=args.port)
            client.trigger_nozzle_check()
            print(f"[BAŞARILI] {args.ip} için püskürtme kontrol testi iletildi.")
            return
        elif args.reboot:
            client = EpsonProtocolClient(ip=args.ip, port=args.port)
            client.send_soft_reset()
            print(f"[BAŞARILI] {args.ip} için yeniden başlatma sinyali iletildi.")
            return

    # Varsayılan: GUI Arayüzünü Başlat
    from gui import run_gui
    run_gui()


if __name__ == "__main__":
    main()
