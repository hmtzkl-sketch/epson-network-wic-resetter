"""
epson_models.py - Epson Yazıcı Model Veritabanı ve EEPROM Haritaları
Bu modül, Epson EcoTank (L ve ET serisi), Expression (XP serisi) ve WorkForce (WF serisi)
yazıcıların EEPROM ofsetlerini, kimlik doğrulama anahtarlarını, atık pedi bölenlerini
ve bakım eşiklerini içerir.
"""

from typing import Dict, Any, Optional

# Epson Model Tanımları ve EEPROM Sayaç Konfigürasyonları
# divider: Sayaç ham değerini yüzdeye çeviren katsayı (Ham Değer / divider = Yüzde %)
# read_key / write_key: SNMP / BDC bakım modu NVRAM kilit açma anahtarları
# oids / offsets: EEPROM bellek ofsetleri
EPSON_MODEL_DATABASE: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------
    # EcoTank L Serisi (En Yaygın Modeller)
    # -------------------------------------------------------------
    "L110": {
        "series": "EcoTank L",
        "alias": ["L100", "L120", "L130"],
        "read_key": [16, 8],
        "write_key": b"Sinabung",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.07, "max_ticks": 6207},
        "borderless_waste": None,
        "reset_payload": {24: 0, 25: 0, 30: 0, 28: 0, 29: 0, 46: 94},
        "page_counter_offsets": [167, 166, 165, 164],
        "head_clean_counter_offset": [147],
    },
    "L210": {
        "series": "EcoTank L",
        "alias": ["L200", "L220"],
        "read_key": [16, 8],
        "write_key": b"Sinabung",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.07, "max_ticks": 6207},
        "borderless_waste": None,
        "reset_payload": {24: 0, 25: 0, 30: 0, 28: 0, 29: 0, 46: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L300": {
        "series": "EcoTank L",
        "alias": ["L310"],
        "read_key": [16, 8],
        "write_key": b"Sinabung",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.07, "max_ticks": 6207},
        "borderless_waste": None,
        "reset_payload": {24: 0, 25: 0, 30: 0, 28: 0, 29: 0, 46: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L350": {
        "series": "EcoTank L",
        "alias": ["L351"],
        "read_key": [65, 9],
        "write_key": b"Wakatobi",
        "main_waste": {"offsets": [24, 25, 30], "divider": 65.00, "max_ticks": 6500},
        "borderless_waste": None,
        "reset_payload": {24: 0, 25: 0, 30: 0, 28: 0, 29: 0, 46: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L355": {
        "series": "EcoTank L",
        "alias": ["L358", "L365"],
        "read_key": [65, 9],
        "write_key": b"Wakatobi",
        "main_waste": {"offsets": [24, 25, 30], "divider": 65.00, "max_ticks": 6500},
        "borderless_waste": None,
        "reset_payload": {24: 0, 25: 0, 30: 0, 28: 0, 29: 0, 46: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L365": {
        "series": "EcoTank L",
        "alias": ["L360", "L362", "L366"],
        "read_key": [130, 2],
        "write_key": b"Gerbera*",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.07, "max_ticks": 6207},
        "borderless_waste": {"offsets": [26, 27, 34], "divider": 24.20, "max_ticks": 2420},
        "reset_payload": {24: 0, 25: 0, 30: 0, 26: 0, 27: 0, 34: 0, 28: 0, 29: 0, 46: 94, 47: 94, 49: 0},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L380": {
        "series": "EcoTank L",
        "alias": ["L382", "L383", "L385", "L386"],
        "read_key": [16, 8],
        "write_key": b"Sinabung",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.07, "max_ticks": 6207},
        "borderless_waste": {"offsets": [26, 27, 34], "divider": 24.20, "max_ticks": 2420},
        "reset_payload": {24: 0, 25: 0, 30: 0, 26: 0, 27: 0, 34: 0, 28: 0, 29: 0, 46: 94, 47: 94, 49: 0},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L395": {
        "series": "EcoTank L",
        "alias": ["L396"],
        "read_key": [16, 8],
        "write_key": b"Sinabung",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.06, "max_ticks": 6206},
        "borderless_waste": None,
        "reset_payload": {24: 0, 25: 0, 30: 0, 28: 0, 29: 0, 46: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L405": {
        "series": "EcoTank L",
        "alias": ["L455", "L486"],
        "read_key": [149, 3],
        "write_key": b"Maninjau",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.07, "max_ticks": 6207},
        "borderless_waste": None,
        "reset_payload": {24: 0, 25: 0, 30: 0, 28: 0, 29: 0, 46: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L3070": {
        "series": "EcoTank L",
        "alias": ["L3050", "L3060", "BUILT-IN", "EPSON BUILT-IN", "PRINT SERVER"],
        "read_key": [149, 3],
        "write_key": b"Maninjau",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.07, "max_ticks": 6207},
        "borderless_waste": {"offsets": [26, 27, 34], "divider": 24.20, "max_ticks": 2420},
        "reset_payload": {24: 0, 25: 0, 30: 0, 26: 0, 27: 0, 34: 0, 28: 0, 29: 0, 46: 94, 47: 94, 49: 0},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "L3110": {
        "series": "EcoTank L (Gen 2)",
        "alias": ["L1110", "L3100"],
        "read_key": [151, 7],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },
    "L3150": {
        "series": "EcoTank L (Gen 2)",
        "alias": ["L3151", "L3152", "L3156", "L3158", "L3160", "L3166", "L3168"],
        "read_key": [151, 7],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },
    "L3250": {
        "series": "EcoTank L (Gen 3)",
        "alias": ["L3210", "L3251", "L3256", "L3260"],
        "read_key": [74, 54],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },
    "L4150": {
        "series": "EcoTank L (Gen 2)",
        "alias": ["L4156", "L4158", "L4160", "L4166", "L4168"],
        "read_key": [73, 8],
        "write_key": b"Arantifo",
        "main_waste": {"offsets": [48, 49, 47], "divider": 109.13, "max_ticks": 10913},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 16.31, "max_ticks": 1631},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [755, 754, 753, 752],
    },
    "L5190": {
        "series": "EcoTank L (Gen 2)",
        "alias": ["L5196", "L6160", "L6170", "L6190"],
        "read_key": [151, 7],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },
    "L800": {
        "series": "Photo L",
        "alias": ["L801", "L805", "L810", "L850", "L1800"],
        "read_key": [16, 8],
        "write_key": b"Sinabung",
        "main_waste": {"offsets": [24, 25, 30], "divider": 84.50, "max_ticks": 8450},
        "borderless_waste": {"offsets": [26, 27, 34], "divider": 29.03, "max_ticks": 2903},
        "reset_payload": {24: 0, 25: 0, 30: 0, 26: 0, 27: 0, 34: 0, 28: 0, 29: 0, 46: 94, 47: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },

    # -------------------------------------------------------------
    # EcoTank ET Serisi (Avrupa / Amerika Pazarı)
    # -------------------------------------------------------------
    "ET-2400": {
        "series": "EcoTank ET",
        "alias": ["ET-2401", "ET-2403", "ET-2405"],
        "read_key": [74, 54],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },
    "ET-2600": {
        "series": "EcoTank ET",
        "alias": ["ET-2650"],
        "read_key": [16, 8],
        "write_key": b"Sinabung",
        "main_waste": {"offsets": [24, 25, 30], "divider": 62.06, "max_ticks": 6206},
        "borderless_waste": None,
        "reset_payload": {24: 0, 25: 0, 30: 0, 28: 0, 29: 0, 46: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "ET-2720": {
        "series": "EcoTank ET",
        "alias": ["ET-2700", "ET-2710", "ET-2711", "ET-2712", "ET-2714", "ET-2715", "ET-2721", "ET-2726"],
        "read_key": [151, 7],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },
    "ET-2750": {
        "series": "EcoTank ET",
        "alias": ["ET-2751", "ET-2756", "ET-2760"],
        "read_key": [73, 8],
        "write_key": b"Arantifo",
        "main_waste": {"offsets": [48, 49, 47], "divider": 109.13, "max_ticks": 10913},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 16.31, "max_ticks": 1631},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [755, 754, 753, 752],
    },
    "ET-2800": {
        "series": "EcoTank ET",
        "alias": ["ET-2803", "ET-2810", "ET-2811", "ET-2812", "ET-2814", "ET-2815", "ET-2820"],
        "read_key": [74, 54],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },
    "ET-4700": {
        "series": "EcoTank ET",
        "alias": ["ET-4750", "ET-4760"],
        "read_key": [151, 7],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },
    "ET-4800": {
        "series": "EcoTank ET",
        "alias": ["ET-4810", "ET-4850"],
        "read_key": [74, 54],
        "write_key": b"Maribaya",
        "main_waste": {"offsets": [48, 49, 47], "divider": 63.46, "max_ticks": 6346},
        "borderless_waste": {"offsets": [50, 51, 47], "divider": 34.16, "max_ticks": 3416},
        "reset_payload": {48: 0, 49: 0, 47: 0, 50: 0, 51: 0, 52: 0, 53: 0, 54: 94, 55: 94, 28: 0},
        "page_counter_offsets": [776, 775, 774, 773],
    },

    # -------------------------------------------------------------
    # Expression Home XP Serisi
    # -------------------------------------------------------------
    "XP-205": {
        "series": "Expression",
        "alias": ["XP-200", "XP-207", "XP-215", "XP-225"],
        "read_key": [25, 7],
        "write_key": b"Wakatobi",
        "main_waste": {"offsets": [24, 25, 30], "divider": 73.50, "max_ticks": 7350},
        "borderless_waste": {"offsets": [26, 27, 34], "divider": 34.34, "max_ticks": 3434},
        "reset_payload": {24: 0, 25: 0, 30: 0, 26: 0, 27: 0, 34: 0, 46: 94, 47: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "XP-315": {
        "series": "Expression",
        "alias": ["XP-312", "XP-313", "XP-320", "XP-322"],
        "read_key": [129, 8],
        "write_key": b"Wakatobi",
        "main_waste": {"offsets": [24, 25], "divider": 69.00, "max_ticks": 6900},
        "borderless_waste": {"offsets": [26, 27], "divider": 32.53, "max_ticks": 3253},
        "reset_payload": {24: 0, 25: 0, 26: 0, 27: 0, 30: 0, 34: 0, 46: 94, 47: 94},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "XP-342": {
        "series": "Expression",
        "alias": ["XP-343", "XP-345", "XP-442", "XP-445"],
        "read_key": [1, 5],
        "write_key": b"Suramadu",
        "main_waste": {"offsets": [24, 25, 30], "divider": 39.90, "max_ticks": 3990},
        "borderless_waste": {"offsets": [26, 27, 34], "divider": 32.55, "max_ticks": 3255},
        "reset_payload": {24: 0, 25: 0, 30: 0, 26: 0, 27: 0, 34: 0, 46: 94, 47: 94, 49: 0},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "XP-422": {
        "series": "Expression",
        "alias": ["XP-423", "XP-425"],
        "read_key": [85, 5],
        "write_key": b"Muscari.",
        "main_waste": {"offsets": [24, 25, 30], "divider": 196.50, "max_ticks": 19650},
        "borderless_waste": {"offsets": [26, 27, 34], "divider": 52.05, "max_ticks": 5205},
        "reset_payload": {24: 0, 25: 0, 26: 0, 27: 0, 30: 0, 34: 0, 46: 94, 47: 94, 49: 0},
        "page_counter_offsets": [167, 166, 165, 164],
    },
    "XP-610": {
        "series": "Expression Premium",
        "alias": ["XP-611", "XP-615", "XP-620", "XP-625", "XP-700", "XP-800"],
        "read_key": [121, 4],
        "write_key": b"Gossypiu",
        "main_waste": {"offsets": [16, 17, 6], "divider": 84.50, "max_ticks": 8450},
        "borderless_waste": {"offsets": [18, 19, 6], "divider": 29.03, "max_ticks": 2903},
        "reset_payload": {16: 0, 17: 0, 6: 0, 18: 0, 19: 0, 52: 94, 53: 94, 493: 0},
        "page_counter_offsets": [99, 98, 97, 96],
    },
    "WF-7525": {
        "series": "WorkForce",
        "alias": ["WF-7515", "WF-7015"],
        "read_key": [101, 0],
        "write_key": b"Sasanqua",
        "main_waste": {"offsets": [20, 21, 59], "divider": 196.50, "max_ticks": 19650},
        "borderless_waste": {"offsets": [22, 23, 59], "divider": 52.05, "max_ticks": 5205},
        "reset_payload": {20: 0, 21: 0, 22: 0, 23: 0, 24: 0, 25: 0, 59: 0, 60: 94, 61: 94},
        "page_counter_offsets": [147, 146, 145, 144],
    },
}


def find_model_config(model_name: str) -> Optional[Dict[str, Any]]:
    """
    Girilen model adı veya tam cihaz dizesine (ör. 'EPSON L3150 Series')
    en uygun model yapılandırmasını döndürür.
    Büyük/küçük harf duyarsızdır ve alias listesini de denetler.
    """
    if not model_name:
        return None
    
    clean_name = model_name.upper().strip()
    
    # 1. Doğrudan eşleşme kontrolü
    for key, conf in EPSON_MODEL_DATABASE.items():
        if key.upper() in clean_name or clean_name in key.upper():
            return {"canonical_model": key, **conf}
            
    # 2. Alias kontrolü
    for key, conf in EPSON_MODEL_DATABASE.items():
        aliases = conf.get("alias", [])
        for alias in aliases:
            if alias.upper() in clean_name or clean_name in alias.upper():
                return {"canonical_model": key, **conf}

    # 3. Generic print server veya "BUILT-IN" tespit edilirse L3070 ata
    if "BUILT-IN" in clean_name or "PRINT SERVER" in clean_name or "PRINTSERVER" in clean_name:
        return {"canonical_model": "L3070", **EPSON_MODEL_DATABASE["L3070"]}

    # 4. Genel EcoTank / L serisi fallback (Standard L-Class 24/25 offset)
    if "L31" in clean_name or "L32" in clean_name or "ET-2" in clean_name:
        return {"canonical_model": "L3150", **EPSON_MODEL_DATABASE["L3150"]}
    elif "L3" in clean_name or "L2" in clean_name or "L1" in clean_name:
        return {"canonical_model": "L380", **EPSON_MODEL_DATABASE["L380"]}
        
    # Varsayılan L3070 fallback
    return {"canonical_model": "L3070", **EPSON_MODEL_DATABASE["L3070"]}
