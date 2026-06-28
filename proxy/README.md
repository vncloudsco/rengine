# Urban Proxy Module cho reNgine

Module plug-and-play tích hợp **Urban VPN free proxy** vào [reNgine](https://github.com/yogeshojha/rengine) mà **không sửa core**. Toàn bộ nằm trong thư mục `proxy/`.

## Giới thiệu

Module này:

1. **Fetch** danh sách proxy Urban VPN qua API (giống extension trình duyệt) — refresh mỗi **25 phút**
2. Ghi file `data/proxies_curl.txt` (một URL proxy mỗi dòng: `http://user:1@ip:port`)
3. **Sync** vào PostgreSQL bảng `scanengine_proxy` — reNgine đọc qua `get_random_proxy()`
4. Tự bật **Use Proxy** trong reNgine khi có danh sách hợp lệ

```
Urban VPN API → fetch_urban_proxies.py → proxy/data/proxies_curl.txt
                                              ↓
                              make sync-once → sync_django.py (trong container web)
                                              ↓
                              scanEngine.models.Proxy → PostgreSQL scanengine_proxy
                                              ↓
                              UI Proxy Settings + celery get_random_proxy() → scan tools
```

**Nguồn sự thật duy nhất cho scan:** bảng Django `scanEngine.models.Proxy` (PostgreSQL `scanengine_proxy`). File `proxies_curl.txt` **không** được reNgine đọc khi scan — chỉ là buffer trước khi sync.

**Xác minh trên server:** `make verify` (chạy sau `make sync-once`).

**Lưu ý tên service:** trong docker-compose gốc, service `proxy` là **nginx** (HTTPS reverse proxy). Module dùng container `urban-proxy-fetcher` (HTTP proxy pool) — không nhầm lẫn.

---

## Yêu cầu hệ thống

| Yêu cầu | Ghi chú |
|---------|---------|
| Docker + Docker Compose | Bắt buộc trên máy chạy thật |
| File `.env` ở thư mục gốc reNgine | `POSTGRES_*`, `DOMAIN_NAME`, … |
| Internet | Sidecar gọi Urban VPN API |
| OS | Linux khuyến nghị; Windows/Mac: Docker Desktop + Git Bash hoặc WSL |
| `make` (tùy chọn) | `./up.sh` chạy được không cần make |

---

## Cài đặt nhanh

### Bước 1: Chuẩn bị `.env` ở thư mục gốc reNgine

```bash
# Ví dụ: copy mẫu nếu có, rồi chỉnh POSTGRES_PASSWORD, DOMAIN_NAME, ...
cp .env.example .env   # nếu repo có file mẫu
nano .env
```

### Bước 2: Khởi động reNgine + Urban proxy

```bash
cd proxy
make up          # hoặc: ./up.sh
```

**Hai kịch bản tự động:**

| Kịch bản | Hành vi |
|----------|---------|
| reNgine **chưa chạy** | Bootstrap full stack (`make certs`, `build`, `up`, `migrate`) + sidecar proxy |
| reNgine **đã chạy** | Chỉ start `urban-proxy-fetcher` + recreate `celery` (mount file proxy) |

### Bước 3: Tạo tài khoản admin (lần đầu)

```bash
make -C .. username
```

### Truy cập

- HTTPS qua nginx: `https://<DOMAIN_NAME>/` (mặc định port **443**)
- Trực tiếp web container: `http://127.0.0.1:8000`

Sau ~1–3 phút, file `data/proxies_curl.txt` có proxy và reNgine tự dùng proxy khi scan.

---

## Lệnh

| Lệnh | Shell tương đương | Mô tả |
|------|-------------------|-------|
| `make up` | `./up.sh` | Bootstrap full (nếu cần) + Urban proxy |
| `make up` với `-n` | `./up.sh -n` | Non-interactive (bỏ qua prompt tạo user) |
| `make down` | `./down.sh` | Tắt **chỉ** module proxy; reNgine core vẫn chạy |
| `make down-all` | `./down-all.sh` | Tắt toàn bộ stack reNgine + proxy |
| `make logs` | `./scripts/logs.sh` | Xem log sidecar |
| `make status` | `./scripts/status.sh` | Trạng thái core + số proxy |
| `make disable` | `./scripts/disable.sh` | `use_proxy=false` trong DB |
| `make sync-once` | `./scripts/sync-once.sh` | Đẩy file → Django `Proxy.save()` (container web) |
| `make verify` | `./scripts/verify-proxy.sh` | Xác nhận DB + `get_random_proxy()` khớp UI |
| `make help` | `./scripts/help.sh` | Trợ giúp |

---

## Cấu hình

Biến tùy chọn (xem [`proxy/.env.example`](.env.example); có thể thêm vào `.env` gốc hoặc export trước `make up`):

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `URBAN_PROXY_WORKERS` | `20` | Số worker fetch credential song song |
| `URBAN_PROXY_INTERVAL` | `25` | Phút giữa mỗi lần refresh proxy |
| `AUTO_ENABLE_PROXY` | `true` | Tự bật Use Proxy trong reNgine khi sync |
| `COMPOSE_PROJECT_NAME` | tên folder repo | Phải khớp project Docker của stack reNgine |

---

## Cách hoạt động chi tiết

### Fetch (`fetch_urban_proxies.py --watch`)

- Gọi Urban VPN API, lấy credential từng server
- Ghi atomic: `*.tmp` → rename (an toàn khi đọc đồng thời)
- Credential Urban hết hạn ~**30 phút**; refresh **25 phút** giữ proxy luôn còn hiệu lực

### Sync (`make sync-once` → `sync_django.py`)

- Chạy **trong container `web`** (cùng Django ORM với màn Proxy Settings)
- Đọc `/usr/src/urban_proxies/proxies_curl.txt` (mount từ `./proxy/data`)
- Ghi `Proxy.objects.first()` → `proxies` + `use_proxy` → `.save()`
- `make disable` gọi `sync_django.py --disable` (cùng đường ORM)

### reNgine lưu và dùng proxy ở đâu

| Thành phần | File / bảng | Vai trò |
|------------|-------------|---------|
| **Model** | `web/scanEngine/models.py` → `Proxy` | `use_proxy` (bool), `proxies` (TextField, một URL/dòng) |
| **PostgreSQL** | `scanengine_proxy` | Dữ liệu thật web + celery đọc chung |
| **UI** | `web/scanEngine/views.py` → `proxy_settings()` | Đọc/ghi `Proxy.objects.all()[0]` qua `ProxyForm` |
| **Scan** | `web/reNgine/common_func.py` → `get_random_proxy()` | `Proxy.objects.first()`; trả `''` nếu `use_proxy=false` hoặc không có row |
| **Celery tasks** | `web/reNgine/tasks.py` | subfinder, naabu, httpx, nuclei, gau, gospider, katana, … gọi `get_random_proxy()`; theHarvester ghi `proxies.yaml` từ `Proxy.objects` |
| **File Urban** | `proxy/data/proxies_curl.txt` | Chỉ module fetch + bước sync; **scan không đọc file này** |

Điều kiện scan thực sự dùng proxy: `use_proxy=true` **và** field `proxies` không rỗng.

### Volume

- `./proxy/data` ↔ sidecar `/data` (read/write fetch)
- `./proxy/data` ↔ web `/usr/src/urban_proxies` (read-only, cho `sync_django.py`)
- `sync_django.py` mount riêng vào web (read-only)

---

## Cấu trúc thư mục

```
proxy/
├── README.md                 # Tài liệu này
├── fetch_urban_proxies.py    # Fetch Urban VPN proxy list
├── sync_django.py              # Sync file → Proxy model (chạy trong container web)
├── sync_proxies_to_db.py     # DEPRECATED — không dùng; giữ tham khảo
├── entrypoint.sh             # Sidecar: fetch + sync
├── Dockerfile
├── requirements.txt
├── docker-compose.yml        # Overlay merge ../docker-compose.yml
├── Makefile                  # Wrapper gọi shell scripts
├── up.sh / down.sh / down-all.sh
├── scripts/                  # Logic bootstrap & vận hành
├── .env.example
├── .gitignore
└── data/                     # proxies_curl.txt (runtime, gitignored)
```

---

## Troubleshooting

### Docker chưa chạy

```
ERROR: Docker is not running
```

→ Khởi động Docker Desktop hoặc `sudo systemctl start docker`.

### Thiếu `.env`

```
Missing ../.env
```

→ Tạo `.env` ở thư mục gốc reNgine với `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DOMAIN_NAME`, …

### `proxies_curl.txt` rỗng hoặc chưa có

→ Xem log: `make logs`  
→ Kiểm tra internet và Urban API  
→ Fetch lần đầu có thể mất 1–3 phút (20 workers)

### Scan không dùng proxy

1. `make status` — sidecar có chạy không?
2. `make sync-once` — ép sync file → DB
3. Kiểm tra UI reNgine → Settings → Proxy (Use Proxy phải bật; module tự bật nếu `AUTO_ENABLE_PROXY=true`)

### Muốn tắt proxy scan

```bash
make disable
# hoặc set AUTO_ENABLE_PROXY=false rồi restart sidecar
```

### Network Docker lỗi (`rengine_rengine_network`)

→ Đảm bảo `COMPOSE_PROJECT_NAME` khớp tên project khi chạy `make up` ở root (thường = tên folder repo, ví dụ `rengine`).

### Cập nhật reNgine upstream

```bash
git pull    # ở thư mục gốc — không đụng proxy/
cd proxy && make up
```

---

## Checklist tự kiểm tra (máy có Docker)

| Bước | Kiểm tra |
|------|----------|
| 1 | `cd proxy && make up` — không lỗi |
| 2 | `docker ps` — thấy `rengine-urban-proxy`, `db`, `web`, `celery` |
| 3 | `data/proxies_curl.txt` — nhiều dòng sau ~2 phút |
| 4 | `make status` — sidecar running, proxies > 0 |
| 5 | Chạy scan — log celery có `Using proxy: http://...` |
| 6 | `make down` — sidecar stop, web/celery vẫn chạy |

---

## Bảo mật & lưu ý

- **Không commit** `data/proxies_curl.txt` — chứa credential proxy
- Proxy Urban **miễn phí** — không đảm bảo ổn định hay bảo mật
- Chỉ dùng cho **recon hợp pháp** với phạm vi được phép
- `AUTO_ENABLE_PROXY=true`: mỗi lần sync có thể **bật lại** Use Proxy nếu bạn tắt trên UI

---

## English (short)

Self-contained module under `proxy/`: run `make up` (or `./up.sh`) to bootstrap reNgine if needed and start the Urban VPN proxy sidecar. Proxies sync into PostgreSQL for reNgine scans. No core code changes. Stop proxy only: `make down`. Stop everything: `make down-all`.
