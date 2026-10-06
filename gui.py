"""
gui.py - Epson Ağ Yönetim ve Atık Mürekkep Pedi Sıfırlama Masaüstü Arayüzü (PyQt6)
Modern, koyu temalı, gerçek zamanlı soket loglamalı ve engelsiz (non-blocking)
iş parçacığı (QThread) mimarisiyle çalışan profesyonel kontrol paneli.
"""

import sys
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QProgressBar,
    QTextEdit, QGroupBox, QLineEdit, QDialog, QMessageBox,
    QFrame, QCheckBox, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor, QIcon

from discovery import NetworkDiscoveryEngine, PrinterDevice
from epson_protocol import EpsonProtocolClient, EpsonProtocolError
from eeprom_handler import EpsonEEPROMHandler, EEPROMError
from epson_models import EPSON_MODEL_DATABASE, find_model_config


# =============================================================================
# Arka Plan İş Parçacıkları (Background Worker Threads)
# =============================================================================

class DiscoveryWorker(QThread):
    """Ağ taramasını arka planda yürüten iş parçacığı."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(list)
    log_msg = pyqtSignal(str)

    def run(self):
        self.log_msg.emit("[AĞ KEŞFİ] Yerel alt ağ taranıyor (SNMP UDP 161 + mDNS + Port 9100)...")
        engine = NetworkDiscoveryEngine(timeout=2.0)
        
        def on_prog(percent: int, text: str):
            self.progress.emit(percent, text)
            if percent % 20 == 0:
                self.log_msg.emit(f"[TARAMA] %{percent} - {text}")

        devices = engine.scan_subnet(progress_callback=on_prog)
        self.finished.emit(devices)


class PrinterQueryWorker(QThread):
    """Seçilen yazıcının detaylarını ve EEPROM sayaçlarını okuyan iş parçacığı."""
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    log_msg = pyqtSignal(str)

    def __init__(self, device: PrinterDevice, preferred_model: str = "L3070"):
        super().__init__()
        self.device = device
        self.preferred_model = preferred_model or "L3070"

    def run(self):
        ip = self.device.ip
        self.log_msg.emit(f"[CİHAZ SORGUSU] {ip} cihazına bağlanılıyor (Port 9100 / 80 / 161)...")
        try:
            protocol = EpsonProtocolClient(ip=ip, port=self.device.port, timeout=4.0)
            handler = EpsonEEPROMHandler(ip=ip, port=self.device.port, timeout=4.0)

            # 1. HTTP ve ESC/P Durumu
            http_info = protocol.fetch_http_diagnostics()
            status_info = protocol.get_printer_status()

            # 2. Model İsmi Netleştirme
            detected_raw = (
                http_info.get("model") or
                self.device.model or
                self.preferred_model
            )
            # Generic "BUILT-IN" veya print server adı varsa tercih edilen modele (L3070) yönlendir
            if "BUILT-IN" in detected_raw.upper() or "PRINT SERVER" in detected_raw.upper():
                effective_model = self.preferred_model
                self.log_msg.emit(f"[BİLGİ] Ağ kartı adı '{detected_raw}' algılandı -> Model '{effective_model}' olarak eşlendi.")
            else:
                effective_model = detected_raw

            # 3. EEPROM Sayaçlarını Oku
            self.log_msg.emit(f"[EEPROM] {effective_model} modeli için sayaç ofsetleri okunuyor...")
            counter_data = handler.read_waste_ink_counters(detected_model=effective_model)

            merged = {
                "ip": ip,
                "port": self.device.port,
                "mac": http_info.get("mac_address") or self.device.mac,
                "model": effective_model,
                "detected_raw": detected_raw,
                "serial": status_info.get("serial_number") or http_info.get("serial_number") or self.device.serial,
                "firmware": http_info.get("firmware_version") or self.device.firmware,
                "page_count": http_info.get("page_count") or "Bilinmiyor",
                "gateway": http_info.get("gateway") or "-",
                "dns": http_info.get("dns") or "-",
                "status_text": status_info.get("error_message", "Hazır"),
                "counters": counter_data,
            }
            self.data_ready.emit(merged)
        except Exception as e:
            self.error_occurred.emit(str(e))


class ResetCounterWorker(QThread):
    """Atık mürekkep sayacı sıfırlama sürecini yöneten iş parçacığı."""
    log_stream = pyqtSignal(str)
    reset_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, ip: str, port: int, model: str):
        super().__init__()
        self.ip = ip
        self.port = port
        self.model = model

    def run(self):
        handler = EpsonEEPROMHandler(ip=self.ip, port=self.port, timeout=5.0)
        try:
            result = handler.reset_waste_ink_counters(
                target_model=self.model,
                log_callback=lambda msg: self.log_stream.emit(msg)
            )
            self.reset_complete.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))


class MaintenanceWorker(QThread):
    """Kafa temizleme, derin temizleme ve püskürtme kontrol işlemlerini yürüten iş parçacığı."""
    log_msg = pyqtSignal(str)
    action_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, ip: str, port: int, action: str):
        super().__init__()
        self.ip = ip
        self.port = port
        self.action = action

    def run(self):
        client = EpsonProtocolClient(ip=self.ip, port=self.port, timeout=5.0)
        try:
            if self.action == "nozzle_check":
                self.log_msg.emit(f"[KOMUT] {self.ip} -> Püskürtme Kontrol Testi (NC) gönderiliyor...")
                client.trigger_nozzle_check()
                self.action_complete.emit("Püskürtme kontrol testi deseni yazıcıya gönderildi.")
            elif self.action == "clean_head":
                self.log_msg.emit(f"[KOMUT] {self.ip} -> Standart Kafa Temizleme (CH) başlatılıyor...")
                client.trigger_head_cleaning(power_flush=False)
                self.action_complete.emit("Kafa temizleme döngüsü başlatıldı.")
            elif self.action == "power_flush":
                self.log_msg.emit(f"[KOMUT] {self.ip} -> Güçlü Mürekkep Püskürtme (Power Flush) başlatılıyor...")
                client.trigger_head_cleaning(power_flush=True)
                self.action_complete.emit("Güçlü mürekkep püskürtme (Power Flush) komutu iletildi.")
            elif self.action == "reboot":
                self.log_msg.emit(f"[KOMUT] {self.ip} -> Yazıcı Soft-Reset / Yeniden Başlatma sinyali gönderiliyor...")
                client.send_soft_reset()
                self.action_complete.emit("Yeniden başlatma sinyali iletildi.")
        except Exception as e:
            self.error_occurred.emit(str(e))


# =============================================================================
# Manuel IP Bağlantı Diyaloğu
# =============================================================================

class ManualConnectDialog(QDialog):
    """Kullanıcının özel IP ve Port girmesini sağlayan modern modal pencere."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manuel Yazıcı Bağlantısı")
        self.setFixedSize(380, 200)
        self.setStyleSheet("""
            QDialog {
                background-color: #1b1c22;
                color: #ffffff;
            }
            QLabel {
                color: #cfd3dc;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #24262e;
                border: 1px solid #3d414d;
                border-radius: 6px;
                color: #ffffff;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #00d2ff;
            }
            QPushButton {
                background-color: #00d2ff;
                color: #000000;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #33dcff;
            }
        """)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Yazıcının Statik IP Adresi:"))
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Örn: 192.168.1.150")
        layout.addWidget(self.ip_input)

        layout.addWidget(QLabel("Haberleşme Portu (Varsayılan RAW 9100):"))
        self.port_input = QLineEdit("9100")
        layout.addWidget(self.port_input)

        btn_box = QHBoxLayout()
        self.btn_connect = QPushButton("Bağlan ve Doğrula")
        self.btn_connect.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_connect)

        layout.addLayout(btn_box)

    def get_data(self) -> tuple[str, int]:
        ip = self.ip_input.text().strip()
        try:
            port = int(self.port_input.text().strip())
        except ValueError:
            port = 9100
        return ip, port


# =============================================================================
# Ana Uygulama Penceresi (Main Window)
# =============================================================================

class EpsonResetterMainWindow(QMainWindow):
    """
    Epson WIC Reset ve Ağ Yönetim Konsolu Ana Penceresi.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("EPSON WIC Reset Master - Network Management & Maintenance")
        self.resize(1100, 750)
        self.setMinimumSize(950, 680)

        self.current_device: Optional[PrinterDevice] = None
        self.devices_list: List[PrinterDevice] = []
        self.current_printer_data: Optional[Dict[str, Any]] = None

        self.init_dark_stylesheet()
        self.init_ui()

        # Başlangıçta log ekranına açılış mesajı
        self.append_log("[BAŞLATILDI] EPSON WIC Reset Master - Network Management & Maintenance v2.5")
        self.append_log("[BİLGİ] Ağdaki Epson yazıcılar taranıyor...")

        # 500ms sonra otomatik ağ taramasını başlat
        QTimer.singleShot(500, self.start_network_scan)

    def init_dark_stylesheet(self):
        """Koyu tema CSS stil şablonu."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121316;
            }
            QWidget {
                color: #e1e4ea;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                background-color: #1b1c22;
                border: 1px solid #292b34;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: bold;
                color: #00d2ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLabel {
                font-size: 13px;
            }
            QComboBox {
                background-color: #24262e;
                border: 1px solid #363946;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 24px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QPushButton {
                background-color: #24262e;
                border: 1px solid #363946;
                border-radius: 6px;
                color: #ffffff;
                padding: 7px 14px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #31343f;
                border-color: #00d2ff;
            }
            QPushButton:pressed {
                background-color: #1a1b20;
            }
            QPushButton#btnScan {
                background-color: #0088cc;
                border: none;
                font-weight: bold;
                color: #ffffff;
            }
            QPushButton#btnScan:hover {
                background-color: #00a2f2;
            }
            QPushButton#btnReset {
                background-color: #d32f2f;
                border: none;
                font-size: 15px;
                font-weight: bold;
                color: #ffffff;
                padding: 12px;
                border-radius: 8px;
            }
            QPushButton#btnReset:hover {
                background-color: #f44336;
            }
            QProgressBar {
                background-color: #24262e;
                border: 1px solid #363946;
                border-radius: 6px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #00e676;
                border-radius: 5px;
            }
            QTextEdit {
                background-color: #0c0d10;
                border: 1px solid #24262e;
                border-radius: 6px;
                color: #00ffaa;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
            }
        """)

    def init_ui(self):
        """Arayüz bileşenlerini konumlandırır."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # -------------------------------------------------------------
        # 1. Başlık & Üst Panel (Discovery & Device Selector)
        # -------------------------------------------------------------
        top_box = QGroupBox("Ağ Keşfi ve Cihaz Seçimi")
        top_layout = QHBoxLayout(top_box)

        self.btn_scan = QPushButton("🔍 Ağı Otomatik Tara")
        self.btn_scan.setObjectName("btnScan")
        self.btn_scan.clicked.connect(self.start_network_scan)
        top_layout.addWidget(self.btn_scan)

        self.combo_printers = QComboBox()
        self.combo_printers.setMinimumWidth(380)
        self.combo_printers.addItem("Henüz yazıcı taranmadı...")
        self.combo_printers.currentIndexChanged.connect(self.on_printer_selected)
        top_layout.addWidget(self.combo_printers, stretch=1)

        self.btn_manual = QPushButton("➕ Manuel IP Bağlan")
        self.btn_manual.clicked.connect(self.show_manual_connect_dialog)
        top_layout.addWidget(self.btn_manual)

        self.btn_refresh = QPushButton("🔄 Bilgileri Yenile")
        self.btn_refresh.clicked.connect(self.refresh_current_printer)
        top_layout.addWidget(self.btn_refresh)

        main_layout.addWidget(top_box)

        # Tarama İlerleme Çubuğu (Varsayılan gizli)
        self.scan_progress_bar = QProgressBar()
        self.scan_progress_bar.setVisible(False)
        main_layout.addWidget(self.scan_progress_bar)

        # -------------------------------------------------------------
        # 2. Orta Panel: İki Sütunlu Kartlar (Durum & Ped Sayaçları)
        # -------------------------------------------------------------
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(12)

        # SOL KART: Yazıcı Temel Bilgileri & Tanılama Butonları
        left_card = QGroupBox("Yazıcı Bilgileri ve Bakım Ayarları")
        left_layout = QVBoxLayout(left_card)

        grid_info = QGridLayout()
        grid_info.setVerticalSpacing(8)

        grid_info.addWidget(QLabel("Ağ Tanımı:"), 0, 0)
        self.lbl_model = QLabel("<b>-</b>")
        grid_info.addWidget(self.lbl_model, 0, 1)

        grid_info.addWidget(QLabel("Hedef Model:"), 1, 0)
        self.combo_target_model = QComboBox()
        self.combo_target_model.addItems([
            "L3070 (Önerilen / Varsayılan)", "L3050", "L3060", "L3150", "L3110", "L3250",
            "L380", "L382", "L386", "L395", "L405", "L4150", "L4160",
            "ET-2720", "ET-2800", "ET-4700", "XP-315", "XP-342", "WF-7525"
        ])
        self.combo_target_model.setCurrentIndex(0)
        self.combo_target_model.currentIndexChanged.connect(self.on_target_model_changed)
        grid_info.addWidget(self.combo_target_model, 1, 1)

        grid_info.addWidget(QLabel("Seri No:"), 2, 0)
        self.lbl_serial = QLabel("-")
        grid_info.addWidget(self.lbl_serial, 2, 1)

        grid_info.addWidget(QLabel("Firmware:"), 3, 0)
        self.lbl_firmware = QLabel("-")
        grid_info.addWidget(self.lbl_firmware, 3, 1)

        grid_info.addWidget(QLabel("IP / MAC:"), 4, 0)
        self.lbl_ip_mac = QLabel("-")
        grid_info.addWidget(self.lbl_ip_mac, 4, 1)

        grid_info.addWidget(QLabel("Toplam Baskı:"), 5, 0)
        self.lbl_pages = QLabel("-")
        grid_info.addWidget(self.lbl_pages, 5, 1)

        grid_info.addWidget(QLabel("Durum:"), 6, 0)
        self.lbl_status = QLabel("<span style='color:#00e676;'>Hazır</span>")
        grid_info.addWidget(self.lbl_status, 6, 1)

        left_layout.addLayout(grid_info)
        left_layout.addSpacing(10)

        # Bakım Komut Butonları
        lbl_maint = QLabel("<b>Donanım Tanılama & Bakım Komutları:</b>")
        left_layout.addWidget(lbl_maint)

        btn_grid = QGridLayout()
        btn_grid.setSpacing(8)

        self.btn_nozzle = QPushButton("📄 Püskürtme Kontrol Testi (NC)")
        self.btn_nozzle.clicked.connect(lambda: self.run_maintenance_action("nozzle_check"))
        btn_grid.addWidget(self.btn_nozzle, 0, 0)

        self.btn_clean = QPushButton("🧹 Kafa Temizleme (CH)")
        self.btn_clean.clicked.connect(lambda: self.run_maintenance_action("clean_head"))
        btn_grid.addWidget(self.btn_clean, 0, 1)

        self.btn_power_flush = QPushButton("⚡ Güçlü Mürekkep Püskürtme")
        self.btn_power_flush.clicked.connect(lambda: self.run_maintenance_action("power_flush"))
        btn_grid.addWidget(self.btn_power_flush, 1, 0)

        self.btn_reboot = QPushButton("🔄 Yazıcıyı Yeniden Başlat (Soft Reset)")
        self.btn_reboot.clicked.connect(lambda: self.run_maintenance_action("reboot"))
        btn_grid.addWidget(self.btn_reboot, 1, 1)

        left_layout.addLayout(btn_grid)
        left_layout.addStretch(1)
        middle_layout.addWidget(left_card, stretch=1)

        # SAĞ KART: Atık Mürekkep Pedi (Waste Ink Pad Counter) Göstergeleri
        right_card = QGroupBox("Atık Mürekkep Pedi (Waste Ink Counters) Durumu")
        right_layout = QVBoxLayout(right_card)
        right_layout.setSpacing(12)

        # Ana Ped İlerleme Çubuğu
        right_layout.addWidget(QLabel("<b>Ana Atık Pedi (Main Pad Counter):</b>"))
        self.main_pad_bar = QProgressBar()
        self.main_pad_bar.setRange(0, 100)
        self.main_pad_bar.setValue(0)
        right_layout.addWidget(self.main_pad_bar)

        self.lbl_main_pad_details = QLabel("Sayım: 0 / 6346 puan (%0.0)")
        self.lbl_main_pad_details.setStyleSheet("color: #8f96a3; font-size: 12px;")
        right_layout.addWidget(self.lbl_main_pad_details)

        right_layout.addSpacing(6)

        # Tablo / Kenarsız Pedi İlerleme Çubuğu
        right_layout.addWidget(QLabel("<b>Kenarsız Baskı Tablası Pedi (Platen Pad):</b>"))
        self.platen_pad_bar = QProgressBar()
        self.platen_pad_bar.setRange(0, 100)
        self.platen_pad_bar.setValue(0)
        right_layout.addWidget(self.platen_pad_bar)

        self.lbl_platen_pad_details = QLabel("Sayım: 0 / 3416 puan (%0.0)")
        self.lbl_platen_pad_details.setStyleSheet("color: #8f96a3; font-size: 12px;")
        right_layout.addWidget(self.lbl_platen_pad_details)

        right_layout.addSpacing(10)

        # Kilit & Eşik Uyarı Rozeti
        self.badge_box = QFrame()
        self.badge_box.setStyleSheet("""
            QFrame {
                background-color: #24262e;
                border: 1px solid #363946;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        badge_layout = QVBoxLayout(self.badge_box)
        self.lbl_badge_title = QLabel("Ped Durumu: <span style='color:#00e676;'>GÜVENLİ (%0 - %79)</span>")
        self.lbl_badge_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        badge_layout.addWidget(self.lbl_badge_title)

        self.lbl_badge_desc = QLabel("Yazıcı normal çalışma durumunda. Sayaç sıfırlama yalnızca %100 dolulukta veya ped değişimi sonrasında önerilir.")
        self.lbl_badge_desc.setStyleSheet("color: #a0a6b5; font-size: 12px;")
        self.lbl_badge_desc.setWordWrap(True)
        badge_layout.addWidget(self.lbl_badge_desc)

        right_layout.addWidget(self.badge_box)
        right_layout.addStretch(1)

        middle_layout.addWidget(right_card, stretch=1)
        main_layout.addLayout(middle_layout, stretch=2)

        # -------------------------------------------------------------
        # 3. Alt Panel: Sıfırlama Butonu ve Log Konsolu
        # -------------------------------------------------------------
        bottom_box = QGroupBox("İşlem Konsolu ve Atık Pedi Sıfırlama")
        bottom_layout = QVBoxLayout(bottom_box)
        bottom_layout.setSpacing(10)

        # BÜYÜK SIFIRLAMA BUTONU
        self.btn_reset_counter = QPushButton("🔥 ATIK MÜREKKEP SAYACINI SIFIRLA (WIC RESET) 🔥")
        self.btn_reset_counter.setObjectName("btnReset")
        self.btn_reset_counter.clicked.connect(self.on_reset_counter_clicked)
        bottom_layout.addWidget(self.btn_reset_counter)

        # Konsol Üst Araç Çubuğu
        console_bar = QHBoxLayout()
        console_bar.addWidget(QLabel("<b>Canlı İşlem Logları (Live Socket Console):</b>"))
        console_bar.addStretch(1)

        self.chk_hex = QCheckBox("Ham Bayt / Hex Dökümü Göster")
        console_bar.addWidget(self.chk_hex)

        btn_clear_log = QPushButton("Temizle")
        btn_clear_log.clicked.connect(lambda: self.log_console.clear())
        console_bar.addWidget(btn_clear_log)

        bottom_layout.addLayout(console_bar)

        # Log Konsol Penceresi
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(140)
        bottom_layout.addWidget(self.log_console)

        main_layout.addWidget(bottom_box, stretch=2)

    # -------------------------------------------------------------------------
    # Loglama Yardımcısı
    # -------------------------------------------------------------------------
    def append_log(self, text: str):
        """Zaman damgalı log satırı ekler."""
        now = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{now}] {text}"
        self.log_console.append(formatted)
        self.log_console.moveCursor(QTextCursor.MoveOperation.End)

    # -------------------------------------------------------------------------
    # Ağ Tarama Eylemleri
    # -------------------------------------------------------------------------
    def start_network_scan(self):
        """Alt ağ taramasını tetikler."""
        self.btn_scan.setEnabled(False)
        self.scan_progress_bar.setVisible(True)
        self.scan_progress_bar.setValue(0)
        self.append_log("[BAŞLADI] Yerel ağda Epson yazıcı araması başlatıldı...")

        self.scan_worker = DiscoveryWorker()
        self.scan_worker.progress.connect(self.on_scan_progress)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.log_msg.connect(self.append_log)
        self.scan_worker.start()

    def on_scan_progress(self, percent: int, text: str):
        self.scan_progress_bar.setValue(percent)

    def on_scan_finished(self, devices: List[PrinterDevice]):
        self.btn_scan.setEnabled(True)
        self.scan_progress_bar.setVisible(False)
        self.devices_list = devices

        self.combo_printers.blockSignals(True)
        self.combo_printers.clear()

        if not devices:
            self.combo_printers.addItem("Epson yazıcı bulunamadı. Manuel IP deneyin.")
            self.append_log("[UYARI] Ağda otomatik yanıt veren Epson yazıcı bulunamadı.")
        else:
            for dev in devices:
                self.combo_printers.addItem(dev.display_name(), dev)
            self.append_log(f"[TAMAMLANDI] Toplam {len(devices)} adet Epson yazıcı tespit edildi.")
            self.current_device = devices[0]
            self.combo_printers.blockSignals(False)
            self.query_printer_details(devices[0])

        self.combo_printers.blockSignals(False)

    def on_printer_selected(self, index: int):
        if index >= 0 and index < len(self.devices_list):
            dev = self.devices_list[index]
            self.current_device = dev
            self.query_printer_details(dev)

    def show_manual_connect_dialog(self):
        """Statik IP giriş modalını açar."""
        dlg = ManualConnectDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ip, port = dlg.get_data()
            if ip:
                self.append_log(f"[MANUEL BAĞLANTI] {ip}:{port} hedefine doğrudan bağlanılıyor...")
                dev = PrinterDevice(ip=ip, port=port, model="Epson (Statik IP)", discovery_source="Manuel")
                self.devices_list.append(dev)
                self.combo_printers.blockSignals(True)
                self.combo_printers.addItem(dev.display_name(), dev)
                self.combo_printers.setCurrentIndex(self.combo_printers.count() - 1)
                self.combo_printers.blockSignals(False)
                self.current_device = dev
                self.query_printer_details(dev)

    def refresh_current_printer(self):
        if self.current_device:
            self.query_printer_details(self.current_device)
        else:
            self.append_log("[UYARI] Yenilenecek yazıcı seçilmedi.")

    # -------------------------------------------------------------------------
    # Yazıcı Detaylarını ve Sayaçlarını Sorgulama
    # -------------------------------------------------------------------------
    def query_printer_details(self, device: PrinterDevice):
        """Seçili yazıcının EEPROM sayaçlarını ve HTTP durumunu sorgular."""
        self.lbl_status.setText("<span style='color:#00d2ff;'>Sorgulanıyor...</span>")
        raw_choice = self.combo_target_model.currentText()
        preferred = raw_choice.split()[0] if " " in raw_choice else raw_choice
        self.query_worker = PrinterQueryWorker(device, preferred_model=preferred)
        self.query_worker.data_ready.connect(self.on_printer_data_ready)
        self.query_worker.error_occurred.connect(self.on_printer_query_error)
        self.query_worker.log_msg.connect(self.append_log)
        self.query_worker.start()

    def on_target_model_changed(self, text: str):
        """Kullanıcı hedef modeli değiştirdiğinde EEPROM sayaçlarını bu modele göre yeniler."""
        if self.current_device:
            raw = text.split()[0]
            self.append_log(f"[MODEL SEÇİMİ] Hedef model profili '{raw}' olarak seçildi. Sayaçlar güncelleniyor...")
            # Sinyal döngüsünü engellemek için doğrudan worker çağır
            self.query_worker = PrinterQueryWorker(self.current_device, preferred_model=raw)
            self.query_worker.data_ready.connect(self.on_printer_data_ready)
            self.query_worker.error_occurred.connect(self.on_printer_query_error)
            self.query_worker.log_msg.connect(self.append_log)
            self.query_worker.start()

    def on_printer_data_ready(self, data: Dict[str, Any]):
        self.current_printer_data = data
        self.lbl_model.setText(f"<b>{data['model']}</b>")
        self.lbl_serial.setText(data['serial'])
        self.lbl_firmware.setText(data['firmware'])
        self.lbl_ip_mac.setText(f"{data['ip']} / {data['mac']}")
        self.lbl_pages.setText(f"{data['page_count']} sayfa")
        self.lbl_status.setText(f"<span style='color:#00e676;'>{data['status_text']}</span>")

        # Sayaçları Arayüze Yansıt
        counters = data.get("counters", {})
        main_pad = counters.get("main_pad", {})
        platen_pad = counters.get("platen_pad", {})

        # Ana Ped Çubuğu
        main_pct = int(main_pad.get("percent", 0.0))
        self.main_pad_bar.setValue(main_pct)
        self.lbl_main_pad_details.setText(
            f"Sayım: {main_pad.get('ticks', 0)} / {main_pad.get('max_ticks', 6346)} puan (%{main_pad.get('percent', 0.0)})"
        )
        self.set_progress_color(self.main_pad_bar, main_pct)

        # Tablo Pedi Çubuğu
        if platen_pad.get("available", False):
            platen_pct = int(platen_pad.get("percent", 0.0))
            self.platen_pad_bar.setValue(platen_pct)
            self.lbl_platen_pad_details.setText(
                f"Sayım: {platen_pad.get('ticks', 0)} / {platen_pad.get('max_ticks', 3416)} puan (%{platen_pad.get('percent', 0.0)})"
            )
            self.set_progress_color(self.platen_pad_bar, platen_pct)
        else:
            self.platen_pad_bar.setValue(0)
            self.lbl_platen_pad_details.setText("Bu modelde ikincil tablo pedi mevcut değil.")

        # Rozet Güncellemesi
        level = counters.get("level", "OK")
        if level == "CRITICAL":
            self.lbl_badge_title.setText("Ped Durumu: <span style='color:#ff1744;'>BLOKE (%100 - SERVİS GEREKLİ)</span>")
            self.lbl_badge_desc.setText("DİKKAT: Atık mürekkep pedi tamamen doldu ve yazıcı kendini kilitledi. Yazıcıyı tekrar açmak için sıfırlama zorunludur.")
        elif level == "WARNING":
            self.lbl_badge_title.setText("Ped Durumu: <span style='color:#ffb300;'>UYARI (YAKINDA DOLACAK)</span>")
            self.lbl_badge_desc.setText("Atık ped kapasitesi %80'in üzerine çıktı. Yakında yazıcı kilitlenebilir.")
        else:
            self.lbl_badge_title.setText("Ped Durumu: <span style='color:#00e676;'>GÜVENLİ (SORUNSUZ)</span>")
            self.lbl_badge_desc.setText("Yazıcı normal çalışma durumunda. Ped seviyesi kabul edilebilir sınırda.")

        self.append_log(f"[GÜNCELLENDİ] {data['model']} verileri ve EEPROM sayaçları başarıyla yüklendi.")

    def on_printer_query_error(self, err: str):
        self.lbl_status.setText(f"<span style='color:#ff1744;'>Hata</span>")
        self.append_log(f"[HATA] Cihaz sorgusu başarısız: {err}")

    def set_progress_color(self, bar: QProgressBar, percent: int):
        """Doluluk oranına göre dinamik renk atar (Yeşil -> Sarı -> Kırmızı)."""
        if percent >= 100:
            color = "#ff1744"  # Kırmızı (Bloke)
        elif percent >= 80:
            color = "#ffb300"  # Sarı/Turuncu (Uyarı)
        else:
            color = "#00e676"  # Yeşil (Normal)
        bar.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 5px;
            }}
        """)

    # -------------------------------------------------------------------------
    # Bakım Eylemleri Tetikleme
    # -------------------------------------------------------------------------
    def run_maintenance_action(self, action_name: str):
        if not self.current_device:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce bir yazıcı seçin!")
            return

        # Power Flush için ekstra onay
        if action_name == "power_flush":
            reply = QMessageBox.question(
                self,
                "Güçlü Temizleme Onayı",
                "Güçlü Mürekkep Püskürtme (Power Flush) yüksek miktarda mürekkep harcar ve atık pedi doldurur.\nDevam etmek istiyor musunuz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.maint_worker = MaintenanceWorker(
            ip=self.current_device.ip,
            port=self.current_device.port,
            action=action_name
        )
        self.maint_worker.log_msg.connect(self.append_log)
        self.maint_worker.action_complete.connect(lambda msg: QMessageBox.information(self, "Bilgi", msg))
        self.maint_worker.error_occurred.connect(lambda err: QMessageBox.critical(self, "Hata", err))
        self.maint_worker.start()

    # -------------------------------------------------------------------------
    # Atık Mürekkep Sayacını Sıfırlama (WIC Reset)
    # -------------------------------------------------------------------------
    def on_reset_counter_clicked(self):
        if not self.current_device or not self.current_printer_data:
            QMessageBox.warning(self, "Yazıcı Seçilmedi", "Lütfen önce ağdan bir Epson yazıcı seçin veya manuel IP girin.")
            return

        raw_text = self.combo_target_model.currentText()
        model = raw_text.split()[0] if " " in raw_text else raw_text
        ip = self.current_device.ip

        # Güvenlik Onay Diyaloğu
        confirm = QMessageBox.warning(
            self,
            "Atık Mürekkep Sayacını Sıfırla (WIC Reset)",
            f"Hedef Yazıcı: {model} ({ip})\n\n"
            "DİKKAT:\n"
            "1. Bu işlem EEPROM sayaç adreslerine sıfırlama (00 00) baytlarını yazacak.\n"
            "2. EEPROM Checksum yeniden hesaplanacak ve yazıcı yeniden başlatılacaktır.\n"
            "3. Lütfen işlem sırasında yazıcının fişini veya ağ bağlantısını kesmeyin!\n\n"
            "Sayaçları şimdi sıfırlamak istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            self.append_log("[İPTAL] Kullanıcı tarafından sayaç sıfırlama işlemi iptal edildi.")
            return

        self.btn_reset_counter.setEnabled(False)
        self.append_log(f"[İŞLEM] {model} için Atık Mürekkep Pedi Sıfırlama döngüsü başlatıldı...")

        self.reset_worker = ResetCounterWorker(ip=ip, port=self.current_device.port, model=model)
        self.reset_worker.log_stream.connect(self.append_log)
        self.reset_worker.reset_complete.connect(self.on_reset_completed)
        self.reset_worker.error_occurred.connect(self.on_reset_failed)
        self.reset_worker.start()

    def on_reset_completed(self, result: Dict[str, Any]):
        self.btn_reset_counter.setEnabled(True)
        if result.get("success", False):
            QMessageBox.information(
                self,
                "Sıfırlama Başarılı!",
                f"Tebrikler!\n\n{result.get('model')} Atık Mürekkep Pedi sayaçları başarıyla %0 seviyesine sıfırlandı.\n\n"
                "ÖNEMLİ:\n"
                "Yeni sıfırlama değerlerinin yazıcı anakartında kalıcı olarak devreye girmesi için:\n"
                "Lütfen yazıcınızı Açma/Kapama (Power) düğmesinden kapatıp 5 saniye bekleyin, ardından tekrar açın (Restart)!"
            )
            self.refresh_current_printer()
        else:
            QMessageBox.warning(
                self,
                "Doğrulama Uyarısı",
                "Sıfırlama paketi gönderildi ancak sayaç beklenen oranda sıfırlanamadı.\n"
                "Lütfen yazıcıyı kapatıp açtıktan sonra [Yenile / Oku] butonuna tıklayarak tekrar kontrol edin."
            )

    def on_reset_failed(self, error_str: str):
        self.btn_reset_counter.setEnabled(True)
        QMessageBox.critical(self, "Sıfırlama Hatası", f"Sıfırlama sırasında kritik hata oluştu:\n{error_str}")
        self.append_log(f"[KRİTİK HATA] Sıfırlama motoru başarısız: {error_str}")


def run_gui():
    """PyQt6 GUI uygulamasını başlatır."""
    app = QApplication(sys.argv)
    window = EpsonResetterMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
