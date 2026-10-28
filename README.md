# Speed Monitor (Desktop)

Aplikasi desktop PyQt untuk memonitor koneksi internet secara lokal. Data disimpan di SQLite. Jika dikonfigurasi, data disinkronkan bertahap ke Firebase Firestore.

## Fitur

- Ping ke host utama (default 8.8.8.8), fallback ke 8.8.4.4 dengan delay 10 detik.
- Speedtest berkala (default 1 jam) menggunakan `speedtest-cli`.
- Identifikasi lokasi dan nama jaringan.
- Sinkronisasi otomatis ke Firebase Firestore (opsional).
- Dashboard desktop: status, statistik, riwayat, export CSV.

## Instalasi & Jalankan

### Windows

Double-click file `run_desktop.bat`, atau jalankan dari Command Prompt:

```cmd
run_desktop.bat
```

### Linux

```bash
chmod +x run_desktop.sh
./run_desktop.sh
```

### Setup Pertama Kali

Saat pertama kali, wizard setup muncul. Isi:
- Network / ISP Name
- Location
- Interval speedtest
- Ping host & fallback host
- Firebase config (opsional)

## Test

```bash
.venv/Scripts/python -m pytest tests/ -q      # Windows
.venv/bin/python -m pytest tests/ -q          # Linux
```

## Struktur

- `desktop.py` — aplikasi utama PyQt.
- `setup_wizard.py` — wizard konfigurasi pertama kali.
- `cloud_sync.py` — sinkronisasi ke Firebase Firestore.
- `monitor.py`, `checker.py`, `speedtester.py` — monitoring inti.
- `config.py`, `db.py` — konfigurasi dan database lokal.
