# swing-screener — KHUNG v3 tự động

Screener chạy theo lịch trên GitHub Actions, commit kết quả JSON ngược vào repo.

Link đọc:
`https://raw.githubusercontent.com/VuongDuong-code/swing-screener/main/out/latest.json`

## Cấu trúc

| File | Vai trò |
|---|---|
| `screener_v3.py` | Port của Ô 2→7. Một namespace, giống hệt Colab. |
| `export_v3.py` | Schema JSON — thay Ô 8/9/10 (in bảng). |
| `probe.py` | Chạy **trong Colab** để lấy 2 thông tin còn treo (xem dưới). |
| `data/` | Log tích luỹ (`khoi_ngoai_log.csv`, `universe_rank.csv`…), commit ngược. |
| `out/latest.json` | Kết quả phiên gần nhất. `out/lich_su/YYYY-MM-DD.json` là bản đóng băng. |

## Secrets bắt buộc

Repo **public** → không được commit số liệu cá nhân. Đặt ở
Settings ▸ Secrets and variables ▸ Actions:

| Secret | Định dạng | Ví dụ |
|---|---|---|
| `NAV` | số | `1000000000` |
| `DANH_MUC_HIEN_TAI` | JSON | `{"GMD": 12.0, "FRT": 8.0}` hoặc `{}` |
| `CHUOI_R_GAN_NHAT` | JSON | `[-1.0, 2.3, -1.0, 4.1]` hoặc `[]` |
| `CO_BAN_TAY` | JSON | `{"HPG": {"eps_yoy": 34.0, "catalyst": "..."}}` |
| `INVALIDATION` | số | `1651.20` |

Secret sai cú pháp JSON → job **dừng**, không im lặng dùng mặc định.
Chạy với NAV sai còn nguy hiểm hơn không chạy.

> Lịch sử commit của repo public **không xoá được**. Nếu đã lỡ commit số liệu
> cá nhân thì phải tạo repo mới, không phải xoá file.

## Xác nhận chạy thật — Colab 02/09/2026, Ô 1 → Ô 7

vnstock **4.0.7 chạy thông suốt**, không sửa dòng nào. Quét 75/75 mã, không lỗi.
Bộ dò cột của Ô 6 tìm đúng: `foreign_buy_volume − foreign_sell_volume` ×
`close_price` × 1, nguồn KBS, trung vị |KN| = 5,77 tỷ VND (thang hợp lý).

Kết quả phiên đó: **0 mã qua bộ lọc**. VNINDEX Stage 1 (MA30W dốc xuống
−0,56%/4 tuần) → cổng đóng, ngân sách về 0% NAV. Bộ lọc chặn nhiều nhất:
`F3×207, F2×67, F1×64, F4×48, F5×48, SETUP×47`.

**Nến cuối 28/08 KHÔNG phải nguồn trễ** — 31/08 → 02/09 là nghỉ bù Quốc
khánh, 28/08 (thứ Sáu) là phiên gần nhất. Danh sách `NGHI_LE` trong code
được trừ ra khi đo `do_tuoi_du_lieu`, nên không bắn báo động giả. Cập nhật
danh sách này mỗi năm khi HOSE công bố lịch — Tết âm lịch đổi ngày hằng năm.
Báo động giả nguy hiểm ngang báo động thiếu: quen bỏ qua một lần thì lần
nguồn hỏng thật cũng bỏ qua nốt.

**Hai chỗ đã sửa trong port:**

- **Chặn chạy lại khi chưa có phiên mới.** Cron chạy T2–T6, nghỉ lễ thì nguồn
  vẫn trả nến cũ. Chạy tiếp sẽ đốt ~8 phút quota cho kết quả y hệt **và** ghi
  thêm một dòng khối ngoại mang ngày không phải phiên giao dịch. Kiểm tra
  `out/latest.json` trước khi quét; trùng phiên thì dừng. Ép chạy lại:
  `workflow_dispatch` có ô `chay_lai`, hoặc `CHAY_LAI=1`.
- **Thứ tự Ô 6.** Trong Colab, Ô 6 chạy trước Ô 3 nên `NGAY_MOC` còn `None`
  và `_ngay_phien()` tự suy ngày theo đồng hồ — log khối ngoại mang ngày
  **02/09** trong khi giá là phiên **28/08**. Hai lịch sử lệch nhau âm thầm.
  Port này gọi `chay_khoi_ngoai()` **sau** `do_nguon()`, nên log ghi đúng
  mốc phiên của giá.

> ⚠️ **Trước khi seed `data/`:** file `khoi_ngoai_log.csv` sinh ra từ lần chạy
> Colab 02/09 có 75 dòng gắn ngày `2026-09-02` — một ngày **nghỉ lễ**, không
> phải phiên giao dịch. Sửa cột `ngay` thành `2026-08-28` (hoặc xoá hẳn 75
> dòng đó) trước khi commit, nếu không KN10 đếm một phiên không tồn tại.

## Kết quả probe (02/09/2026) — đã áp vào requirements.txt

```
vnstock 4.0.7 | pandas 2.2.3 | numpy 2.1.3
vnstock.api.quote: Quote = CÓ      -> đường dẫn import của Ô 3 vẫn sống ở 4.x
Trading: history, price_board, provider, random_agent, show_log, source, symbol
         KHÔNG có foreign_trade    -> giữ nguyên khối dò tên cột ở Ô 6
```

Hai hệ quả:

- **Ô 6 vẫn là điểm mong manh nhất.** Không có API khối ngoại ổn định, nên vẫn
  phải dò tên cột từ `price_board()`. vnstock 4.x là bản "Unified UI" — nếu nó
  đổi tên cột, Ô 6 sẽ ném `RuntimeError` kèm danh sách cột thật. Lỗi đó KHÔNG
  chặn phần còn lại; hệ quả duy nhất là Lớp 3 bị loại khỏi mẫu số. Gặp thì gửi
  dòng `Cột nguồn trả về: [...]` để cập nhật bộ dò.
- **Nên ghim luôn Ô 1 của notebook.** Đổi `!pip install -U vnstock -q` thành
  `!pip install vnstock==4.0.7 -q`. Trong giai đoạn chạy song song, `-U` sẽ kéo
  bản mới nhất tại thời điểm chạy và bản tay trôi khỏi bản tự động — lúc đó
  không phân biệt được "khung sai" với "thư viện đổi".

`out/latest.json` có `cau_hinh.phien_ban_thu_vien` ghi lại phiên bản thật của
mỗi lần chạy. Khi hai bản lệch nhau, nhìn chỗ đó trước.

## Chạy song song trước khi bỏ bản tay

Workflow có `workflow_dispatch` — bấm tay để chạy ngay, không cần chờ 16:00.
Vài phiên đầu: chạy cả Colab lẫn Actions, đối chiếu `out/latest.json` với bảng
Ô 8. Chỉ bỏ bản tay khi khớp.

Ba chỗ đáng nghi nhất khi đối chiếu:
- **`data/khoi_ngoai_log.csv` số phiên.** Colab tích luỹ trên Drive, Actions
  tích luỹ trong repo — hai lịch sử tách rời. Copy file từ Drive vào `data/`
  ở commit đầu, nếu không KN10 đếm lại từ 0 và Lớp 3 bị loại thêm 10 phiên.
- **Mốc phiên.** Lần chạy gần nhất báo 28/08 trong khi ngày thực là 02/09.
  `out/latest.json` có trường `phien` và `canh_bao_du_lieu.ma_du_lieu_cu` —
  đối chiếu trước khi đọc bất cứ con số nào.
- **Rate limit.** `GIOI_HAN_RPM = 10` (gói Khách). Quét 50 mã ≈ 5 phút.
  Có API key Community (60 req/phút) thì nâng lên 45.

## Ngang bằng với notebook v8.1

Port này khớp với `KhungV2_Screener_v8-0-v3.ipynb` bản 02/09/2026 (đã diff
từng ô). Hai thay đổi thật của v8.1 đều đã có:

- **Ô 7 nạp CACHE dùng chung** → ở đây là `OHLCV_CACHE`, nạp ngay trong vòng
  quét. Không cần khoá theo `NGAY_MOC` như Colab: mỗi lần chạy Actions là một
  tiến trình mới, không có runtime sống qua đêm để lặng lẽ phục vụ nến hôm qua.
- **Ô 10 chọn mã theo SỐ MÃ QUA BỘ LỌC**, không còn con số cứng → `export_v3.py`
  dùng đúng quy tắc đó cho phần OHLCV: tất cả mã không mang nhãn ❌/⚠️, sắp theo
  `_v3ok → ĐiểmV3 → Điểm`, trần 25, mã **đang giữ luôn có mặt** kể cả khi đã bị
  loại. Phần bị cắt ghi rõ ở `canh_bao_du_lieu.ma_bi_cat_khoi_ohlcv`.

Nến TUẦN xuất cả tuần đang chạy (khớp Ô 10) nhưng gắn `chua_dong: true` —
điều kiện "đóng cửa TUẦN" của Phần 6 có hiệu lực cao nhất, đọc nhầm nến dở
là hỏng cả kết luận ĐÃ GÃY.

## Không port sang đây

Ô 4C (kiểm định AUC) và Ô 11 (sổ nhật ký + expectancy) không nằm trong luồng
hằng ngày — vẫn chạy tay trong Colab.
