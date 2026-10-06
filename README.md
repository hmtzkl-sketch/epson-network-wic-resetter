# Epson Network WIC Resetter & Management Tool (Open-Source)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

> **Free, open-source network management and Waste Ink Pad counter reset tool for Epson EcoTank / L-Series / ET-Series printers over Wi-Fi and LAN.**  
> No paid reset keys (WIC Reset / INKCHIP / 2Manuals), no shady Russian/Indonesian cracks, and no USB cable required.

---

## 🌟 Overview / Genel Bakış

Epson EcoTank and inkjet printers automatically lock themselves with a service error (e.g. *"A printer's ink pad is at the end of its service life"*, Service Code `000041` / `000043` / `0x9A`) when the internal waste ink counter reaches 100%.

Traditionally, users are forced to pay **$10–$15 per reset key** through proprietary closed-source utilities (WIC Reset, INKCHIP), or download suspicious "Adjustment Program" (AdjProg) cracks that only work via USB cable and are often plagued with malware.

**Epson Network WIC Resetter** solves this by communicating directly with the printer over the local network (**Wi-Fi / Ethernet LAN**) using pure Python socket protocols, allowing you to read live EEPROM counters and reset waste ink pads to **0%** completely free.

---

## 🔬 Reverse-Engineering Breakthrough / Teknik Çözüm

Epson disables standard network raw printing ports (TCP 9100) and ESC/P-R commands when it comes to low-level EEPROM service operations. This project unlocks the network service layer by reverse-engineering Epson's proprietary **IONET Protocol**:

1. **SNMP OID Command Tunneling (UDP Port 161):**
   Service commands and memory operations are transmitted using SNMP `GetRequest` (0xA0) with community `"public"`. Raw command bytes are encoded directly into the sub-identifiers of Epson's private enterprise OID:
   ```
   1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1.<byte0>.<byte1>...<byteN>
   ```
   The printer responds with execution output encapsulated within an ASN.1 `OCTET STRING`.

2. **Master Authentication Challenge (`Tjobcvoh`):**
   Epson blocks unauthorized EEPROM write attempts. To unlock memory write access, packets must contain the master key `Tjobcvoh` *(a ROT-1 Caesar cipher for Epson's internal project codename "Sinbaung")*.

3. **EEPROM Memory Verification & Checksum:**
   Counters (Main Pad, Platen Pad) are read and written at model-specific hex offsets (e.g. `0x18`, `0x19`, `0x1E`, `0x1C`, `0x1D`). After writing zeroes (`0x00`), the 8-bit inverted sum checksum is calculated:
   $$\text{Checksum} = (0\text{x}100 - (\sum \text{Bytes} \ \& \ 0\text{xFF})) \ \& \ 0\text{xFF}$$

---

## ✨ Features / Özellikler

- 🔍 **Automatic Subnet Discovery:** Scans the local network for Epson printers using UDP 161 SNMP probes, mDNS (`_printer._tcp`, `_ipp._tcp`), and MAC OUI vendor filtering (`00:00:48`, `00:21:54`, `00:26:AB`, etc.).
- 🎯 **Manual IP Connection:** Connect directly to any printer via static IP.
- 📊 **Real-Time Live Counter Reading:** Displays exact tick counts and percentage progress bars for:
  - **Main Waste Ink Pad (Ana Atık Pedi)**
  - **Platen / Borderless Waste Ink Pad (Baskı Tablası Pedi)**
- 🧹 **1-Click Waste Ink Counter Reset (WIC Reset):** Flashes counters back to 0.00% without one-time keys or license codes.
- 🧰 **Printer Diagnostics & Maintenance:**
  - Standard Printhead Cleaning (Kafa Temizleme)
  - Deep / Power Ink Flushing (Güçlü Mürekkep Boşaltma)
  - Nozzle Check Test Pattern (Püskürtme Kontrol Deseni Bastırma)
  - Remote Soft Reboot / Power Cycle
- 🖥️ **Modern Dark-Mode GUI:** Built with PyQt6, featuring non-blocking background threads (`QThread`), real-time socket packet inspection, and visual percentage indicators.
- ⚡ **Full CLI Support:** Terminal automation and headless scripting flags.

---

## 🖨️ Supported Models / Desteklenen Modeller

Tested and verified on:
- **Epson L-Series (EcoTank):** L3050, L3060, L3070, L3110, L3150, L3151, L3156, L3160, L380, L382, L386, L4150, L4160, L5190, L6160, L6170, L6190, L1110, L1210, L3210, L3250, L3251, L3256, etc.
- **Epson ET-Series (EcoTank):** ET-2600, ET-2650, ET-2700, ET-2710, ET-2720, ET-2750, ET-2800, ET-2810, ET-2820, ET-2850, ET-3700, ET-3750, ET-4700, etc.
- **Epson XP-Series / WF-Series:** XP-2100, XP-3100, XP-4100, WF-2810, WF-2830, etc.

*(Additional models can be added by declaring their EEPROM offsets in `epson_models.py`)*

---

## 🚀 Installation & Usage / Kurulum ve Kullanım

### 1. Requirements / Gereksinimler
- Python 3.10 or higher
- Windows, macOS, or Linux connected to the same Wi-Fi/LAN as the printer.

```bash
git clone https://github.com/hmtzkl-sketch/epson-network-wic-resetter.git
cd epson-network-wic-resetter
pip install -r requirements.txt
```

### 2. Graphical Interface (GUI)
Launch the dark-mode desktop application:
```bash
python main.py
```
1. Click **[Ağı Tara (Scan Network)]** or enter your printer's IP address.
2. Watch live counter percentages update automatically.
3. Click **[Atık Mürekkep Sayacını Sıfırla (Reset Waste Ink Counter)]**.
4. Power-cycle the printer (turn off with power button, wait 5 seconds, turn back on).

### 3. Command Line Automation (CLI)
Automate or manage printers remotely without a GUI:

```bash
# Scan local subnet for Epson printers
python main.py --scan

# Read printer info, serial number, and live waste ink counters
python main.py --ip 192.168.1.104 --info

# Reset waste ink counter to 0%
python main.py --ip 192.168.1.104 --model L3070 --reset

# Run printhead nozzle check test page
python main.py --ip 192.168.1.104 --nozzle

# Trigger standard printhead cleaning
python main.py --ip 192.168.1.104 --clean

# Soft-reboot the printer
python main.py --ip 192.168.1.104 --reboot
```

### 4. Compiling Standalone Windows Executable (.exe)
To compile a single portable `.exe` file without needing Python installed on the target machine:
```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name="Epson_Network_WIC_Resetter" main.py
```
The executable will be generated in the `dist/` directory.

---

## 🧪 Unit Tests / Testler

Run the built-in test suite to verify ASN.1 BER encoding, SNMP packet structures, model mapping, and checksum mathematics:
```bash
python test_resetter.py
```

---

## ⚠️ Important Physical Maintenance Notice / Fiziksel Ped Uyarısı

> **Note:** Resetting the counter electronically clears the software lockout and allows printing to resume immediately. However, the **physical waste ink pads (sponges) inside the printer continue to collect ink**.
>
> If you have printed thousands of pages or perform frequent head cleanings, ensure you:
> 1. Unscrew the waste ink box on the back/bottom of your printer.
> 2. Wash and thoroughly dry the felt pads, replace them with new sponge pads, OR
> 3. Route a silicone waste ink drainage tube to an external waste ink bottle.

---

## 📄 License / Lisans

Distributed under the **MIT License**. See `LICENSE` for more information.

---

## 💡 Contributing / Katkıda Bulunma

Pull requests and model profile additions are welcome! If you have offset mappings for other Epson models, please feel free to submit a PR or open an issue.

---

## ⚖️ Legal Disclaimer / Yasal Uyarı & Sorumluluk Reddi

- **Trademarks:** All product names, logos, trademarks, and registered trademarks (including "EPSON", "EcoTank", etc.) are property of their respective owners (Seiko Epson Corporation). Their use in this project is strictly for identification, compatibility, and interoperability purposes under fair use policies.
- **Affiliation:** This project is an independent open-source research and maintenance initiative. It is not affiliated with, endorsed by, sponsored by, or associated in any way with Seiko Epson Corporation, 2Manuals, or WIC Reset.
- **Warranty:** This software is distributed under the MIT License on an "AS-IS" basis without warranties of any kind. Users are responsible for the physical maintenance (sponge/pad cleaning) of their devices.

