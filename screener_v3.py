# -*- coding: utf-8 -*-
"""
screener_v3.py — KHUNG v3 (v8.0-v3) chạy phi tương tác trên GitHub Actions.

PORT TỪ NOTEBOOK COLAB — nguyên tắc: KHÔNG sửa logic, chỉ đổi vỏ.
Ba thay đổi duy nhất so với bản Colab:
  1. Dữ liệu cá nhân (NAV, danh mục, chuỗi R, cơ bản tay) đọc từ BIẾN MÔI
     TRƯỜNG (GitHub secret). Repo public — không được commit các số này,
     và lịch sử commit thì xoá sau cũng không gỡ được.
  2. Bỏ mọi phụ thuộc Colab: mount Drive, google.colab.files, input().
     Log tích luỹ ghi vào ./data và được workflow commit ngược vào repo.
  3. Ô 8/9/10 (in bảng) thay bằng JSON theo schema export_v3.py: mỗi bộ lọc
     xuất GIÁ TRỊ ĐO ĐƯỢC, không chỉ pass/fail, kèm OHLCV thô để kiểm chứng.

Cell 4C (kiểm định AUC) và Ô 11 (sổ nhật ký) KHÔNG nằm trong luồng hằng ngày
nên không port sang đây.
"""
import json as _json
import os as _os


def _env_raw(ten, mac_dinh=None):
    v = _os.environ.get(ten)
    if v is None or not str(v).strip():
        return mac_dinh
    return str(v).strip()


def _env_json(ten, mac_dinh):
    """Secret dạng JSON. Sai cú pháp -> DỪNG, không im lặng dùng mặc định:
    chạy với NAV/danh mục sai còn nguy hiểm hơn là không chạy."""
    v = _env_raw(ten)
    if v is None:
        return mac_dinh
    try:
        return _json.loads(v)
    except Exception as e:
        raise SystemExit(f"⛔ Secret {ten} không phải JSON hợp lệ: {e}")


def _env_int(ten, mac_dinh):
    v = _env_raw(ten)
    return mac_dinh if v is None else int(float(v.replace("_", "")))


def _env_float(ten, mac_dinh):
    v = _env_raw(ten)
    return mac_dinh if v is None else float(v)


def _ghi_duoc(thu_muc):
    """Chứng minh thư mục ghi được THẬT bằng cách ghi rồi xoá 1 file."""
    try:
        _os.makedirs(thu_muc, exist_ok=True)
        p = _os.path.join(thu_muc, ".khungv2_ghithu")
        with open(p, "w") as f:
            f.write("ok")
        with open(p) as f:
            assert f.read() == "ok"
        _os.remove(p)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ======================================================================
# Ô 2 — CẤU HÌNH  ⬅️ CHỈ SỬA Ở ĐÂY
# ======================================================================
import os
from datetime import datetime, date, timedelta

# ---------------------------------------------------------------- #
# 2.1 DANH MỤC HIỆN TẠI                                             #
# Để RỖNG {} nếu đang 100% tiền mặt.                                #
# Định dạng: {"MÃ": tỷ_trọng_phần_trăm_NAV}                          #
# ---------------------------------------------------------------- #
DANH_MUC_HIEN_TAI = _env_json("DANH_MUC_HIEN_TAI", {})   # secret

NAV = _env_int("NAV", 1_000_000_000)                     # secret
RUI_RO_MOI_LENH_PCT = 1.0       # % NAV rủi ro tối đa 1 lệnh
TY_TRONG_TOI_DA_1_MA = 15.0     # % NAV

# ---------------------------------------------------------------- #
# 2.2 NGƯỠNG KHUNG v2                                               #
# ---------------------------------------------------------------- #
INVALIDATION    = _env_float("INVALIDATION", 1651.20)    # mức cấu trúc chỉ số
RR_TOI_THIEU    = 2.0           # dưới ngưỡng này -> Đứng ngoài
RR_TOI_THIEU_SAU_CANH_BAO = 2.5 # dùng khi kịch bản xấu kích hoạt

GTGD_TOI_THIEU  = 20.0          # tỷ đồng — dưới ngưỡng: giảm 50% size
GTGD_CANH_BAO   = 40.0          # tỷ đồng — vùng sát ngưỡng, gắn cờ
CACH_DINH_52W   = 25.0          # %
RSI_SETUP       = (40, 65)
HE_SO_SETUP     = 0.75          # setup: |ExtATR| <= 0.75
HE_SO_DUOI      = 2.0           # chạy xa: ExtATR > 2.0

# [VÁ LỖI 2] RS tối thiểu để được gắn nhãn SETUP.
# ExtATR thấp + RS thấp = YẾU, không phải nén tích lũy.
RS_TOI_THIEU_SETUP = 5.0

# ---------------------------------------------------------------- #
# 2.3 THAM SỐ PIVOT & R:R   [VÁ LỖI 3]                              #
# ---------------------------------------------------------------- #
PIVOT_N_NGAY    = 5             # số nến 2 bên để xác nhận pivot khung ngày
PIVOT_N_TUAN    = 3             # số nến 2 bên để xác nhận pivot khung tuần

# [VÁ LỖI 8] Cửa sổ nhìn lại — pivot cũ hơn ngưỡng này KHÔNG còn là cấu trúc sống.
LOOKBACK_PIVOT_NGAY = 120       # ~6 tháng
LOOKBACK_PIVOT_TUAN = 52        # ~1 năm

# [VÁ LỖI 9] SL phải đủ rộng để sống qua T+2.5 (2-3 phiên nhiễu).
SL_TOI_THIEU_ATR = 1.5          # SÀN: SL cách giá vào >= 1.5 × ATR14
SL_TOI_DA_ATR    = 4.0          # cảnh báo: xa hơn mức này = không còn cấu trúc

# [VÁ 12] TRẦN CỨNG cho khoảng cách SL. Bản cũ chỉ có SÀN -> mã momentum
# không có đáy pivot gần bị gán SL cách 20-30% -> R:R chết oan (ca FRT/GMD/ORS).
# Khi bị cap, SL là stop RỦI RO (không phải cấu trúc) -> tự động giảm nửa size.
# [SỬA v7.3] Bản v7.2 kích hoạt cap ngay tại 2.5×ATR -> cap CẢ pivot thật
# (VNINDEX 26/08: đáy 1715.91 cách 3.71×ATR là cấu trúc SỐNG) -> R:R bị
# THỔI PHỒNG 0.64 -> 0.95. Bản vá tự nới chuẩn = vi phạm Phần 5.
# Nguyên tắc mới:
#   - Chỉ cap khi pivot xa hơn NGUONG_KICH_HOAT_SL_CAP (= mốc "hết cấu trúc")
#   - Khi đã cap: stop hẹp hơn -> xác suất bị quét cao hơn -> ngưỡng R:R PHẢI cao hơn
NGUONG_KICH_HOAT_SL_CAP = 4.0   # = SL_TOI_DA_ATR. Dưới mức này: pivot còn sống, KHÔNG đụng.
# [SỬA v7.4 — BUG A] Giá trị cap PHẢI BẰNG ngưỡng kích hoạt.
# LỖI v7.3: kích hoạt tại 4.0×ATR nhưng cap về 2.5×ATR -> tự cắt 1.5×ATR khỏi R
#           -> R:R bị THỔI PHỒNG một cách âm thầm.
# Đo trên VNINDEX 28/08/2026: SL pivot thật 1.715,91 (R = 116,21)
#           R:R thật    = 56,87 / 116,21 = 0,49
#           R:R hiển thị= 56,87 /  67,55 = 0,84   (+71%)
# Đặt = NGUONG_KICH_HOAT_SL_CAP thì stop nằm ĐÚNG mốc "hết cấu trúc",
# không còn vùng chết 1,5×ATR ở giữa.
SL_TOI_DA_ATR_CAP = 4.0         # = NGUONG_KICH_HOAT_SL_CAP. KHÔNG đặt thấp hơn.
RR_TOI_THIEU_KHI_SL_CAP = 3.0   # bù rủi ro: stop rủi ro phải đổi lấy R:R cao hơn
HE_SO_SIZE_KHI_SL_CAP = 0.5     # nhân dồn với hệ số bậc giải ngân
TP_FALLBACK_RR   = 2.5          # measured move khi giá ở vùng đỉnh, không có kháng cự

# [SỬA v7.4 — BUG B] TP_CACH_TOI_THIEU_PCT là thủ phạm thật của "bug TP1".
# LỖI v7.3: dùng % này làm BỘ LỌC LOẠI kháng cự -> mọi đỉnh nằm trong khoảng
#           đó bị vứt đi và TP1 NHẢY CÓC lên mốc xa hơn.
# Đo trên VNINDEX 28/08/2026 (giá 1.832,12; lọc 3% = phải ≥ 1.887,08):
#           bị loại: 1.838,52 / 1.871,09 / 1.873,58 / 1.873,87
#           TP1 nhảy lên 1.888,99 -> R:R 0,62 bị thổi thành 0,84.
# NGUYÊN TẮC MỚI: TP1 = KHÁNG CỰ CHƯA GÃY GẦN NHẤT. Khe tối thiểu chỉ để loại
# nhiễu dính sát giá, KHÔNG bao giờ để nhảy cóc. Kháng cự quá gần -> R:R tự
# trượt -> đó là NO-TRADE ĐÚNG, không phải lý do đi tìm mốc xa hơn.
# [SỬA v7.5 — BUG L] v7.4 vá quá tay: thay bộ lọc 5% bằng khe 0.25×ATR thì
# nhận cả VI-PIVOT. Phiên 28/08: TP1 của 8/10 mã top nằm trong 0.26-0.79×ATR,
# tức cách giá ~1% = 1/7 biên độ một phiên → R:R bị BÓP xuống 0.07-0.27.
# v7.3 THỔI R:R, v7.4 BÓP R:R. Cả hai đều sai, chỉ khác chiều.
#
# NGƯỠNG ĐÚNG suy ra từ chính hình học của khung, không phải chọn tùy ý:
#   sàn SL   = SL_TOI_THIEU_ATR × ATR           (điều kiện sống qua T+2.5)
#   R:R ≥ k  ⟺ thưởng ≥ k × sàn SL = k × SL_TOI_THIEU_ATR × ATR
#   ⟹ 2.0 × 1.5 = 3.0×ATR là khoảng cách TỐI THIỂU để R:R ≥ 2 KHẢ THI.
# Kháng cự gần hơn 3×ATR ⟹ đặt stop ở ĐÂU CŨNG không đạt R:R.
# Đó KHÔNG phải "R:R kém" mà là BẾ TẮC HÌNH HỌC — đúng khái niệm đã dùng ở
# tầng chỉ số, nay đưa xuống tầng mã.
TP_KHE_TOI_THIEU_ATR = 0.25         # chỉ để loại nhiễu dính sát giá
# Ngưỡng phân loại KẸP KHÁNG CỰ (tự suy từ RR_TOI_THIEU × SL_TOI_THIEU_ATR)
NGUONG_KEP_KHANG_CU_ATR = None      # None = tự tính; đặt số để ép thủ công
BAT_PHAN_LOAI_KEP = True            # tách "kẹp kháng cự" khỏi "R:R không đạt"
# Hai hằng số dưới GIỮ LẠI nhưng chỉ còn dùng để CẢNH BÁO "TP1 quá gần",
# tuyệt đối không dùng để lọc bỏ kháng cự.
TP_CANH_BAO_GAN_PCT_IDX     = 3.0
SL_CACH_TOI_THIEU_PCT_IDX   = 1.0
TP_CANH_BAO_GAN_PCT_CP      = 5.0
SL_CACH_TOI_THIEU_PCT_CP    = 2.0
# alias tương thích ngược (Ô 7/9/10 cũ còn gọi tên này)
TP_CACH_TOI_THIEU_PCT_IDX   = TP_CANH_BAO_GAN_PCT_IDX
TP_CACH_TOI_THIEU_PCT_CP    = TP_CANH_BAO_GAN_PCT_CP

# [VÁ LỖI 10] Chống dữ liệu cũ: cổ phiếu phải cùng phiên với chỉ số.
THU_NGUON_KHAC_KHI_CU = True    # nếu nguồn chính trả nến cũ -> thử nguồn còn lại

# ---------------------------------------------------------------- #
# 2.4 CỔNG CHẾ ĐỘ (DE_RISK)   [VÁ LỖI 4]                            #
# ---------------------------------------------------------------- #
# [VÁ 16] Bộ đệm cổng: cổng chỉ vượt vài điểm là "mở hờ", một phiên đỏ là đóng.
BUFFER_CONG_ATR      = 0.5      # cổng DÀY = DE_RISK_LEVEL + 0.5 × ATR14(chỉ số)
TRAN_NAV_CONG_MONG   = 15       # % NAV trần khi cổng mở nhưng chưa DÀY

HE_SO_QUY_DOI_IDX    = 1        # PHẢI = 1 với chỉ số
DUNG_TUAN_HOAN_CHINH = True     # bỏ tuần đang chạy dở
NEO_TUAN             = "W-FRI"
BIEN_HOP_LE_IDX      = (800, 3000)

# ---------------------------------------------------------------- #
# 2.5 SỰ KIỆN — FTSE   [VÁ LỖI 7]                                   #
# ---------------------------------------------------------------- #
# [PORT] NGHỈ LỄ HOSE — dùng để đo ĐỘ TƯƠI dữ liệu cho đúng.
# Không có danh sách này thì "nến cuối 28/08 mà hôm nay 02/09" bị đếm là trễ
# 3 ngày làm việc và bắn báo động giả, trong khi 31/08–02/09 là nghỉ bù Quốc
# khánh. Báo động giả nguy hiểm ngang báo động thiếu: quen bỏ qua một lần thì
# lần nguồn hỏng thật cũng bỏ qua nốt.
# Cập nhật mỗi năm khi HOSE công bố lịch (Tết âm lịch đổi ngày hằng năm).
NGHI_LE = _env_json("NGHI_LE", [
    "2026-08-31", "2026-09-01", "2026-09-02",   # nghỉ bù + Quốc khánh
])

NGAY_FTSE_HIEU_LUC = date(2026, 9, 18)
FTSE_ALL_WORLD = ["VCB", "VIC", "VHM", "BID", "HPG", "VPB"]
# 27 mã All-Cap: dán vào đây khi có danh sách chính thức.
FTSE_ALL_CAP   = []
# Số ngày sau hiệu lực mới coi là "đã qua rủi ro unwind"
NGAY_CHO_SAU_FTSE = 7

# ---------------------------------------------------------------- #
# 2.6 API & DỮ LIỆU                                                 #
# ---------------------------------------------------------------- #
NGUON_UU_TIEN   = ["KBS", "VCI"]    # TCBS đã gỡ khỏi vnstock
SO_PHIEN        = 400               # >= 320; 400 an toàn cho MA200D + MA20W

# [SỬA v7.4 — BUG H] 18/20 là quá sát. Bộ đếm của ta là cửa sổ TRƯỢT 60s,
# bộ đếm của vnstock là PHÚT ĐỒNG HỒ — hai cửa sổ lệch pha nên 18 req của ta
# có thể rơi trọn vào một phút của họ. Cộng thêm: Ô 6 vừa đốt quota, do_nguon()
# tốn 2 req, và q.history() có thể tự phát sinh request phụ mà ta không đếm.
# Thực tế phiên 28/08: chết ở mã thứ 15 sau ~50 giây.
GIOI_HAN_RPM    = 10                # gói Khách 20/phút → chạy ở 50% cho an toàn
GIOI_HAN_RPM_SAN = 4                # đáy khi tự động hạ tốc sau mỗi lần dính limit
SO_LAN_THU_GIOI_HAN = 4             # số lần thử lại khi dính rate limit
CHO_KHI_LIMIT   = 65
# 👉 FIX THẬT SỰ: đăng ký API key MIỄN PHÍ tại https://vnstocks.com/login
#    (gói Community = 60 req/phút). Làm theo hướng dẫn của vnstock để nạp key,
#    rồi đặt GIOI_HAN_RPM = 45. Quét 75 mã: ~8 phút → ~2 phút, và hết dính limit.
KHOI_PHUC_TIEN_TRINH = True         # chạy lại Ô 7 sau khi lỗi -> tiếp tục, không quét lại
SO_MA_UNIVERSE  = 50
# [VÁ 29] price_board cả 75 mã một lần rất dễ OSError/timeout -> chia lô.
KICH_THUOC_LO   = 25                # số mã mỗi lần gọi price_board
DANH_SACH_TAY   = []                # điền mã để bỏ qua universe tự động

# ---------------------------------------------------------------- #
# 2.7 ĐƯỜNG DẪN                                                     #
# ---------------------------------------------------------------- #
THU_MUC = os.path.abspath(os.environ.get("DATA_DIR", "data"))
DUONG_DAN_KN      = f"{THU_MUC}/khoi_ngoai_log.csv"
DUONG_DAN_LOG     = f"{THU_MUC}/screener_log.csv"
DUONG_DAN_UNI     = f"{THU_MUC}/universe_rank.csv"
DUONG_DAN_DERISK  = f"{THU_MUC}/de_risk_log.csv"
KN_SO_PHIEN       = 10
KN_NGUONG_BAN     = 7

# ---------------------------------------------------------------- #
# 2.8 UNIVERSE ỨNG VIÊN + BẢN ĐỒ NGÀNH                              #
# ---------------------------------------------------------------- #
NGANH = {}
def _gan(ds, ten):
    for m in ds:
        NGANH[m] = ten

_gan(["SSI","VND","VIX","VCI","HCM","BSI","FTS","CTS","AGR","ORS","MBS"], "Chứng khoán")
_gan(["SHB","STB","MBB","VPB","TCB","ACB","CTG","BID","VCB","HDB",
      "TPB","LPB","EIB","MSB","OCB","VIB","SSB","NAB"], "Ngân hàng")
_gan(["BVH"], "Bảo hiểm")
_gan(["MSN","MCH","VNM","SAB","PNJ"], "Tiêu dùng")
_gan(["MWG","FRT","DGW"], "Bán lẻ ICT")
_gan(["FPT"], "Công nghệ")
_gan(["VTP"], "Chuyển phát")
_gan(["VIC","VHM","VRE","NVL","DIG","DXG","PDR","KBC","KDH","NLG","SZC","IJC","HDG"], "Bất động sản")
_gan(["GEX","CTD"], "Xây dựng")
_gan(["POW","GAS","PLX","BSR","PVD","PVS","NT2"], "Năng lượng")
_gan(["DGC","DPM","DCM"], "Hóa chất")
_gan(["HPG","HSG","NKG"], "Thép")
_gan(["VJC"], "Hàng không")
_gan(["GMD","VSC","HAH"], "Cảng biển")
_gan(["ANV","VHC","DBC"], "Thủy sản - NN")

NHOM_TAI_CHINH = {"Chứng khoán", "Ngân hàng", "Bảo hiểm"}
GIOI_HAN_SLOT_TAI_CHINH = 2     # tổng số mã tài chính tối đa trong danh mục

UNG_VIEN = sorted(NGANH.keys())

# ---------------------------------------------------------------- #
# 2.9 LƯU TRỮ BỀN VỮNG — [PORT] thay cho mount Google Drive         #
# ---------------------------------------------------------------- #
# Colab: log tích luỹ nằm trên Drive. GitHub Actions: nằm trong repo
# và được commit ngược sau mỗi phiên. Cùng một hợp đồng: thư mục phải
# GHI ĐƯỢC THẬT, nếu không khoi_ngoai_log.csv không bao giờ đủ 10 phiên
# -> Lớp 3 (25% trọng số) bị loại khỏi mẫu số phiên này qua phiên khác.
os.makedirs(THU_MUC, exist_ok=True)
DRIVE_OK, _ly_do_drive = _ghi_duoc(THU_MUC)
if not DRIVE_OK:
    raise RuntimeError(
        f"Không ghi được vào {THU_MUC} — {_ly_do_drive}. "
        "Trên GitHub Actions đây là lỗi cấu hình, KHÔNG được chạy tiếp: "
        "log khối ngoại sẽ mất và KN10 vĩnh viễn thiếu.")
print(f"✅ Lưu trữ ghi được — dữ liệu tích luỹ tại {THU_MUC}")

# ---------------------------------------------------------------- #
# 2.10 PHƯƠNG ÁN B — CỔNG NHỊ PHÂN + NGÂN SÁCH GIẢI NGÂN            #
# ---------------------------------------------------------------- #
# PHƯƠNG ÁN A (v7.3): R:R của CHỈ SỐ phủ quyết lệnh CỔ PHIẾU.
#   Hệ quả toán học: R:R chỉ số chỉ đạt >= 2.0 khi giá nằm SÁT MA20W.
#   Trong toàn bộ pha markup, chỉ số luôn chạy xa MA20W -> R:R luôn < 2
#   -> bị khóa 100% tiền mặt ĐÚNG lúc thị trường tăng.
# PHƯƠNG ÁN B: chỉ số quyết định ĐƯỢC GIẢI NGÂN BAO NHIÊU, không quyết định
#   CÓ ĐƯỢC VÀO LỆNH KHÔNG. R:R giữ nguyên 100% kỷ luật ở TẦNG MÃ.
#
#   Cổng   = nhị phân: Close >= DE_RISK_LEVEL  VÀ  chưa ĐÃ GÃY
#   Rủi ro = NgânSách = TrầnCổng(D) × f_ext × f_vol
#
# ⚠️ B KHÔNG PHẢI NỚI LỎNG. B đổi "chặn tuyệt đối" lấy "vào rất nhỏ".
#    Bạn SẼ ăn những cú thua mà A không bao giờ gặp — chỉ nhỏ hơn 4-8 lần.
CHE_DO_CONG = "B"               # "A" = v7.3 (R:R chỉ số chặn lệnh) | "B" = ngân sách

# Trục 1 — độ dày cổng D = (Close − DE_RISK_LEVEL) / ATR khung neo
# (ngưỡng D, trần % NAV) — tra từ trên xuống, lấy mốc đầu tiên thỏa D < ngưỡng
BANG_TRAN_CONG = [(0.00, 0), (0.25, 15), (0.75, 40), (9e9, 60)]

# Trục 2 — phạt mua đuổi theo ExtATR NGÀY của chỉ số
def _f_ext_tu_ext(e):
    if e is None or not (e == e):        # NaN
        return 0.50
    if abs(e) <= HE_SO_SETUP:  return 1.00      # vùng setup
    if e < -1.50:              return 0.50      # rơi dưới MA20D dù trên cổng
    if e <= 1.50:              return 0.75
    if e <= 2.50:              return 0.50      # chạy xa
    return 0.25

# Trục 3 — xác nhận volume khi giành lại mốc neo (khung TUẦN)
F_VOL_CHUA_XAC_NHAN = 0.50

# Cổng riêng TẦNG MÃ (bù cho việc chỉ số không còn phủ quyết)
BAT_COng_MA_MA20W    = True     # S1: giá mã phải >= MA20W của chính nó
RS_TOI_THIEU_VAO_LENH = 0.0     # S2: RS12w phải > mốc này mới được vào lệnh

assert SL_TOI_DA_ATR_CAP >= NGUONG_KICH_HOAT_SL_CAP, (
    "SL_TOI_DA_ATR_CAP < NGUONG_KICH_HOAT_SL_CAP -> cap sẽ THỔI R:R. "
    "Đây chính là BUG A của v7.3.")

print("=" * 66)
print(f"CẤU HÌNH KHUNG v2 — v7.6-B   [CHẾ ĐỘ CỔNG: {CHE_DO_CONG}]")
print("=" * 66)
if DANH_MUC_HIEN_TAI:
    print(f"Danh mục: {len(DANH_MUC_HIEN_TAI)} mã — "
          + ", ".join(f"{k} {v}%" for k, v in DANH_MUC_HIEN_TAI.items()))
    _tc = [m for m in DANH_MUC_HIEN_TAI if NGANH.get(m) in NHOM_TAI_CHINH]
    print(f"  Tài chính đang giữ: {len(_tc)}/{GIOI_HAN_SLOT_TAI_CHINH} slot"
          + (f" ({', '.join(_tc)})" if _tc else ""))
else:
    print("Danh mục: TRỐNG — 100% tiền mặt.")
    print("  → Bộ lọc chồng lấn ngành TẮT. Mọi mã xét trên chất lượng tín hiệu thuần.")
print(f"Universe ứng viên: {len(UNG_VIEN)} mã | INVALIDATION: {INVALIDATION:,.2f}")
print(f"R:R tối thiểu: {RR_TOI_THIEU} | RS tối thiểu cho SETUP: {RS_TOI_THIEU_SETUP}")
print(f"SL: sàn {SL_TOI_THIEU_ATR}×ATR | cap kích hoạt khi > {NGUONG_KICH_HOAT_SL_CAP}×ATR "
      f"→ cap về {SL_TOI_DA_ATR_CAP}×ATR, R:R yêu cầu {RR_TOI_THIEU_KHI_SL_CAP}, size ×{HE_SO_SIZE_KHI_SL_CAP}")
print(f"TP1: vùng kháng cự đạt hạng MÀNG gần nhất, khe tối thiểu "
      f"{TP_KHE_TOI_THIEU_ATR}×ATR (KHÔNG lọc bỏ theo %)")
print(f"Bộ đệm cổng: {BUFFER_CONG_ATR}×ATR (khung của mốc neo) "
      f"| NAV/lệnh: {RUI_RO_MOI_LENH_PCT}% của {NAV:,.0f} VND")
if CHE_DO_CONG == "B":
    print("CHẾ ĐỘ B: R:R chỉ số = THAM KHẢO (không chặn lệnh).")
    print("          Rủi ro thị trường -> NGÂN SÁCH % NAV. R:R giữ nguyên ở TẦNG MÃ.")
    print(f"          Cổng mã: MA20W={BAT_COng_MA_MA20W} | RS12w > {RS_TOI_THIEU_VAO_LENH}")
else:
    print("CHẾ ĐỘ A: R:R chỉ số CHẶN lệnh cổ phiếu (hành vi v7.3).")
print("=" * 66)
# ---------------------------------------------------------------- #
# 2.11 BẢN ĐỒ KHÁNG CỰ CÓ TRỌNG SỐ  (SUPPLY_SCORE)          [v7.6]  #
# ---------------------------------------------------------------- #
# VẤN ĐỀ v7.5: bộ chọn TP1 chỉ hỏi MỘT câu — "mốc này cao hơn giá không?"
# Mọi đỉnh pivot có trọng lượng như nhau: bóng nến volume 40% MA20 ngang
# hàng với vùng phân phối 4 tuần volume 170%.
# Hệ quả đo trên phiên 28/08/2026: 10/12 mã bị gắn KẸP KHÁNG CỰ.
# Chấm điểm tay 4 vùng của FRT cho kết quả cao nhất 44/100 — tức KHÔNG có
# tường thật nào phía trên, "kẹp" của FRT là KẸP GIẢ.
#
# v7.6: chấm điểm CUNG 0-100 cho từng VÙNG, rồi phân hạng:
#   TRONG SUỐT (<36)  — loại khỏi ứng viên TP1
#   MÀNG      (36-65) — TP1 hợp lệ, chốt từng phần
#   TƯỜNG      (>=66) — TP1 hợp lệ, yêu cầu volume phá cao hơn
BAT_SUPPLY_SCORE = True          # PHƯƠNG ÁN B — bật mặc định. False = quay lại v7.5.

# Lùi TP1 xuống dưới biên vùng để đảm bảo khớp lệnh — đừng đặt đúng giá tường.
TP1_LUI_ATR = 0.10

# ⚠️⚠️ ĐỌC KỸ TRƯỚC KHI DÙNG THẬT ⚠️⚠️
#
# 1) v7.6 BẬT là một bản NỚI LỎNG, không phải siết.
#    Bỏ qua vùng TRONG SUỐT và ĐỈNH BOX -> TP1 ra XA hơn -> R:R TĂNG ->
#    NHIỀU mã vượt chuẩn hơn. Đó ĐÚNG LÀ CHIỀU HỎNG CỦA v7.3 (thổi R:R).
#    Khác biệt duy nhất: v7.3 thổi vì một bộ lọc % tùy tiện, v7.6 thổi (nếu
#    có) vì một bộ điểm CÓ LÝ THUYẾT nhưng CHƯA ĐƯỢC KIỂM CHỨNG.
#    Lý thuyết đẹp không phải là bằng chứng.
#
# 2) Mọi đầu ra đều in SONG SONG R:R theo v7.5 và v7.6 (cột R:R_v75 và
#    Thổi×). Khi Thổi× >= 2.0, tinh_rr() tự bắn cảnh báo. ĐỪNG BỎ QUA NÓ —
#    đó là toàn bộ lớp bảo vệ còn lại khi chưa có backtest.
#
# 3) Trọng số dưới đây là GIẢ THUYẾT: 8 tham số + 3 ngưỡng, hiệu chỉnh tay
#    trên 12 mã của MỘT phiên = overfit gần như chắc chắn.
#    Chạy Ô 4C, đọc AUC PHÂN TẦNG (không phải AUC thô — AUC thô bị biến
#    "khoảng cách" át, đo trên dữ liệu ngẫu nhiên cho tới 0.91).
#       AUC phân tầng < 0.55 -> đặt BAT_SUPPLY_SCORE = False
#       AUC phân tầng > 0.75 -> nghi ngờ rò rỉ dữ liệu tương lai
#
# 4) KILL-SWITCH (cùng kỷ luật với chuyển A->B):
#    Sau 10 lệnh, nếu R trung bình < 0 VÀ >= 3 lệnh thua theo kiểu
#    "giá khựng ở một vùng mà Ô 4B chấm là TRONG SUỐT"
#    -> đặt BAT_SUPPLY_SCORE = False, KHÔNG chỉnh trọng số để cứu.
#
# 5) KHÓA trọng số cho tới khi có >= 200 mẫu có nhãn từ Ô 4C.
KC_THAM_SO = {
    # --- gộp cụm ---
    "khe_gop_atr":      0.50,   # hai mốc cách nhau <= mức này thì gộp
    "tran_rong_cum":    1.00,   # [VÁ M1] trần bề rộng cụm — chống chain-linking
    # --- Nhóm A: cung tại mốc (tối đa 55) ---
    "A1_max":           20.0,   # volume tạo đỉnh
    "A1_bao_hoa":       3.00,   # vol/volMA20 = 3.0 -> điểm tối đa
    "A2a_max":          12.0,   # TỶ LỆ volume từ chối
    "A2a_bao_hoa":      2.00,
    "A2b_max":           8.0,   # SỐ LẦN từ chối             [VÁ M3]
    "A2b_bao_hoa":         6,
    "A3_max":           15.0,   # độ mạnh cú bật ra
    "A3_bao_hoa":       2.00,   # bật 2.0xATR -> điểm tối đa
    # --- Nhóm B: cấu trúc (tối đa 29) ---
    "B1_tuan":          10.0,
    "B1_ngay_dong":      7.0,   # đỉnh ngày + >=3 close tụ trong dải
    "B1_ngay_than":      5.0,   # đỉnh ngày, thân nến chạm dải
    "B1_ngay_bong":      2.0,   # chỉ có bóng nến
    "B2_moi_ma":         4.0,   # hợp lưu MA
    "B2_max":           10.0,
    "B2_khe_atr":       0.25,
    "B4_moi_pivot":      3.0,   # độ dày cụm
    "B4_max":            9.0,
    # --- suy giảm theo tuổi (NHÂN vào A1 và A3, KHÔNG nhân vào A2) ---
    # Sự kiện đơn lẻ thì phai; hàng kẹp trong vùng thì không tự biến mất.
    "tau_ngay":         60.0,
    "san_decay_ngay":   0.30,
    "tau_tuan":        100.0,   # [VÁ M5] mốc tuần phai chậm hơn nhiều
    "san_decay_tuan":   0.50,
    # --- Nhóm C: lịch sử test (-15 .. +20) ---
    "C_box":             0.0,
    "C_pha_that_bai":   20.0,   # [VÁ M4] hàng kẹp tái tạo tường
    "C_hap_thu":       -15.0,   # vol cạn dần + đáy nâng = cung sắp hết
    "C_nen":           -10.0,
    "C_cung_that":      20.0,
    "C_mot_lan":         5.0,
    "C_chua_test":       8.0,   # [VÁ M5] chưa test = KHÔNG BIẾT, không phải yếu
    # --- ngưỡng nhận diện ---
    "bat_ra_toi_thieu_atr": 1.00,   # bật >= 1xATR mới tính là một lần từ chối
    "cua_so_box":            20,    # số nến xét run close-trên-dải
    "hap_thu_ty_le_vol":   0.75,    # vol lần cuối / lần đầu < mức này = cạn cung
    # --- phân hạng ---
    "nguong_mang":      36.0,
    "nguong_tuong":     66.0,
}
KC_TP1_DIEM_TOI_THIEU = KC_THAM_SO["nguong_mang"]   # TP1 tối thiểu hạng MÀNG
KC_VOL_PHA = {"TƯỜNG": 150, "MÀNG": 120, "TRONG SUỐT": 120}   # %MA20 để phá

print(f"SUPPLY_SCORE: {'BẬT' if BAT_SUPPLY_SCORE else 'TẮT (hành vi v7.5)'} "
      f"| TP1 tối thiểu {KC_TP1_DIEM_TOI_THIEU:g}đ (MÀNG) "
      f"| TƯỜNG >= {KC_THAM_SO['nguong_tuong']:g}đ")
print("  ⚠️ Trọng số CHƯA BACKTEST — chạy Ô 4C trước khi tin số điểm.")
print("=" * 66)

# ================================================================== #
# 2.12 KHUNG v3 — BỘ LỌC CỨNG + THOÁT LỆNH 2 TẦNG                    #
#      (Minervini · Weinstein · Kullamägi · O'Neil · Raschke)         #
# ------------------------------------------------------------------ #
# THAY ĐỔI KIẾN TRÚC LỚN NHẤT so với v2:
#
#   v2: chấm điểm 6 lớp có trọng số  →  ra quyết định
#       Hệ quả: một lớp mạnh "cứu" được một lớp đã gãy. FRT đứng #1 với 80
#       điểm trong khi R:R cấu trúc 0,07 và không có chỗ đặt stop.
#
#   v3: BỘ LỌC CỨNG pass/fail chạy TRƯỚC  →  điểm chỉ dùng để XẾP HẠNG
#       các mã ĐÃ SỐNG SÓT. Trượt bất kỳ bộ lọc nào = ĐỨNG NGOÀI, không
#       có điểm số nào cứu được.
#
#   v2: cổng R:R ≥ 2,0 tính đến TP1 (một mục tiêu giá CỐ ĐỊNH)
#       Đây là nguồn gốc của mọi deadlock đã gặp (VNM / HDB / MBB, và cả
#       9/10 mã "KẸP KHÁNG CỰ" phiên 28/08). Trong pha markup, kháng cự
#       gần nhất LUÔN ở ngay trên đầu → R:R luôn < 2 → chặn sạch.
#
#   v3: cổng chuyển sang KHOẢNG CÁCH STOP, không phải khoảng cách target.
#       Kullamägi bỏ lệnh khi stop rộng hơn ADR của mã; ông KHÔNG định
#       target trước. R:R là số ĐO SAU, không phải điều kiện lọc trước.
#       → xem SL_CUA_SO_ATR bên dưới (bộ lọc F5).
# ------------------------------------------------------------------ #
BAT_KHUNG_V3 = True        # False = quay lại hành vi v7.6 nguyên bản

# --- F1 · Giai đoạn Weinstein (khung TUẦN) --------------------------
MA_STAGE_TUAN         = 30      # MA30W — "trọng tài xu hướng" của Weinstein
STAGE_DOC_LEN_SO_TUAN = 4       # so MA30W hiện tại với 4 tuần trước
STAGE_DOC_NGUONG_PCT  = 0.50    # |độ dốc| <= mức này = ĐI NGANG (Stage 1/3)
STAGE_CHO_PHEP        = (2,)    # chỉ Stage 2 mới được mở vị thế mới

# --- F2 · Trend Template (Minervini) — hiệu chỉnh cho VN ------------
TT_MA200_DOC_SO_PHIEN = 21      # MA200 phải dốc lên >= ~1 tháng
TT_CACH_DAY_52W_MIN   = 25.0    # % — giá phải cao hơn đáy 52W ít nhất mức này
TT_CACH_DINH_52W_MAX  = 25.0    # % — giá không được thấp hơn đỉnh 52W quá mức này
TT_SO_DK_TOI_THIEU    = 8       # /8 — Minervini yêu cầu ĐỦ CẢ 8. Hạ xuống 7 là
                                # tự nới chuẩn: phải ghi log lý do nếu đổi.

# --- F3 · Xếp hạng dẫn dắt đa khung (Kullamägi) ---------------------
# Gốc: top 1-2% TOÀN THỊ TRƯỜNG Mỹ (vài nghìn mã) trên CẢ 3 khung 1T/3T/6T.
# Universe ở đây ĐÃ được lọc trước theo GTGD (~50 mã bluechip/midcap thanh
# khoản cao), nên top 20% của rổ này xấp xỉ top 3-5% của toàn sàn HOSE.
# Đặt 2% ở đây là ép lấy 1 mã — vô nghĩa về mặt thống kê.
RS_TOP_PCT      = 20.0          # phải nằm trong top X% ở CẢ BA khung
RS_KHUNG        = (21, 63, 126) # số phiên ~ 1 tháng / 3 tháng / 6 tháng
RS_DUONG_BAT_BUOC = True        # đồng thời phải KHỎE HƠN VNINDEX ở cả 3 khung

# Nền tảng: mã phải đã CHỨNG MINH được đợt tăng thứ nhất rồi mới cược đợt hai.
NEN_TANG_CUA_SO = 126           # cửa sổ xét (~6 tháng)
NEN_TANG_MIN_PCT = 30.0         # đợt tăng nền tảng tối thiểu
NEN_TANG_MAX_PCT = 200.0        # trên mức này: đã parabolic, không phải nền

# --- F4 · Thanh khoản & biên độ ------------------------------------
# ADR gốc của Kullamägi là > 5%. HOSE trần biên độ ±7% nên ADR 5% gần như
# không tồn tại ở nhóm thanh khoản cao → hạ về 2.5%.
ADR_TOI_THIEU_PCT = 2.5
ADR_SO_PHIEN      = 20

# --- F5 · CỔNG CHẤT LƯỢNG ĐIỂM VÀO  (THAY CHO CỔNG R:R) ------------
# Stop quá CHẶT  -> T+2.5 giết lệnh bằng nhiễu (đã có sàn 1.5×ATR ở v7.x)
# Stop quá RỘNG  -> nền chưa siết, CHƯA PHẢI điểm vào -> chờ, không mua
SL_CUA_SO_ATR   = (1.5, 2.5)    # khoảng cách stop hợp lệ, tính bằng ATR14
SL_TOI_DA_PCT   = 8.0           # đồng thời <= 8% giá vào (quy tắc Minervini)
EP_SL_TOI_DA_ATR = 3.0          # riêng setup EP được nới trần (kỳ vọng cao hơn)

# R:R KHÔNG còn là cổng chặn. Giữ lại để ĐO và GHI LOG.
RR_LA_CONG_CHAN = False         # True = quay lại hành vi v7.6

# --- Nhận diện setup ------------------------------------------------
# A · Breakout nền co thắt (VCP / flat base)
BO_NEN_CUA_SO      = 40         # số phiên xét nền (~8 tuần)
BO_NEN_SO_DOAN     = 3          # chia nền thành 3 đoạn để đo co thắt
BO_NEN_CO_THAT_TY  = 0.85       # đoạn sau phải <= 85% biên độ đoạn trước
BO_VOL_PCT         = 150.0      # vol phá vỡ đạt chuẩn (Weinstein đòi 200-300%
                                # ở Mỹ; VN biên ±7% làm loãng spike → 150%)
BO_VOL_PCT_TOI_THIEU = 120.0    # dưới mức này: breakout CHẤT LƯỢNG THẤP

# B · Episodic Pivot phiên bản Việt Nam
# Gốc: gap >= 10% + vol >= 10x. HOSE không cho gap 10% → dùng phiên gần trần.
EP_TANG_PCT_MIN    = 5.0        # phiên tăng >= 5% (gần trần / kịch trần)
EP_VOL_LAN         = 5.0        # vol >= 5x MA20
EP_CUA_SO_PHIEN    = 5          # EP phải xảy ra trong 5 phiên gần nhất
EP_NGU_QUEN_PHIEN  = 63         # trước đó >= 3 tháng đi ngang/giảm
EP_NGU_QUEN_BIEN_PCT = 25.0     # biên độ giai đoạn ngủ quên < 25% = "bị lãng quên"

# C · Pullback về MA (Raschke "Holy Grail")
ADX_TOI_THIEU      = 30.0
PULLBACK_MA        = (10, 20)   # chạm MA10 hoặc MA20 ngày
PULLBACK_KHE_PCT   = 2.0        # |close/MA - 1| <= 2% coi là đang test MA

# --- THOÁT LỆNH 2 TẦNG (thay TP1/TP2 cứng) -------------------------
TP_TANG1_R        = 2.0         # bán tầng 1 khi đạt +2R ...
TP_TANG1_PHIEN    = (3, 5)      # ... HOẶC vào đợt mạnh đầu tiên 3-5 phiên
TY_LE_BAN_TANG1   = 0.5         # bán 1/2 (Kullamägi: 1/3 - 1/2)
MA_TRAIL          = 20          # trail phần còn lại theo MA20 ngày
MA_TRAIL_NHANH    = 10          # mã biến động nhanh / người mới: MA10
# Sau tầng 1: dời stop phần còn lại về HOÀ VỐN. Thoát khi ĐÓNG CỬA dưới MA trail.

# --- Tín hiệu thoát chủ động (thay setup parabolic short) ----------
# VN không bán khống được → chuyển thành tín hiệu THOÁT cho vị thế long.
PARA_TANG_PCT     = 50.0        # tăng >= 50% trong ...
PARA_CUA_SO       = 15          # ... 15 phiên
PARA_CHUOI_XANH   = 3           # >= 3 phiên tăng liên tiếp
PARA_VOL_CLIMAX   = 300.0       # vol >= 300% MA20 tại đỉnh

# --- PROGRESSIVE EXPOSURE (Minervini) ------------------------------
# Vào bằng vị thế THĂM DÒ để lấy phản hồi thị trường, chỉ tăng size khi
# các lệnh nhỏ bắt đầu chạy. Đây là cách hệ số bậc của Khung v2 nên vận hành.
RUI_RO_PCT_THAM_DO     = 0.25   # 2+ lệnh thua liên tiếp, hoặc cổng nhanh ĐÓNG
RUI_RO_PCT_BINH_THUONG = 0.50   # mặc định
RUI_RO_PCT_TOI_DA      = 1.00   # 2+ lệnh thắng liên tiếp VÀ cổng nhanh MỞ
# ⚠️ Ba mức trên THAY THẾ RUI_RO_MOI_LENH_PCT (2.1) khi BAT_KHUNG_V3 = True.
#    Ô 7 tính RUI_RO_V3 mỗi phiên và truyền vào tinh_size(). Sửa 2.1 sẽ KHÔNG
#    có tác dụng gì nếu v3 đang bật — sửa ba dòng này.
# R của 5-10 lệnh ĐÃ ĐÓNG gần nhất, cũ -> mới. Ví dụ: [-1.0, 2.3, -1.0, 4.1]
# Để RỖNG nếu chưa có lịch sử -> hệ thống dùng mức BÌNH THƯỜNG.
CHUOI_R_GAN_NHAT = _env_json("CHUOI_R_GAN_NHAT", [])     # secret

# --- CỔNG NHANH MA10/MA20 CỦA CHỈ SỐ (Kullamägi) -------------------
# Kullamägi ước tính: tuân thủ đúng bộ lọc này sẽ cắt ~90% khoản lỗ 2022.
# DE_RISK (MA20W) là tầng CHẬM; MA10/MA20 ngày là tầng NHANH.
BAT_CONG_MA1020   = True
F_MA1020_KHI_DUOI = 0.25        # MA10 < MA20 -> ngân sách × 0.25

# --- SỔ NHẬT KÝ & KỲ VỌNG (Phần 8 của prompt v3) -------------------
DUONG_DAN_NHATKY   = f"{THU_MUC}/nhat_ky_lenh.csv"
KY_VONG_MAU_TOI_THIEU = 20      # dưới 20 lệnh: mọi thống kê chỉ là nhiễu
GAIN_LOSS_MUC_TIEU = 2.0        # Avg Gain / Avg Loss, lý tưởng >= 3.0
BATTING_MUC_TIEU   = 35.0       # % — với G/L >= 2 thì 35% là đủ để dương

# --- Trọng số 6 lớp bản v3 (chỉ để XẾP HẠNG, KHÔNG BAO GIỜ để chặn) -
# v2: 30/25/20/10/10/5.  Thay đổi và lý do:
#   Lớp 2 Động lượng  25 -> 15 : F3 (xếp hạng RS đa khung) đã gánh phần lớn
#                                vai trò này; RSI/MACD là chỉ báo TRỄ.
#   Lớp 3 Dòng tiền   20 -> 25 : KN10 là bằng chứng tổ chức THẬT.
#   Lớp 4 Liên thị    10 -> 15 : mã mạnh trong ngành mạnh bền hơn nhiều.
#   Lớp 5 Cơ bản      10 ->  0 : chuyển thành BỘ LỌC F6 (nhập tay).
#   Lớp 1 Cấu trúc    30 -> 35 : cộng thêm chất lượng nền co thắt.
TRONG_SO_V3 = {"L1": 35, "L2": 15, "L3": 25, "L4": 15, "L6": 10}
# Tổng trọng số các lớp CÓ dữ liệu phải đạt mức này mới được chấm điểm.
# Dưới ngưỡng -> ĐiểmV3 = None (không biết), KHÔNG phải điểm cao.
MAU_TOI_THIEU_CHAM_DIEM = 50

# --- F6 · Cơ bản (nhập tay — không có API tin cậy trong notebook) ---
# {"MÃ": {"eps_yoy": 25.0, "catalyst": "mô tả"}}  — thiếu = hạ 1 bậc, KHÔNG suy diễn
CO_BAN_TAY = _env_json("CO_BAN_TAY", {})                 # secret (F6)
EPS_YOY_TOI_THIEU = 20.0

assert SL_CUA_SO_ATR[0] >= SL_TOI_THIEU_ATR - 1e-9, (
    "SL_CUA_SO_ATR[0] < SL_TOI_THIEU_ATR — cửa sổ F5 nằm dưới sàn ATR của "
    "khung, sẽ không bao giờ có mã nào lọt.")
assert SL_CUA_SO_ATR[1] <= NGUONG_KICH_HOAT_SL_CAP + 1e-9, (
    "SL_CUA_SO_ATR[1] > ngưỡng kích hoạt SL_CAP — F5 sẽ nhận cả stop đã bị cap.")

print("-" * 66)
print(f"KHUNG v3: {'BẬT' if BAT_KHUNG_V3 else 'TẮT (hành vi v7.6)'}"
      f" | R:R là cổng chặn: {RR_LA_CONG_CHAN}")
print(f"  F1 Stage {STAGE_CHO_PHEP} (MA{MA_STAGE_TUAN}W) | F2 Trend Template "
      f"{TT_SO_DK_TOI_THIEU}/8 | F3 top {RS_TOP_PCT:g}% ở cả {len(RS_KHUNG)} khung")
print(f"  F4 ADR ≥ {ADR_TOI_THIEU_PCT:g}% | F5 stop ∈ "
      f"[{SL_CUA_SO_ATR[0]:g}, {SL_CUA_SO_ATR[1]:g}]×ATR và ≤ {SL_TOI_DA_PCT:g}%")
print(f"  Thoát: bán {TY_LE_BAN_TANG1:.0%} tại +{TP_TANG1_R:g}R hoặc đợt mạnh "
      f"{TP_TANG1_PHIEN[0]}-{TP_TANG1_PHIEN[1]} phiên → hoà vốn → trail MA{MA_TRAIL}")
print(f"  Progressive exposure: {RUI_RO_PCT_THAM_DO:g}% / "
      f"{RUI_RO_PCT_BINH_THUONG:g}% / {RUI_RO_PCT_TOI_DA:g}% NAV mỗi lệnh")
print("=" * 66)

# ======================================================================
# Ô 3 — RATE LIMITER + TẦNG LẤY DỮ LIỆU
# ======================================================================
import time
import re
import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime, timedelta


# ---------------------------------------------------------------- #
# [SỬA v7.4 — BUG G]  LỖI CHÍ MẠNG CỦA v7.3                        #
# ---------------------------------------------------------------- #
# vnstock KHÔNG raise một Exception bình thường khi hết quota. Trong
# vnai/beam/quota.py, CleanErrorContext.__exit__ gọi thẳng sys.exit(...)
# -> sinh ra SystemExit, mà SystemExit kế thừa BaseException, KHÔNG kế thừa
# Exception.
# Hệ quả: mọi `except Exception` trong Ô 3 và Ô 7 KHÔNG bắt được nó.
#   - vòng retry rate-limit của lay_du_lieu() không bao giờ chạy
#   - vòng quét 75 mã chết đứng ở mã thứ 15, mất sạch 14 mã đã tải
#   - traceback còn kéo theo lỗi phụ của IPython ('tuple' object has no
#     attribute 'f_lineno') làm che mất nguyên nhân thật.
# Cách vá: bắt BaseException, bóc ra thành LoiGioiHan (một Exception thật)
# rồi để các tầng trên xử lý như mọi lỗi khác. KeyboardInterrupt vẫn phải
# được ném tiếp — nếu nuốt luôn thì không dừng tay được nữa.
class LoiGioiHan(Exception):
    """Rate limit đã được bóc ra khỏi SystemExit của vnstock."""
    def __init__(self, cho=None, goc=None):
        self.cho = cho
        self.goc = goc
        super().__init__(f"Rate limit — cần chờ ~{cho}s")


_RE_CHO = re.compile(r"Ch[ờo]\s+(\d+)\s*gi[âa]y")


def _la_gioi_han(e):
    t = f"{type(e).__name__} {e}"
    return ("RateLimit" in t or "rate limit" in t.lower()
            or "GIỚI HẠN API" in t or "Rate limit exceeded" in t)


def _giay_cho(e, mac_dinh=None):
    m = _RE_CHO.search(str(e))
    if m:
        return min(int(m.group(1)) + 8, 120)
    return mac_dinh if mac_dinh is not None else CHO_KHI_LIMIT


class BoDieuTiet:
    """Giữ số request dưới GIOI_HAN_RPM trong mọi cửa sổ 60 giây."""

    def __init__(self, rpm):
        self.rpm = rpm
        self.moc = deque()

    def giam_toc(self, ly_do=""):
        """Dính limit dù đã điều tiết -> cửa sổ của ta lệch pha với của họ.
        Hạ tốc vĩnh viễn cho phần còn lại của phiên thay vì cứ đâm vào tường."""
        cu = self.rpm
        self.rpm = max(GIOI_HAN_RPM_SAN, int(self.rpm * 0.6))
        if self.rpm != cu:
            print(f"   🐢 Hạ tốc {cu} → {self.rpm} req/phút {ly_do}")
        return self.rpm

    def cho_phep(self):
        now = time.time()
        while self.moc and now - self.moc[0] > 60:
            self.moc.popleft()
        if len(self.moc) >= self.rpm:
            cho = 61 - (now - self.moc[0])
            if cho > 0:
                print(f"   ⏸ Điều tiết: chờ {cho:.0f}s (giữ dưới {self.rpm} req/phút)")
                time.sleep(cho)
            now = time.time()
            while self.moc and now - self.moc[0] > 60:
                self.moc.popleft()
        self.moc.append(time.time())


DIEU_TIET = BoDieuTiet(GIOI_HAN_RPM)

_START = (datetime.now() - timedelta(days=int(SO_PHIEN * 1.6))).strftime("%Y-%m-%d")
# [VÁ LỖI 10] +1 ngày: một số nguồn coi `end` là KHÔNG bao gồm -> mất phiên cuối.
_END = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

NGAY_MOC = None   # ngày nến cuối của VNINDEX — chuẩn để đối chiếu độ tươi


def _chuan_hoa(df, toi_thieu=60):
    if df is None or len(df) < toi_thieu:
        return None
    df = df.rename(columns=str.lower)
    if "time" not in df.columns:
        for c in ("date", "tradingdate", "index"):
            if c in df.columns:
                df = df.rename(columns={c: "time"})
                break
    if "time" not in df.columns:
        return None
    # [VÁ LỖI 11] Nguồn có thể trả 2 dòng cho CÙNG một ngày: snapshot trong phiên
    # + nến chốt phiên (open/volume khác nhau). Nếu để nguyên: vol tuần cộng đôi,
    # MA/RSI/MACD lệch, quy tắc "2 phiên liên tiếp" so 2 bản sao cùng ngày.
    # -> Chuẩn hóa timestamp về NGÀY, giữ dòng có VOLUME LỚN NHẤT (bản đầy đủ
    #    nhất của phiên, vì volume chỉ tăng dần trong ngày).
    df["time"] = pd.to_datetime(df["time"]).dt.normalize()
    df = (df.sort_values(["time", "volume"])
            .drop_duplicates(subset="time", keep="last")
            .sort_values("time").reset_index(drop=True))
    # KHÔNG chia 1000 bất kỳ trường hợp nào — đây là lỗi của v4.
    return df


def _goi_api_tho(ma, src, toi_thieu=60):
    from vnstock.api.quote import Quote
    try:
        q = Quote(symbol=ma, source=src)
        return _chuan_hoa(q.history(start=_START, end=_END, interval="1D"), toi_thieu)
    except ImportError:
        from vnstock import Vnstock
        return _chuan_hoa(
            Vnstock().stock(symbol=ma, source=src).quote.history(
                start=_START, end=_END, interval="1D"), toi_thieu)


def _goi_api(ma, src, toi_thieu=60):
    """[SỬA v7.4 — BUG G] Bắt BaseException để chặn SystemExit của vnstock."""
    DIEU_TIET.cho_phep()
    try:
        return _goi_api_tho(ma, src, toi_thieu)
    except KeyboardInterrupt:
        raise                                   # phải để người dùng dừng được
    except BaseException as e:                  # SystemExit KHÔNG phải Exception
        if _la_gioi_han(e):
            raise LoiGioiHan(_giay_cho(e), e) from None
        if isinstance(e, SystemExit):
            raise RuntimeError(
                f"vnstock gọi sys.exit() ngoài ngữ cảnh rate-limit: {e}") from None
        raise


def lay_du_lieu(ma, src, toi_thieu=60):
    """Thử lại có backoff khi dính rate limit; tự hạ tốc sau mỗi lần dính."""
    for lan in range(1, SO_LAN_THU_GIOI_HAN + 1):
        try:
            return _goi_api(ma, src, toi_thieu)
        except LoiGioiHan as e:
            if lan == SO_LAN_THU_GIOI_HAN:
                print(f"   ⛔ {ma}: bỏ qua sau {lan} lần dính rate limit.")
                return None
            DIEU_TIET.giam_toc(f"({ma}, lần {lan})")
            cho = e.cho * lan                   # backoff tuyến tính
            print(f"   ⏳ {ma}: rate limit — chờ {cho}s "
                  f"(thử {lan + 1}/{SO_LAN_THU_GIOI_HAN})")
            time.sleep(cho)
        except KeyboardInterrupt:
            raise
        except Exception:
            return None
    return None


def do_nguon():
    """Chọn nguồn trả VNINDEX có nến MỚI NHẤT, đặt NGAY_MOC."""
    global NGAY_MOC
    tot = tot_src = None
    tot_ngay = None
    for src in NGUON_UU_TIEN:
        try:
            # [SỬA v7.4 — BUG G] dùng lay_du_lieu() để có retry rate-limit;
            # bản cũ gọi thẳng _goi_api rồi `except Exception` -> SystemExit
            # lọt lưới ngay ở TẦNG 0, giết cả Ô 7 trước khi quét mã nào.
            df = lay_du_lieu("VNINDEX", src, toi_thieu=200)
        except KeyboardInterrupt:
            raise
        except Exception:
            time.sleep(3)
            continue
        if df is None:
            continue
        ngay = pd.to_datetime(df["time"]).max()
        if tot_ngay is None or ngay > tot_ngay:
            tot, tot_ngay, tot_src = df, ngay, src
    if tot is not None:
        NGAY_MOC = tot_ngay
        print(f"   Mốc phiên chuẩn (VNINDEX): {NGAY_MOC:%d/%m/%Y} — nguồn {tot_src}")
    return tot_src, tot


def lay_du_lieu_moi_nhat(ma, toi_thieu=60):
    """
    [VÁ LỖI 10] Trả (df, nguồn, ngày_cuối, bị_cũ).
    Nếu nguồn chính trả nến cũ hơn NGAY_MOC -> thử nguồn còn lại, giữ bản mới nhất.
    """
    tot = tot_src = tot_ngay = None
    ds_nguon = [NGUON] + [s for s in NGUON_UU_TIEN if s != NGUON] \
        if THU_NGUON_KHAC_KHI_CU else [NGUON]
    for src in ds_nguon:
        df = lay_du_lieu(ma, src, toi_thieu)
        if df is None:
            continue
        ngay = pd.to_datetime(df["time"]).max()
        if tot_ngay is None or ngay > tot_ngay:
            tot, tot_ngay, tot_src = df, ngay, src
        if NGAY_MOC is not None and ngay >= NGAY_MOC:
            break
    if tot is None:
        return None, None, None, True
    bi_cu = bool(NGAY_MOC is not None and tot_ngay < NGAY_MOC)
    return tot, tot_src, tot_ngay, bi_cu


print("✅ Ô 3 v7.4 — bắt SystemExit của vnstock [BUG G], backoff + tự hạ tốc")
print(f"   Điều tiết: {GIOI_HAN_RPM} req/phút (sàn {GIOI_HAN_RPM_SAN}), "
      f"thử lại tối đa {SO_LAN_THU_GIOI_HAN} lần")
print(f"   Khoảng tải: {_START} → {_END}  (end +1 ngày để không mất phiên cuối)")

# ======================================================================
# Ô 4 — CỔNG DE_RISK ĐỘNG + PIVOT + R:R          [v7.2]
#   [VÁ 3] TP không bao giờ dùng mốc cổng. SL tách khỏi INVALIDATION.
#   [VÁ 4] DE_RISK_LEVEL = max(MA20W, MA200D), tính lại mỗi lần chạy.
#   --- MỚI v7.2 ---
#   [VÁ 12] SL_CAP: SL không được xa hơn SL_TOI_DA_ATR_CAP × ATR14.
#           Bản cũ chỉ có SÀN (1.5×ATR), không có TRẦN -> mã momentum
#           không có đáy pivot gần bị gán SL cách 30% (FRT) -> R:R chết oan.
#   [VÁ 13] LY_DO_TRUOT: nêu đích danh vì sao DAT_RR=False.
#           Bản cũ luôn in "R:R x < 2.0" kể cả khi trượt vì BREAKOUT
#           -> sinh câu vô lý "R:R 2.5 < 2.0" (ca STB 26/08).
#   [VÁ 14] GIA_TRAN_RR (tên cũ VùngVào): trả None khi BREAKOUT vì TP1
#           phụ thuộc chính giá -> công thức vùng vào là tự quy chiếu.
#           Thêm cờ DA_TRONG_VUNG khi giá hiện tại đã thỏa.
#   [VÁ 15] gop_tuan(bo_tuan_dang_chay=True): pivot tuần không được tính
#           trên nến tuần chưa đóng.
# ======================================================================
import pandas as pd
import numpy as np


# ---------------------------------------------------------------- #
# 4.1 CỔNG CHẾ ĐỘ                                                   #
# ---------------------------------------------------------------- #
def tinh_de_risk(df_idx, cot_ngay="time", cot_gia="close"):
    """df_idx: VNINDEX khung NGÀY, >= 200 phiên. Trả dict trạng thái cổng."""
    if df_idx is None or len(df_idx) == 0:
        raise ValueError("df_idx rỗng — kiểm tra bước tải dữ liệu VNINDEX.")

    thieu = [c for c in (cot_ngay, cot_gia) if c not in df_idx.columns]
    if thieu:
        raise KeyError(f"Thiếu cột {thieu}. Cột hiện có: {list(df_idx.columns)}")

    df = df_idx[[cot_ngay, cot_gia]].copy()
    df[cot_ngay] = pd.to_datetime(df[cot_ngay]).dt.normalize()
    df = (df.dropna()
            .drop_duplicates(subset=cot_ngay, keep="last")
            .sort_values(cot_ngay)
            .set_index(cot_ngay))
    gia = df[cot_gia].astype(float) * HE_SO_QUY_DOI_IDX

    canh_bao = []

    lo, hi = BIEN_HOP_LE_IDX
    if not (lo <= gia.iloc[-1] <= hi):
        raise ValueError(
            f"Giá VNINDEX = {gia.iloc[-1]:,.2f} ngoài biên [{lo}-{hi}]. "
            f"Nhiều khả năng HE_SO_QUY_DOI_IDX sai (phải = 1).")

    if len(gia) < 200:
        raise ValueError(f"Cần >= 200 phiên cho MA200D, hiện có {len(gia)}. "
                         f"Tăng SO_PHIEN (đang là {SO_PHIEN}).")
    ma200d = gia.tail(200).mean()

    tuan = gia.resample(NEO_TUAN).last().dropna()
    if DUNG_TUAN_HOAN_CHINH and len(tuan) > 0:
        ngay_cuoi = gia.index[-1]
        if ngay_cuoi < tuan.index[-1]:
            tuan = tuan.iloc[:-1]
            canh_bao.append(
                f"Đã loại tuần đang chạy dở (phiên cuối {ngay_cuoi:%d/%m/%Y}). "
                f"Mốc cổng giữ nguyên tới đóng cửa tuần.")
    if len(tuan) < 20:
        raise ValueError(f"Cần >= 20 tuần cho MA20W, hiện có {len(tuan)}.")
    ma20w = tuan.tail(20).mean()

    de_risk = max(ma20w, ma200d)
    gia_ht = float(gia.iloc[-1])

    if ma200d >= ma20w:
        canh_bao.append("MA200D đang là SÀN (MA20W đã rơi dưới MA200D).")

    # [VÁ 16 + SỬA v7.4 — BUG C] Bộ đệm cổng.
    # LỖI v7.3: luôn đo bằng ATR NGÀY, kể cả khi mốc neo là MA20W (khung TUẦN).
    #   VNINDEX 28/08: 10,81 / ATR_D 27,02 = 0,400×ATR  -> nghe như "hơi mỏng"
    #   đo đúng khung: 10,81 / ATR_W 73,53 = 0,147×ATR_W -> thực chất là NHIỄU.
    # Mốc neo khung nào thì đo bằng ATR khung đó.
    atr_ngay = float(atr14(df_idx))
    atr_tuan = float(atr14_tuan(df_idx))
    neo_la_tuan = bool(ma20w >= ma200d)
    if neo_la_tuan and np.isfinite(atr_tuan) and atr_tuan > 0:
        atr_idx, khung_atr = atr_tuan, "ATR_W"
    else:
        atr_idx, khung_atr = atr_ngay, "ATR_D"
    day_cong = (gia_ht - float(de_risk)) / atr_idx if atr_idx > 0 else np.nan
    muc_cong_day = float(de_risk) + BUFFER_CONG_ATR * atr_idx
    cong_mo = bool(gia_ht >= de_risk)
    cong_day = bool(gia_ht >= muc_cong_day)
    if cong_mo and not cong_day:
        canh_bao.append(
            f"CỔNG MỎNG: chỉ vượt {gia_ht - float(de_risk):+,.2f} điểm "
            f"= {day_cong:.3f}×{khung_atr} (< {BUFFER_CONG_ATR}×ATR, "
            f"đo bằng ATR khung của mốc neo {'MA20W' if neo_la_tuan else 'MA200D'}). "
            f"Trần NAV thực tế nên giảm còn {TRAN_NAV_CONG_MONG}% cho tới khi "
            f"đóng cửa ≥ {muc_cong_day:,.2f}.")

    return {
        "NGAY": gia.index[-1].strftime("%d/%m/%Y"),
        "GIA": round(gia_ht, 2),
        "MA20W": round(float(ma20w), 2),
        "MA200D": round(float(ma200d), 2),
        "NEO": "MA20W" if ma20w >= ma200d else "MA200D",
        "DE_RISK_LEVEL": round(float(de_risk), 2),
        "CONG_MO": cong_mo,
        "CONG_DAY": cong_day,
        "MUC_CONG_DAY": round(muc_cong_day, 2),
        "DAY_CONG_ATR": round(float(day_cong), 3) if np.isfinite(day_cong) else None,
        "KHUNG_ATR": khung_atr,
        "ATR_IDX": round(float(atr_idx), 2),
        "ATR_NGAY": round(atr_ngay, 2),
        "ATR_TUAN": round(atr_tuan, 2) if np.isfinite(atr_tuan) else None,
        "KHOANG_CACH": round(gia_ht - float(de_risk), 2),
        "canh_bao": canh_bao,
    }


# ---------------------------------------------------------------- #
# 4.2 PIVOT — nền tảng cho SL/TP cấu trúc                           #
# ---------------------------------------------------------------- #
def tim_pivot(df, n=5, lookback=None):
    """
    Trả (đỉnh, đáy) đã XÁC NHẬN, mỗi phần tử là (thời_gian, giá).
    n nến cuối bị loại vì chưa xác nhận.
    [VÁ 8] lookback giới hạn cửa sổ — pivot quá cũ không còn là cấu trúc sống.
    """
    d = df.tail(lookback) if lookback else df
    d = d.reset_index(drop=True)
    h = d["high"].to_numpy(dtype=float)
    l = d["low"].to_numpy(dtype=float)
    t = (pd.to_datetime(d["time"]) if "time" in d.columns
         else pd.Series(pd.RangeIndex(len(d))))
    dinh, day = [], []
    for i in range(n, len(h) - n):
        if h[i] == h[i - n:i + n + 1].max():
            dinh.append((t.iloc[i], float(h[i])))
        if l[i] == l[i - n:i + n + 1].min():
            day.append((t.iloc[i], float(l[i])))
    return dinh, day


def gop_tuan(df, bo_tuan_dang_chay=False):
    """
    [VÁ 15] bo_tuan_dang_chay=True -> loại nến tuần chưa đóng.
    Dùng cho MỌI phép tính cấu trúc tuần (pivot, MA10W, kiểm tra GÃY).
    Để False khi chỉ hiển thị bảng nến cho người đọc.
    """
    w = df.copy()
    w["time"] = pd.to_datetime(w["time"])
    ngay_cuoi = w["time"].max()
    out = (w.set_index("time").resample(NEO_TUAN)
             .agg({"open": "first", "high": "max", "low": "min",
                   "close": "last", "volume": "sum"})
             .dropna().reset_index())
    if bo_tuan_dang_chay and len(out):
        if ngay_cuoi < pd.to_datetime(out["time"].iloc[-1]):
            out = out.iloc[:-1].reset_index(drop=True)
    return out


# ---------------------------------------------------------------- #
# 4.3 R:R  [TRỌNG TÂM]                                              #
# ---------------------------------------------------------------- #
def tinh_rr(df_ngay, gia, atr=None, de_risk_level=None,
            tp_min_pct=3.0, sl_min_pct=1.0,
            n_ngay=None, n_tuan=None, rr_min=None):
    """
    SL  = pivot ĐÁY xác nhận GẦN NHẤT THEO THỜI GIAN nằm dưới giá,
          SÀN  = max(sl_min_pct, SL_TOI_THIEU_ATR × ATR14)   [VÁ 9] sống qua T+2.5
          TRẦN = SL_TOI_DA_ATR_CAP × ATR14                   [VÁ 12] chống SL chết oan
    TP  = pivot ĐỈNH xác nhận thấp nhất trên giá (kháng cự gần nhất).
          Không có -> đỉnh 52W -> vẫn không có = BREAKOUT, measured move.

    KHÔNG dùng DE_RISK_LEVEL làm TP, KHÔNG dùng INVALIDATION làm SL.
    """
    rr_min_gan = RR_TOI_THIEU if rr_min is None else rr_min
    n_ngay = n_ngay or PIVOT_N_NGAY
    n_tuan = n_tuan or PIVOT_N_TUAN
    if atr is None or not np.isfinite(atr) or atr <= 0:
        atr = atr14(df_ngay)

    d_dinh, d_day = tim_pivot(df_ngay, n_ngay, LOOKBACK_PIVOT_NGAY)
    try:
        # [VÁ 15] pivot tuần chỉ tính trên tuần ĐÃ ĐÓNG
        w_dinh, w_day = tim_pivot(gop_tuan(df_ngay, bo_tuan_dang_chay=True),
                                  n_tuan, LOOKBACK_PIVOT_TUAN)
    except Exception:
        w_dinh, w_day = [], []

    dinh = sorted(d_dinh + w_dinh, key=lambda x: x[0])
    day = sorted(d_day + w_day, key=lambda x: x[0])
    canh_bao = []

    # ---------------- SL: SÀN ----------------
    khoang_toi_thieu = max(gia * sl_min_pct / 100, SL_TOI_THIEU_ATR * atr)
    tran_sl = gia - khoang_toi_thieu
    sl_hop_le = [(t, p) for t, p in day if p <= tran_sl]
    sl_pivot_goc = None
    if sl_hop_le:
        t_sl, sl = sl_hop_le[-1]          # GẦN NHẤT theo thời gian
        ngay_sl = pd.Timestamp(t_sl).strftime("%d/%m/%Y")
        gan_hon = [p for t, p in day if tran_sl < p < gia]
        if gan_hon:
            canh_bao.append(
                f"Có đáy gần hơn ({max(gan_hon):,.2f}) nhưng cách giá "
                f"< {SL_TOI_THIEU_ATR}×ATR — quá sát, không sống qua T+2.5. "
                f"Đã lùi SL về đáy {ngay_sl}.")
    else:
        sl = tran_sl
        ngay_sl = "—"
        canh_bao.append(f"Không có đáy pivot đủ xa — SL đặt theo sàn ATR "
                        f"({SL_TOI_THIEU_ATR}×ATR = {khoang_toi_thieu:,.2f}).")

    # ---------------- SL: TRẦN  [VÁ 12 — SỬA v7.3] ----------------
    # Cap CHỈ kích hoạt khi pivot vượt NGUONG_KICH_HOAT_SL_CAP (mốc "hết cấu trúc").
    # Trong vùng [sàn, ngưỡng kích hoạt] pivot vẫn SỐNG -> giữ nguyên, không đụng.
    sl_goc_luon = float(sl)                       # luôn giữ SL cấu trúc để đối chiếu
    do_rong_goc = (gia - sl_goc_luon) / atr if atr > 0 else np.nan
    muc_kich_hoat = gia - NGUONG_KICH_HOAT_SL_CAP * atr
    sl_cap = False
    # [SỬA v7.4 — BUG A] Chốt chặn cứng: cap KHÔNG BAO GIỜ được chặt hơn ngưỡng
    # kích hoạt, nếu không R bị cắt ngắn -> R:R tự phồng lên (v7.3: 0,49 -> 0,84).
    _cap_atr = max(SL_TOI_DA_ATR_CAP, NGUONG_KICH_HOAT_SL_CAP)
    if sl < muc_kich_hoat:
        sl_pivot_goc = round(sl_goc_luon, 2)
        sl = gia - _cap_atr * atr
        sl_cap = True
        ngay_sl = f"ATR-CAP (pivot gốc {sl_pivot_goc:,.2f} — {do_rong_goc:.1f}×ATR)"
        canh_bao.append(
            f"SL_ATR: đáy pivot {sl_pivot_goc:,.2f} cách giá {do_rong_goc:.1f}×ATR "
            f"— vượt ngưỡng {NGUONG_KICH_HOAT_SL_CAP}×ATR (hết cấu trúc). "
            f"Cap SL về {sl:,.2f} ({_cap_atr:g}×ATR — ĐÚNG mốc hết cấu trúc, "
            f"không cắt ngắn thêm). "
            f"Đây là stop RỦI RO, không phải stop CẤU TRÚC: xác suất bị quét cao hơn "
            f"→ ngưỡng R:R nâng lên {RR_TOI_THIEU_KHI_SL_CAP} và size ×{HE_SO_SIZE_KHI_SL_CAP}.")

    do_rong_atr = (gia - sl) / atr if atr > 0 else np.nan

    # ---------------- TP  [v7.6 — BẢN ĐỒ KHÁNG CỰ CÓ TRỌNG SỐ] ----------------
    # LỊCH SỬ BA ĐỜI CỦA BUG NÀY:
    #   v7.3 THỔI R:R  — dùng % làm bộ lọc LOẠI kháng cự -> TP1 nhảy cóc.
    #   v7.4 BÓP R:R   — bỏ lọc %, nhận cả vi-pivot -> TP1 dính sát giá.
    #   v7.5 phân loại KẸP KHÁNG CỰ — đúng khái niệm, nhưng vẫn coi MỌI đỉnh
    #        pivot là ngang nhau, nên sinh KẸP GIẢ: bóng nến volume 40% MA20
    #        chặn TP1 trong khi tường thật nằm xa hơn 3xATR.
    #   v7.6 CHẤM ĐIỂM CUNG cho từng VÙNG (Ô 4B) rồi mới chọn.
    #
    # Đo trên phiên 28/08/2026: 10/12 mã bị gắn KẸP. Chấm điểm tay 4 vùng
    # kháng cự của FRT cho điểm cao nhất 44/100 -> KHÔNG có tường thật nào,
    # "kẹp" của FRT là KẸP GIẢ. VNM ngược lại: vùng 63.00-63.30 là PHÁ THẤT
    # BẠI 4 phiên trước (17,89 triệu CP = 4,17x nền đang kẹt) -> kẹp THẬT.
    khe_min = max(TP_KHE_TOI_THIEU_ATR * atr, gia * 0.001)

    # Danh sách pivot thô — chỉ còn dùng cho dòng chẩn đoán so sánh với v7.3
    tat_ca_tp = sorted(set(p for _, p in dinh if p >= gia + khe_min))
    bi_bo_qua_boi_v73 = [p for p in tat_ca_tp
                         if p < gia * (1 + tp_min_pct / 100)]

    vung_kc, tp1_vung, tp_nguon = [], None, "PIVOT_THO_v75"
    ung_vien_vung = []
    tp1 = tp2 = None
    breakout = False
    trong_box = False

    if BAT_SUPPLY_SCORE:
        if "ban_do_khang_cu" not in globals():
            raise NameError(
                "BAT_SUPPLY_SCORE=True nhưng chưa chạy Ô 4B. "
                "Thứ tự đúng: Ô 4 → Ô 4B → Ô 5. "
                "(Hoặc đặt BAT_SUPPLY_SCORE=False ở Ô 2 để dùng lại v7.5.)")
        _dn = pivot_dinh_meta(df_ngay, n_ngay, LOOKBACK_PIVOT_NGAY, "NGAY")
        try:
            _w = gop_tuan(df_ngay, bo_tuan_dang_chay=True)
            _dw = pivot_dinh_meta(_w, n_tuan, LOOKBACK_PIVOT_TUAN, "TUAN")
        except Exception:
            _dw = []
        vung_kc = ban_do_khang_cu(df_ngay, gia, atr, _dn, _dw,
                                  khe_min=khe_min, mas=_mas_hop_luu(df_ngay))
        tp1_vung, tp_nguon, ung_vien_vung = chon_tp1(vung_kc)
        if tp1_vung is not None:
            # Lùi TP1 xuống dưới biên vùng để đảm bảo khớp — đừng đặt lệnh
            # đúng giá tường. Kẹp lại để không tụt xuống dưới giá hiện tại.
            tp1 = max(round(tp1_vung["LO"] - TP1_LUI_ATR * atr, 2),
                      round(gia + khe_min, 2))
            _ke = [z for z in ung_vien_vung if z["LO"] > tp1_vung["HI"] + 1e-9]
            tp2 = round(_ke[0]["LO"], 2) if _ke else None
            _n_box = len(vung_kc) - len(ung_vien_vung)
            _ts = [z for z in vung_kc
                   if z["DIEM"] < KC_TP1_DIEM_TOI_THIEU and not z["BOX"]
                   and z["LO"] < tp1_vung["LO"]]
            _bo_qua = []
            if _ts:
                _ds = ", ".join("{:,.2f}".format(z["LO"]) for z in _ts)
                _bo_qua.append("{} vùng TRONG SUỐT ({})".format(len(_ts), _ds))
            if _n_box:
                _bo_qua.append("{} vùng ĐỈNH BOX".format(_n_box))
            canh_bao.append(
                f"TP1 = vùng {tp1_vung['LO']:,.2f}-{tp1_vung['HI']:,.2f} "
                f"[{tp1_vung['HANG']}, {tp1_vung['DIEM']:.0f}đ, "
                f"{tp1_vung['C_NHAN']}]"
                + (". Đã bỏ qua " + " và ".join(_bo_qua)
                   + " — v7.5 sẽ lấy mốc gần nhất bất kể chất lượng."
                   if _bo_qua else "."))
        elif vung_kc:
            # Có vùng nhưng TẤT CẢ là ĐỈNH BOX -> giá đang ở TRONG box, không
            # bị chặn. Đây KHÔNG phải breakout thật, phải nói đúng tên.
            trong_box = True
            canh_bao.append(
                f"GIÁ ĐANG TRONG BOX: {len(vung_kc)} vùng phía trên đều là "
                f"ĐỈNH BOX (giá dao động quanh chúng, không bị chặn). "
                f"Không có kháng cự cấu trúc để neo TP1.")
    else:
        tp1 = tat_ca_tp[0] if tat_ca_tp else None
        tp2 = tat_ca_tp[1] if len(tat_ca_tp) > 1 else None

    if tp1 is not None and bi_bo_qua_boi_v73:
        canh_bao.append(
            f"[chẩn đoán] v7.3 sẽ bỏ qua {len(bi_bo_qua_boi_v73)} mốc "
            f"({', '.join(f'{p:,.2f}' for p in bi_bo_qua_boi_v73)}) do lọc "
            f"{tp_min_pct:g}% và nhảy lên mốc xa hơn → R:R bị thổi.")

    # ---- ĐỐI CHỨNG BẮT BUỘC: luôn tính song song TP1 theo v7.5 ----
    # v7.6 BỎ QUA vùng TRONG SUỐT và ĐỈNH BOX -> TP1 ra XA hơn -> R:R TĂNG.
    # Đó đúng là CHIỀU HỎNG của v7.3 (thổi R:R). Trọng số của Ô 4B chưa
    # backtest, nên độ thổi phải LUÔN hiện ra, không được giấu.
    tp1_v75 = tat_ca_tp[0] if tat_ca_tp else None

    # ---------------- FALLBACK khi không có kháng cự cấu trúc ----------------
    if tp1 is None:
        hi52 = float(df_ngay["high"].tail(250).max())
        if hi52 >= gia + khe_min and not trong_box:
            tp1 = hi52
            canh_bao.append("Không có vùng kháng cự đạt chuẩn — dùng đỉnh 52W "
                            "làm TP1 (mốc THAM CHIẾU, chưa qua chấm điểm).")
        else:
            breakout = True
            tp1 = gia + TP_FALLBACK_RR * (gia - sl)
            canh_bao.append(
                f"GIÁ Ở VÙNG ĐỈNH — không có kháng cự cấu trúc phía trên "
                f"(BREAKOUT). TP1 {tp1:,.2f} = measured move {TP_FALLBACK_RR}R. "
                f"⚠️ R:R sẽ LUÔN ra đúng {TP_FALLBACK_RR:.2f} vì đó là hệ quả "
                f"của công thức, KHÔNG phải của cấu trúc giá.")

    # -------- KẸP KHÁNG CỰ — [SỬA v7.6, BUG N] xét SAU khi TP1 chốt --------
    # LỖI v7.5: khối phân loại kẹp nằm TRƯỚC nhánh fallback, nên khi TP1 rơi
    # vào đỉnh 52W thì tp_atr không bao giờ được tính -> một TP1 cách giá
    # 0.3xATR vẫn thoát nhãn KẸP. Nay đặt sau, mọi đường dẫn đều được xét.
    nguong_kep = (NGUONG_KEP_KHANG_CU_ATR if NGUONG_KEP_KHANG_CU_ATR
                  else rr_min_gan * SL_TOI_THIEU_ATR)
    kep_khang_cu = False
    tp_atr = None
    if tp1 is not None and atr > 0 and not breakout:
        tp_atr = (tp1 - gia) / atr
        if BAT_PHAN_LOAI_KEP and tp_atr < nguong_kep:
            kep_khang_cu = True
            _mo_ta = (f"[{tp1_vung['HANG']}, {tp1_vung['DIEM']:.0f}đ]"
                      if tp1_vung else "")
            canh_bao.append(
                f"KẸP KHÁNG CỰ: TP1 {tp1:,.2f} {_mo_ta} chỉ cách "
                f"{tp_atr:.2f}×ATR ({(tp1 / gia - 1) * 100:.2f}%), dưới ngưỡng "
                f"khả thi {nguong_kep:g}×ATR (= R:R {rr_min_gan:g} × sàn SL "
                f"{SL_TOI_THIEU_ATR:g}×ATR). R:R ≥ {rr_min_gan:g} là BẤT KHẢ THI "
                f"ở mọi vị trí stop → đây là BẾ TẮC HÌNH HỌC, không phải tỷ lệ xấu. "
                f"Đầu ra đúng là MỐC KÍCH HOẠT, không phải 'chờ giá tốt hơn'.")

    if de_risk_level and abs(tp1 - de_risk_level) / de_risk_level < 0.005:
        canh_bao.append(
            f"⚠️ TP1 ({tp1:,.2f}) gần trùng mốc cổng ({de_risk_level:,.2f}). "
            f"Cổng là BỘ LỌC CHẾ ĐỘ, không phải mục tiêu giá — kiểm tra pivot.")

    # ---------------- R:R ----------------
    # [SỬA v7.3] SL bị cap -> R ngắn lại -> R:R tự tăng. Phải BÙ bằng ngưỡng cao hơn,
    # và LUÔN in R:R gốc (theo SL cấu trúc) để không mất dấu con số thật.
    rr_min = (max(rr_min_gan, RR_TOI_THIEU_KHI_SL_CAP) if sl_cap else rr_min_gan)
    # [VÁ M7 — v7.6] TP1 lấy từ vùng KHÔNG đạt chuẩn (fallback) thì mục tiêu
    # kém tin cậy y như stop bị cap. Cùng logic bù rủi ro: nâng ngưỡng R:R.
    tp_kem_tin_cay = (tp_nguon == "FALLBACK_DIEM_CAO_NHAT")
    if tp_kem_tin_cay:
        rr_min = max(rr_min, RR_TOI_THIEU_KHI_SL_CAP)

    rr = gia_tran = rr_goc = None
    da_trong_vung = False
    if gia > sl_goc_luon:
        rr_goc = round((tp1 - gia) / (gia - sl_goc_luon), 2)
    if gia > sl:
        R = gia - sl
        rr = round((tp1 - gia) / R, 2)
        if breakout:
            # [VÁ 14] TP1 phụ thuộc chính giá -> vùng vào tự quy chiếu, vô nghĩa.
            gia_tran = None
        elif kep_khang_cu:
            # [BUG L] "Chờ về ≤ X" là lời khuyên SAI cho mã kẹp kháng cự: giá
            # giảm không mở được R:R vì trần TP1 tụt theo. Lối ra là PHÁ LÊN.
            gia_tran = None
        else:
            gia_tran = round((tp1 + rr_min * sl) / (1 + rr_min), 2)
            if gia_tran >= gia:
                da_trong_vung = True

    # ---------------- [VÁ 13] LÝ DO TRƯỢT ----------------
    # ---- Độ THỔI R:R do v7.6 bỏ qua vùng yếu ----
    rr_v75 = do_phong_rr = None
    if tp1_v75 is not None and gia > sl:
        rr_v75 = round((tp1_v75 - gia) / (gia - sl), 2)
        if rr_v75 > 1e-9 and rr is not None:
            do_phong_rr = round(rr / rr_v75, 2)
    if do_phong_rr is not None and do_phong_rr >= 2.0:
        canh_bao.append(
            f"⚠️ THỔI R:R ×{do_phong_rr:.1f}: v7.5 lấy TP1 {tp1_v75:,.2f} "
            f"→ R:R {rr_v75:.2f}; v7.6 bỏ qua vùng yếu, lấy TP1 {tp1:,.2f} "
            f"→ R:R {rr:.2f}. Chênh lệch này DỰA TRÊN trọng số CHƯA BACKTEST "
            f"của Ô 4B. Nếu bộ điểm sai thì đây chính là lỗi v7.3 tái diễn. "
            f"Đối chiếu bằng mắt trên chart trước khi vào lệnh.")

    ly_do_truot = []
    if rr is None:
        ly_do_truot.append("không tính được R:R (giá ≤ SL)")
    elif kep_khang_cu:
        # [BUG L] KHÔNG in "R:R x < 2.0" cho mã kẹp kháng cự — con số đó vô nghĩa
        # vì mẫu số bị hình học chặn, không phải do vị trí stop.
        ly_do_truot.append(
            f"KẸP KHÁNG CỰ ({tp_atr:.2f}×ATR < {nguong_kep:g}×ATR) — R:R "
            f"{rr:.2f} là hệ quả của khoảng cách, KHÔNG dùng để so ngưỡng")
    elif rr < rr_min - 1e-9:
        ly_do_truot.append(f"R:R {rr:.2f} < {rr_min}")
    if breakout:
        ly_do_truot.append(
            f"BREAKOUT — TP1 là measured move {TP_FALLBACK_RR}R, "
            f"không có kháng cự cấu trúc để neo → R:R không dùng được")
    if tp_kem_tin_cay and rr is not None and rr < rr_min - 1e-9:
        ly_do_truot.append(
            f"TP1 KÉM TIN CẬY: không vùng nào đạt hạng MÀNG "
            f"(cao nhất {tp1_vung['DIEM']:.0f}đ < {KC_TP1_DIEM_TOI_THIEU:g}) "
            f"→ ngưỡng R:R nâng lên {RR_TOI_THIEU_KHI_SL_CAP}")
    if trong_box:
        ly_do_truot.append(
            "GIÁ TRONG BOX — mọi vùng phía trên là ĐỈNH BOX, không có "
            "kháng cự cấu trúc. Chờ giá thoát box rồi đánh giá lại.")
    if sl_cap and rr is not None and rr_goc is not None:
        ly_do_truot.append(
            f"SL_CAP: R:R {rr:.2f} là số ĐÃ ĐƯỢC CAP làm ngắn R "
            f"(R:R theo SL cấu trúc thật chỉ {rr_goc:.2f}) → yêu cầu "
            f"≥ {RR_TOI_THIEU_KHI_SL_CAP}") if rr < rr_min - 1e-9 else None
    ly_do_truot = [l for l in ly_do_truot if l]
    dat_rr = (len(ly_do_truot) == 0)

    return {
        "SL": round(float(sl), 2),
        "SL_PIVOT_GOC": sl_pivot_goc,
        "SL_CAP": sl_cap,
        "NGAY_SL": ngay_sl,
        "SL_ATR": round(float(do_rong_atr), 2) if np.isfinite(do_rong_atr) else None,
        "ATR14": round(float(atr), 2),
        "TP1": round(float(tp1), 2),
        "TP2": round(float(tp2), 2) if tp2 else None,
        "TP_BI_BO_QUA_V73": [round(p, 2) for p in bi_bo_qua_boi_v73],
        "TP_KHE_MIN": round(float(khe_min), 2),
        "TP_ATR": round(float(tp_atr), 2) if tp_atr is not None else None,
        "KEP_KHANG_CU": kep_khang_cu,
        "NGUONG_KEP_ATR": round(float(nguong_kep), 2),
        # [SỬA v7.6] Mốc kích hoạt = ĐỈNH của vùng, không phải TP1.
        # LỖI v7.5: lấy đúng TP1 làm mốc kích hoạt. Nhưng TP1 nằm ở BIÊN DƯỚI
        # vùng cung — đóng cửa ngay tại đó chưa dọn xong vùng, giá vẫn còn
        # nguyên lượng hàng kẹp phía trên. Phải vượt HẲN đỉnh vùng.
        "MOC_KICH_HOAT": (round(float(tp1_vung["HI"]), 2) if (kep_khang_cu and tp1_vung)
                          else round(float(tp1), 2) if kep_khang_cu else None),
        "VOL_PHA_PCT": (tp1_vung["VOL_PHA_PCT"] if tp1_vung else 120),
        "TP_KE_TIEP": (round(float(tp2), 2) if (kep_khang_cu and tp2) else None),
        # --- v7.6: bản đồ kháng cự ---
        "VUNG_KC": vung_kc,
        "TP1_VUNG": tp1_vung,
        "TP1_HANG": (tp1_vung["HANG"] if tp1_vung else None),
        "TP1_DIEM": (tp1_vung["DIEM"] if tp1_vung else None),
        "TP1_CHAN_DOAN": (tp1_vung["C_NHAN"] if tp1_vung else None),
        "TP_NGUON": tp_nguon,
        "TP_KEM_TIN_CAY": tp_kem_tin_cay,
        "TRONG_BOX": trong_box,
        "N_VUNG": len(vung_kc),
        "N_VUNG_TUONG": sum(1 for z in vung_kc if z["HANG"] == "TƯỜNG"),
        # --- đối chứng v7.5 (luôn có, kể cả khi SUPPLY_SCORE bật) ---
        "TP1_V75": (round(float(tp1_v75), 2) if tp1_v75 is not None else None),
        "RR_V75": rr_v75,
        "DO_PHONG_RR": do_phong_rr,
        "BREAKOUT": breakout,
        "RR": rr,
        "RR_GOC": rr_goc,
        "RR_MIN": rr_min,
        "GIA_TRAN_RR": gia_tran,          # tên cũ: VUNG_VAO_RR  [VÁ 4 danh sách cũ]
        "VUNG_VAO_RR": gia_tran,          # alias giữ tương thích ngược
        "DA_TRONG_VUNG": da_trong_vung,
        "DAT_RR": dat_rr,
        "LY_DO_TRUOT": ly_do_truot,
        "canh_bao": canh_bao,
    }


def tinh_size(gia_vao, sl, nav=None, rui_ro_pct=None,
              he_so=1.0, he_so_gtgd=1.0, he_so_slatr=1.0, tran_pct=None):
    """
    Số CP = (NAV × rủi ro% × Πhệ_số) / (Giá vào − SL).
    [VÁ 17] Các hệ số giảm size NHÂN DỒN, không ghi đè nhau:
        he_so        : bậc giải ngân (Bậc 1 = 0.5)
        he_so_gtgd   : thanh khoản sát ngưỡng = 0.5
        he_so_slatr  : SL bị ATR-cap (stop rủi ro, không cấu trúc) = 0.5
    Bản cũ chỉ in ghi chú "size ×0.5" mà KHÔNG áp vào phép tính.
    """
    nav = nav or NAV
    rui_ro_pct = rui_ro_pct or RUI_RO_MOI_LENH_PCT
    if not sl or gia_vao is None or gia_vao <= sl:
        return None
    he_so_tong = he_so * he_so_gtgd * he_so_slatr
    if he_so_tong <= 0:
        return None
    tien_rui_ro = nav * rui_ro_pct / 100 * he_so_tong
    so_cp = int(tien_rui_ro / ((gia_vao - sl) * 1000))   # giá vnstock: nghìn đồng
    gia_tri = so_cp * gia_vao * 1000
    ty_trong = gia_tri / nav * 100
    bi_cap = False
    # [PHƯƠNG ÁN B] Trần thực = min(trần 1 mã, NGÂN SÁCH giải ngân của cổng).
    tran_hieu_luc = (TY_TRONG_TOI_DA_1_MA if tran_pct is None
                     else min(TY_TRONG_TOI_DA_1_MA, float(tran_pct)))
    if tran_hieu_luc <= 0:
        return None
    if ty_trong > tran_hieu_luc:
        bi_cap = True
        so_cp = int(nav * tran_hieu_luc / 100 / (gia_vao * 1000))
        gia_tri = so_cp * gia_vao * 1000
        ty_trong = gia_tri / nav * 100
    return {"SO_CP": so_cp, "GIA_TRI": round(gia_tri),
            "TY_TRONG_PCT": round(ty_trong, 1),
            "TRAN_HIEU_LUC_PCT": round(tran_hieu_luc, 2),
            "HE_SO": round(he_so_tong, 3), "BI_CAP_TRAN": bi_cap,
            "RUI_RO_VND": round(so_cp * (gia_vao - sl) * 1000)}


# ---------------------------------------------------------------- #
# 4.4 NGÂN SÁCH GIẢI NGÂN  [PHƯƠNG ÁN B]                            #
# ---------------------------------------------------------------- #
def tinh_ngan_sach(kq_cong, x_idx, ct_tuan=None, tran_bac=100.0):
    """
    PHƯƠNG ÁN B — chỉ số KHÔNG phủ quyết cổ phiếu bằng R:R nữa.
    Cổng trả nhị phân MỞ/ĐÓNG; mức rủi ro thị trường chuyển thành NGÂN SÁCH.

        NgânSách(%NAV) = TrầnCổng(D) × f_ext × f_vol × (trần bậc giải ngân)

    D     = (Close − DE_RISK_LEVEL) / ATR khung neo   → độ dày cổng
    f_ext = phạt mua đuổi theo ExtATR NGÀY của chỉ số
    f_vol = 1.00 nếu tuần đã đóng gần nhất giành lại mốc neo KÈM vol ≥ 120%
            MA20 khung TUẦN; ngược lại 0.50
    """
    if not kq_cong.get("CONG_MO"):
        return {"NGAN_SACH_PCT": 0.0, "LY_DO": "Cổng đóng — 0% NAV.",
                "D": None, "TRAN_CONG": 0, "F_EXT": 0, "F_VOL": 0,
                "MOC_NANG": [], "CHI_TIET": []}

    D = kq_cong.get("DAY_CONG_ATR")
    D = float(D) if D is not None else 0.0
    tran_cong = 0
    for nguong, tran in BANG_TRAN_CONG:
        if D < nguong:
            tran_cong = tran
            break
    else:
        tran_cong = BANG_TRAN_CONG[-1][1]

    ext = x_idx.get("ext_atr") if x_idx else None
    f_ext = _f_ext_tu_ext(ext)

    xac_nhan_vol = bool(
        ct_tuan
        and ct_tuan.get("close") is not None
        and ct_tuan["close"] >= kq_cong["DE_RISK_LEVEL"]
        and ct_tuan.get("vol_tuan_cuoi", 0) >= ct_tuan.get("nguong_vol_120_tuan", 9e18))
    f_vol = 1.00 if xac_nhan_vol else F_VOL_CHUA_XAC_NHAN

    # Bậc giải ngân là một TRẦN ĐỘC LẬP, không phải hệ số nhân.
    # Nhân vào sẽ phạt chồng: bậc 1 đã tự giảm size qua HE_SO_SIZE=0.5 rồi.
    ngan_sach_tho = tran_cong * f_ext * f_vol
    ngan_sach = min(ngan_sach_tho, float(tran_bac))

    # Mốc giá để nâng từng bậc trần cổng
    atr_neo = kq_cong.get("ATR_IDX") or 0
    # Vượt ngưỡng thứ k thì rơi vào bậc trần của mục thứ k+1 (vì điều kiện là
    # D < nguong). Ghép nhầm cặp sẽ in ra bậc thấp hơn thực tế một nấc.
    moc = []
    for k, (nguong, _) in enumerate(BANG_TRAN_CONG):
        if nguong > D and nguong < 9e8 and atr_neo > 0 and k + 1 < len(BANG_TRAN_CONG):
            moc.append((round(kq_cong["DE_RISK_LEVEL"] + nguong * atr_neo, 2),
                        nguong, BANG_TRAN_CONG[k + 1][1]))

    chi_tiet = [
        f"D = ({kq_cong['GIA']:,.2f} − {kq_cong['DE_RISK_LEVEL']:,.2f}) / "
        f"{atr_neo:,.2f} [{kq_cong.get('KHUNG_ATR','ATR')}] = {D:.3f} "
        f"→ trần cổng {tran_cong}%",
        f"ExtATR(1D) = {ext:.2f} → f_ext = {f_ext:.2f}" if ext is not None
        else "ExtATR THIẾU → f_ext = 0.50",
        (f"Tuần đã đóng giành lại mốc neo KÈM vol "
         f"{ct_tuan['vol_tuan_cuoi']:,.0f} ≥ 120% MA20W "
         f"({ct_tuan['nguong_vol_120_tuan']:,.0f}) → f_vol = 1.00"
         if xac_nhan_vol else
         f"Reclaim CHƯA được vol tuần xác nhận"
         + (f" (vol {ct_tuan['vol_cuoi_pct_tuan']:.0f}% MA20W < 120%)"
            if ct_tuan else " (thiếu dữ liệu tuần)")
         + f" → f_vol = {F_VOL_CHUA_XAC_NHAN:.2f}"),
        f"Trần bậc giải ngân: {tran_bac:g}% "
        + ("(RÀNG BUỘC — đang chặn)" if ngan_sach_tho > tran_bac else "(không ràng buộc)"),
    ]
    return {"NGAN_SACH_PCT": round(ngan_sach, 2), "D": round(D, 3),
            "TRAN_CONG": tran_cong, "F_EXT": f_ext, "F_VOL": f_vol,
            "XAC_NHAN_VOL_TUAN": xac_nhan_vol,
            "MOC_NANG": moc, "CHI_TIET": chi_tiet,
            "NGAN_SACH_THO": round(ngan_sach_tho, 2),
            "LY_DO": (f"min({tran_cong}% × {f_ext:.2f} × {f_vol:.2f} "
                      f"= {ngan_sach_tho:.2f}% ; trần bậc {tran_bac:g}%) "
                      f"= {ngan_sach:.2f}% NAV")}


def in_ngan_sach(ns):
    print("-" * 66)
    print("NGÂN SÁCH GIẢI NGÂN  [PHƯƠNG ÁN B — thay cho việc R:R chỉ số chặn lệnh]")
    for c in ns["CHI_TIET"]:
        print(f"  • {c}")
    print(f"  ➜ NGÂN SÁCH = {ns['LY_DO']}")
    if ns["MOC_NANG"]:
        print("  Mốc nâng trần cổng (tính với mốc neo hiện tại — đổi mỗi tuần):")
        for gia_moc, ng, tran in ns["MOC_NANG"]:
            print(f"     đóng cửa ≥ {gia_moc:,.2f}  (D ≥ {ng:g}×ATR) → trần {tran}%")
    print("  Đây là TRẦN, không phải chỉ tiêu. R:R tầng mã vẫn phải tự đạt chuẩn.")


def in_cong(kq, rr=None):
    trang_thai = "🟢 CỔNG MỞ" if kq["CONG_MO"] else "⛔ CỔNG CHẶN"
    if kq["CONG_MO"] and not kq.get("CONG_DAY", True):
        trang_thai = "🟡 CỔNG MỞ (MỎNG)"
    pct = kq["KHOANG_CACH"] / kq["DE_RISK_LEVEL"] * 100
    print("=" * 66)
    print(f"CỔNG CHẾ ĐỘ VNINDEX — {kq['NGAY']}")
    print("=" * 66)
    print(f"Đóng cửa        : {kq['GIA']:>12,.2f}")
    print(f"MA20W           : {kq['MA20W']:>12,.2f}")
    print(f"MA200D          : {kq['MA200D']:>12,.2f}")
    print(f"DE_RISK_LEVEL   : {kq['DE_RISK_LEVEL']:>12,.2f}   (neo: {kq['NEO']})")
    print(f"Trạng thái      : {trang_thai}   "
          f"({kq['KHOANG_CACH']:+,.2f} điểm / {pct:+.2f}%"
          + (f" = {kq['DAY_CONG_ATR']}×ATR" if kq.get("DAY_CONG_ATR") is not None else "")
          + ")")
    if kq.get("MUC_CONG_DAY"):
        print(f"Mốc cổng DÀY    : {kq['MUC_CONG_DAY']:>12,.2f}   "
              f"(= cổng + {BUFFER_CONG_ATR}×ATR14 → mới cho dùng hết trần NAV)")
    print(f"INVALIDATION    : {INVALIDATION:>12,.2f}   "
          f"(cách {kq['GIA'] - INVALIDATION:+,.2f} điểm)")
    if rr:
        print("-" * 66)
        _nhan = ("R:R CẤU TRÚC CHỈ SỐ — ⚠️ THAM KHẢO, KHÔNG CHẶN LỆNH [chế độ B]"
                 if globals().get("CHE_DO_CONG", "A") == "B"
                 else "R:R CẤU TRÚC (pivot tự dò — KHÔNG dùng mốc cổng làm TP)")
        print(_nhan)
        print(f"  SL  (đáy pivot)   : {rr['SL']:>12,.2f}   "
              f"({rr['NGAY_SL']}, cách {rr['SL_ATR']}×ATR)")
        print(f"  TP1               : {rr['TP1']:>12,.2f}"
              + ("   [measured move — BREAKOUT]" if rr["BREAKOUT"] else ""))
        print(f"  TP2               : "
              + (f"{rr['TP2']:>12,.2f}" if rr['TP2'] else f"{'—':>12}"))
        print(f"  R:R tại giá hiện  : {rr['RR'] if rr['RR'] else '—':>12}"
              f"   → {'ĐẠT' if rr['DAT_RR'] else 'KHÔNG ĐẠT'}"
              f"   (ngưỡng {rr['RR_MIN']:g})")
        if rr.get("SL_CAP") and rr.get("RR_GOC") is not None:
            print(f"  R:R theo SL CẤU TRÚC: {rr['RR_GOC']:>12,.2f}   "
                  f"← con số THẬT (SL {rr['SL_PIVOT_GOC']:,.2f}). "
                  f"Số phía trên đã được cap làm ngắn R.")
        for l in rr["LY_DO_TRUOT"]:
            print(f"     ↳ trượt vì: {l}")
        if rr["GIA_TRAN_RR"]:
            print(f"  GiáTrầnRR{rr['RR_MIN']:g} (giá vào tối đa để đạt R:R ≥ "
                  f"{rr['RR_MIN']:g}): {rr['GIA_TRAN_RR']:,.2f}")
            if rr["DA_TRONG_VUNG"]:
                print("     ✅ Giá hiện tại ĐÃ nằm trong vùng — không phải chờ.")
            if kq["DE_RISK_LEVEL"] and rr["GIA_TRAN_RR"] < kq["DE_RISK_LEVEL"]:
                _b = globals().get("CHE_DO_CONG", "A") == "B"
                print(f"     {'ℹ️' if _b else '🚨'} BẾ TẮC CHỈ SỐ: GiáTrầnRR "
                      f"({rr['GIA_TRAN_RR']:,.2f}) < cổng ({kq['DE_RISK_LEVEL']:,.2f}) "
                      f"— hụt {kq['DE_RISK_LEVEL'] - rr['GIA_TRAN_RR']:,.2f} điểm.")
                if _b:
                    print("        [B] KHÔNG chặn lệnh. Bế tắc này chỉ nói: chỉ số "
                          "đang xa MA20W → đã phản ánh vào f_ext của NGÂN SÁCH.")
                    print("        R:R vẫn phải tự đạt chuẩn ở TỪNG MÃ — không hạ ở đó.")
                else:
                    print("        [A] Chờ MA20D dâng (ExtATR tự nén) hoặc pivot đáy "
                          "mới. KHÔNG hạ chuẩn R:R để lách.")
        elif rr.get("KEP_KHANG_CU"):
            print(f"  GiáTrầnRR         : — (KẸP KHÁNG CỰ: giá giảm KHÔNG mở được "
                  f"R:R vì TP1 tụt theo)")
            print(f"  MỐC KÍCH HOẠT     : đóng cửa > {rr['MOC_KICH_HOAT']:,.2f} "
                  f"kèm vol ≥ 120% MA20"
                  + (f" → TP1 nhảy lên {rr['TP_KE_TIEP']:,.2f}"
                     if rr.get("TP_KE_TIEP") else " → tính lại kháng cự kế tiếp"))
        elif rr["BREAKOUT"]:
            print("  GiáTrầnRR         : — (BREAKOUT: TP1 phụ thuộc chính giá "
                  "→ vùng vào tự quy chiếu, không tính)")
        for c in rr["canh_bao"]:
            print(f"  ⚠️ {c}")
    for c in kq["canh_bao"]:
        print(f"  ⚠️ {c}")
    print("=" * 66)


print("✅ Ô 4 v7.4-B — TP1=kháng cự gần nhất [B], cap SL=ngưỡng kích hoạt [A],")
print("   cổng đo bằng ATR khung neo [C], tinh_ngan_sach() [Phương án B]")

# ======================================================================
# Ô 4B — BẢN ĐỒ KHÁNG CỰ CÓ TRỌNG SỐ  (SUPPLY_SCORE)          [v7.6]
# ----------------------------------------------------------------------
# Kháng cự KHÔNG bằng nhau. Bộ chọn TP1 của v7.5 đối xử với chúng như nhau
# nên sinh ra "KẸP KHÁNG CỰ GIẢ": TP1 bị chặn bởi một bóng nến volume 40%
# MA20 trong khi tường thật nằm xa hơn 3xATR.
#
# Module này chấm điểm 0-100 cho từng VÙNG cung rồi phân hạng. Tất cả
# thành phần tính được từ OHLCV đã có — KHÔNG cần dán tay thêm dữ liệu.
#
#   Nhóm A — cung tại mốc      (55đ): volume tạo đỉnh, volume từ chối, độ bật
#   Nhóm B — cấu trúc          (29đ): cấp khung, hợp lưu MA, độ dày cụm
#   Nhóm C — lịch sử test  (-15..20): hấp thụ / cung thật / phá thất bại / box
#
# ⚠️ Trọng số CHƯA BACKTEST. Xem cảnh báo ở Ô 2 mục 2.11 và chạy Ô 4C.
# ======================================================================
import numpy as np
import pandas as pd


# ---------------------------------------------------------------- #
# 4B.1 PIVOT ĐỈNH CÓ METADATA                                       #
# ---------------------------------------------------------------- #
def pivot_dinh_meta(df, n, lookback, khung):
    """
    Pivot ĐỈNH đã xác nhận, kèm dữ liệu cần cho chấm điểm.
    khung: "NGAY" | "TUAN" — quyết định hằng số suy giảm theo tuổi.

    ⚠️ "idx_lat" là chỉ số TRONG LÁT tail(lookback) hoặc trong frame TUẦN,
    KHÔNG phải chỉ số trên frame ngày đầy đủ. Mọi tra cứu chéo phải đi qua
    "time" + idx_tu_thoi_gian().  [VÁ M9]
    """
    d = df.tail(lookback) if lookback else df
    d = d.reset_index(drop=True)
    if len(d) < 2 * n + 1:
        return []
    h = d["high"].to_numpy(dtype=float)
    o = d["open"].to_numpy(dtype=float)
    c = d["close"].to_numpy(dtype=float)
    l = d["low"].to_numpy(dtype=float)
    v = d["volume"].to_numpy(dtype=float)
    t = (pd.to_datetime(d["time"]) if "time" in d.columns
         else pd.Series(pd.RangeIndex(len(d))))
    vma = pd.Series(v).rolling(20, min_periods=5).mean().to_numpy()
    N = len(d)
    ra = []
    for i in range(n, N - n):
        if h[i] != h[i - n:i + n + 1].max():
            continue
        sau = l[i + 1:i + 1 + 5]
        day_sau = float(sau.min()) if len(sau) else float(l[i])
        vm = vma[i]
        ra.append({
            "khung": khung,
            "idx_lat": i,
            "tuoi": N - 1 - i,
            "time": t.iloc[i],
            "gia": float(h[i]),
            "than": float(max(o[i], c[i])),
            "vol": float(v[i]),
            "vol_ty_le": (float(v[i] / vm)
                          if np.isfinite(vm) and vm > 0 else np.nan),
            "bat_ra": float(h[i] - day_sau),
        })
    return ra


def idx_tu_thoi_gian(df, t):
    """[VÁ M9] Bắc cầu chỉ số giữa các frame qua timestamp.
    Dùng thẳng idx của lát cắt sẽ đọc nhầm nến: một vùng TUẦN 26 tuần tuổi
    bị chấm bằng dữ liệu của 26 nến NGÀY gần nhất."""
    if "time" not in df.columns or len(df) == 0:
        return 0
    tt = pd.to_datetime(df["time"]).to_numpy()
    pos = int(np.searchsorted(tt, np.datetime64(pd.Timestamp(t)), side="left"))
    return int(np.clip(pos, 0, len(df) - 1))


# ---------------------------------------------------------------- #
# 4B.2 GỘP CỤM  — [VÁ M1] chặn chain-linking                        #
# ---------------------------------------------------------------- #
def gop_cum(mocs, atr, ts=None):
    """
    LỖI ĐÃ VÁ: chỉ so khe giữa hai mốc KỀ NHAU thì một chuỗi mốc cách đều
    0.4xATR nối thành cụm rộng vô hạn. Ca FRT: 146.50 -> 148.50 -> 149.24
    -> 151.50 nối liền thành "một vùng" rộng 1.1xATR — vô nghĩa.
    Nay áp thêm TRẦN BỀ RỘNG tính từ mốc neo của cụm.
    """
    ts = ts or KC_THAM_SO
    if not mocs or atr <= 0:
        return []
    ms = sorted(mocs, key=lambda m: m["gia"])
    khe = ts["khe_gop_atr"] * atr
    tran = ts["tran_rong_cum"] * atr
    cum, hien = [], [ms[0]]
    for m in ms[1:]:
        neo = hien[0]["gia"]
        if (m["gia"] - hien[-1]["gia"] <= khe) and (m["gia"] - neo <= tran):
            hien.append(m)
        else:
            cum.append(hien)
            hien = [m]
    cum.append(hien)
    return cum


# ---------------------------------------------------------------- #
# 4B.3 LỊCH SỬ TƯƠNG TÁC VỚI VÙNG                                   #
# ---------------------------------------------------------------- #
def lich_su_vung(df, lo, hi, atr, tu_idx=0, ts=None):
    """
    Đọc cách giá đã cư xử với dải [lo, hi] kể từ nến tu_idx.

    Đây là phần trả lời trực tiếp câu "kháng cự nào phải test nhiều lần mới
    qua được". Sách vở nói "test càng nhiều càng yếu" — thực tế HƯỚNG phụ
    thuộc CHẤT LƯỢNG test:
      vol giảm dần + đáy nâng dần  -> HẤP THỤ, cung cạn, lần sau qua được
      vol không giảm / đáy thấp dần -> CUNG THẬT, tường đang xây dày
    """
    ts = ts or KC_THAM_SO
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    v = df["volume"].to_numpy(dtype=float)
    N = len(df)
    tu_idx = max(0, min(int(tu_idx), max(N - 1, 0)))

    # ---- nến TỪ CHỐI  [VÁ M2] ------------------------------------
    # LỖI ĐÃ VÁ: bản đầu đếm MỌI nến có [low,high] giao dải. Với vùng nằm
    # ngay trên giá hiện tại thì 13/16 nến gần nhất đều "giao" — chỉ vì giá
    # đang đứng đó, KHÔNG phải vì bị từ chối. Điểm A2 tự phồng.
    # Nay chỉ đếm nến THẬT SỰ bị đẩy xuống: high vào dải, close vẫn dưới.
    nen_tc = [i for i in range(tu_idx, N) if h[i] >= lo and c[i] < lo]

    # ---- các đợt chạm dải ----------------------------------------
    eps, cur = [], None
    for i in range(tu_idx, N):
        if h[i] >= lo:
            cur = {"bd": i, "kt": i} if cur is None else {**cur, "kt": i}
        elif cur is not None:
            eps.append(cur)
            cur = None
    if cur is not None:
        eps.append(cur)

    for e in eps:
        s, k = e["bd"], e["kt"]
        e["vol_max"] = float(v[s:k + 1].max())
        e["high_max"] = float(h[s:k + 1].max())
        e["close_max"] = float(c[s:k + 1].max())
        sau = l[k + 1:k + 1 + 10]
        e["day_sau"] = float(sau.min()) if len(sau) else float(l[k])
        e["bat_ra"] = e["high_max"] - e["day_sau"]
        e["bien_do"] = e["high_max"] - float(l[s:k + 1].min())

    nguong_bat = ts["bat_ra_toi_thieu_atr"] * atr
    ep_tc = [e for e in eps if e["bat_ra"] >= nguong_bat]

    # ---- run close-trên-dải: phân biệt BOX với PHÁ THẤT BẠI -------
    # BOX          : nhiều cụm rời rạc -> giá DAO ĐỘNG quanh dải, không bị chặn
    # PHÁ THẤT BẠI : đúng một cụm rồi rơi lại -> hàng kẹp tái tạo tường
    cs = int(ts["cua_so_box"])
    bd = max(tu_idx, N - cs)
    tren = [c[i] > lo for i in range(bd, N)]
    so_run, truoc = 0, False
    for x in tren:
        if x and not truoc:
            so_run += 1
        truoc = x
    dang_duoi = bool(N and c[-1] <= lo)
    box = bool(so_run >= 2)
    pha_that_bai = bool(so_run == 1 and dang_duoi)

    # ---- xu hướng volume / đáy giữa các đợt ----------------------
    vol_can = day_nang = bien_nen = False
    if len(ep_tc) >= 2:
        v0, v1 = ep_tc[0]["vol_max"], ep_tc[-1]["vol_max"]
        vol_can = bool(v0 > 0 and v1 / v0 < ts["hap_thu_ty_le_vol"])
        days = [e["day_sau"] for e in ep_tc]
        day_nang = bool(days[-1] > days[0])
        bds = [e["bien_do"] for e in ep_tc]
        bien_nen = bool(bds[0] > 0 and bds[-1] < bds[0] * 0.75)

    return {
        "nen_tu_choi": nen_tc, "n_nen_tu_choi": len(nen_tc),
        "vol_tu_choi": float(sum(v[i] for i in nen_tc)) if nen_tc else 0.0,
        "ep": eps, "ep_tu_choi": ep_tc, "n_tu_choi": len(ep_tc),
        "so_run": so_run, "box": box, "pha_that_bai": pha_that_bai,
        "vol_can": vol_can, "day_nang": day_nang, "bien_nen": bien_nen,
    }


# ---------------------------------------------------------------- #
# 4B.4 CHẤM ĐIỂM MỘT VÙNG                                           #
# ---------------------------------------------------------------- #
def cham_diem_vung(cum, df_ngay, atr, mas=None, ts=None):
    ts = ts or KC_THAM_SO
    mas = mas or {}
    lo = min(m["gia"] for m in cum)
    hi = max(m["gia"] for m in cum)
    tam = (lo + hi) / 2

    def _decay(m):
        if m["khung"] == "TUAN":
            return max(np.exp(-m["tuoi"] / ts["tau_tuan"]), ts["san_decay_tuan"])
        return max(np.exp(-m["tuoi"] / ts["tau_ngay"]), ts["san_decay_ngay"])

    # ---- A1: volume tạo đỉnh ----
    # Đỉnh tạo bằng vol 250% = 250% người mua ở đó đang kẹt -> lực bán khi
    # giá quay lại. Đỉnh tạo bằng vol 60% = gần như không ai kẹt.
    a1_raw = a1 = 0.0
    for m in cum:
        r = m["vol_ty_le"]
        if not np.isfinite(r):
            continue
        d = min(max(r, 0), ts["A1_bao_hoa"]) / ts["A1_bao_hoa"] * ts["A1_max"]
        a1_raw, a1 = max(a1_raw, d), max(a1, d * _decay(m))

    # ---- A3: độ mạnh cú bật ra ----
    a3_raw = a3 = 0.0
    if atr > 0:
        for m in cum:
            r = m["bat_ra"] / atr
            d = min(max(r, 0), ts["A3_bao_hoa"]) / ts["A3_bao_hoa"] * ts["A3_max"]
            a3_raw, a3 = max(a3_raw, d), max(a3, d * _decay(m))

    # ---- lịch sử (dùng cho A2 và C) ----
    t_som = min(pd.Timestamp(m["time"]) for m in cum)
    idx_som = idx_tu_thoi_gian(df_ngay, t_som)
    ls = lich_su_vung(df_ngay, lo, hi, atr, tu_idx=idx_som, ts=ts)

    # ---- A2a: TỶ LỆ volume từ chối ----
    v = df_ngay["volume"].to_numpy(dtype=float)
    _s = pd.Series(v).rolling(20, min_periods=5).mean()
    vma_now = float(_s.iloc[-1]) if len(_s) and np.isfinite(_s.iloc[-1]) else 0.0
    a2a = 0.0
    if ls["n_nen_tu_choi"] > 0 and vma_now > 0:
        tyle = ls["vol_tu_choi"] / (vma_now * ls["n_nen_tu_choi"])
        a2a = min(tyle, ts["A2a_bao_hoa"]) / ts["A2a_bao_hoa"] * ts["A2a_max"]

    # ---- A2b: SỐ LẦN từ chối  [VÁ M3] ----
    # Tỷ lệ thuần bỏ sót thông tin: 8 nến từ chối ở tỷ lệ 1.0 là tường dày
    # hơn 1 nến ở tỷ lệ 1.0, nhưng A2a chấm hai ca đó BẰNG NHAU.
    a2b = (min(ls["n_nen_tu_choi"], ts["A2b_bao_hoa"])
           / ts["A2b_bao_hoa"] * ts["A2b_max"])

    # ---- B1: cấp khung ----
    b1 = 0.0
    c_arr = df_ngay["close"].to_numpy(dtype=float)[idx_som:]
    n_close_trong = int(((c_arr >= lo) & (c_arr <= hi)).sum())
    for m in cum:
        if m["khung"] == "TUAN":
            b1 = max(b1, ts["B1_tuan"])
        elif n_close_trong >= 3:
            b1 = max(b1, ts["B1_ngay_dong"])
        elif m["than"] >= lo:
            b1 = max(b1, ts["B1_ngay_than"])
        else:
            b1 = max(b1, ts["B1_ngay_bong"])

    # ---- B2: hợp lưu MA ----
    khe_ma = ts["B2_khe_atr"] * atr
    ma_trung = [k for k, gv in mas.items()
                if gv is not None and np.isfinite(gv) and abs(gv - tam) <= khe_ma]
    b2 = min(len(ma_trung) * ts["B2_moi_ma"], ts["B2_max"])

    # ---- B4: độ dày cụm ----
    b4 = min((len(cum) - 1) * ts["B4_moi_pivot"], ts["B4_max"])

    # ---- C: lịch sử test ----
    if ls["box"]:
        c_diem, c_nhan = ts["C_box"], "ĐỈNH BOX — giá dao động quanh dải"
    elif ls["pha_that_bai"]:
        c_diem, c_nhan = ts["C_pha_that_bai"], "PHÁ THẤT BẠI — hàng kẹp tái tạo tường"
    elif ls["n_tu_choi"] >= 2 and ls["vol_can"] and ls["day_nang"]:
        c_diem, c_nhan = ts["C_hap_thu"], "HẤP THỤ — vol cạn dần, đáy nâng"
    elif ls["n_tu_choi"] >= 4 and ls["bien_nen"]:
        c_diem, c_nhan = ts["C_nen"], "NÉN — biên độ co hẹp"
    elif ls["n_tu_choi"] >= 2:
        c_diem, c_nhan = ts["C_cung_that"], f"CUNG THẬT — {ls['n_tu_choi']} lần từ chối"
    elif ls["n_tu_choi"] == 1:
        c_diem, c_nhan = ts["C_mot_lan"], "1 lần test — chưa đủ mẫu"
    else:
        c_diem, c_nhan = ts["C_chua_test"], "CHƯA TEST — không có thông tin"

    tong = float(np.clip(a1 + a2a + a2b + a3 + b1 + b2 + b4 + c_diem, 0, 100))
    tong_raw = float(np.clip(a1_raw + a2a + a2b + a3_raw + b1 + b2 + b4 + c_diem, 0, 100))
    hang = ("TƯỜNG" if tong >= ts["nguong_tuong"]
            else "MÀNG" if tong >= ts["nguong_mang"] else "TRONG SUỐT")

    return {
        "LO": round(lo, 2), "HI": round(hi, 2), "TAM": round(tam, 2),
        "DIEM": round(tong, 1),
        # [VÁ M8] RAW = trước decay. Phân biệt "yếu vì MỎNG" với "yếu vì CŨ":
        # vùng RAW cao nhưng già = TƯỜNG NGỦ, vẫn phải cảnh giác khi giá tới.
        "DIEM_RAW": round(tong_raw, 1),
        "HANG": hang,
        "BOX": ls["box"], "PHA_THAT_BAI": ls["pha_that_bai"],
        "TUONG_NGU": bool(tong_raw >= ts["nguong_tuong"] and tong < ts["nguong_tuong"]),
        "N_PIVOT": len(cum), "N_TU_CHOI": ls["n_tu_choi"],
        "N_NEN_TU_CHOI": ls["n_nen_tu_choi"],
        "TUOI": min(m["tuoi"] for m in cum),
        "KHUNG": "TUAN" if any(m["khung"] == "TUAN" for m in cum) else "NGAY",
        "MA_TRUNG": ma_trung, "C_NHAN": c_nhan,
        "THANH_PHAN": {"A1": round(a1, 1), "A2a": round(a2a, 1),
                       "A2b": round(a2b, 1), "A3": round(a3, 1),
                       "B1": round(b1, 1), "B2": round(b2, 1),
                       "B4": round(b4, 1), "C": round(c_diem, 1)},
        "VOL_PHA_PCT": KC_VOL_PHA.get(hang, 120),
    }


# ---------------------------------------------------------------- #
# 4B.5 BẢN ĐỒ + CHỌN TP1                                            #
# ---------------------------------------------------------------- #
def _mas_hop_luu(df_ngay):
    """Các đường MA dùng để tính hợp lưu (B2)."""
    c = df_ngay["close"]
    m = {}
    for n, ten in ((20, "MA20D"), (50, "MA50D"), (200, "MA200D")):
        m[ten] = float(c.rolling(n).mean().iloc[-1]) if len(c) >= n else None
    try:
        wc = gop_tuan(df_ngay, bo_tuan_dang_chay=True)["close"]
        for n, ten in ((20, "MA20W"), (50, "MA50W")):
            m[ten] = float(wc.rolling(n).mean().iloc[-1]) if len(wc) >= n else None
    except Exception:
        pass
    return m


def ban_do_khang_cu(df_ngay, gia, atr, dinh_ngay, dinh_tuan,
                    khe_min=0.0, mas=None, ts=None):
    """Danh sách VÙNG kháng cự trên giá, đã chấm điểm, sắp theo giá tăng dần."""
    ts = ts or KC_THAM_SO
    if atr is None or not np.isfinite(atr) or atr <= 0:
        return []
    mocs = [m for m in (list(dinh_ngay) + list(dinh_tuan))
            if m["gia"] >= gia + khe_min]
    if not mocs:
        return []
    vungs = []
    for cum in gop_cum(mocs, atr, ts):
        z = cham_diem_vung(cum, df_ngay, atr, mas=mas, ts=ts)
        z["CACH_ATR"] = round((z["LO"] - gia) / atr, 2)
        z["CACH_PCT"] = round((z["LO"] / gia - 1) * 100, 2)
        vungs.append(z)
    return sorted(vungs, key=lambda z: z["LO"])


def chon_tp1(vungs, diem_toi_thieu=None, ts=None):
    """
    TP1 = VÙNG GẦN NHẤT không phải ĐỈNH BOX và đạt tối thiểu hạng MÀNG.

    [VÁ M6] Loại vùng ĐỈNH BOX: giá đang dao động BÊN TRONG dải đó nên nó
    không chặn gì. Lấy nó làm TP1 sinh R:R vô nghĩa (ca FRT: box
    142.90-148.00, "kháng cự" 146.50 chỉ cách giá 0.12xATR).

    KHÔNG nhảy lên TƯỜNG xa hơn khi có MÀNG chắn trước: màng vẫn làm giá
    khựng: bỏ qua nó là lặp lại đúng lỗi THỔI R:R của v7.3.

    Trả (vùng|None, nguồn, danh_sách_ứng_viên).
    """
    ts = ts or KC_THAM_SO
    nguong = KC_TP1_DIEM_TOI_THIEU if diem_toi_thieu is None else diem_toi_thieu
    ung_vien = [z for z in vungs if not z["BOX"]]
    hop_le = [z for z in ung_vien if z["DIEM"] >= nguong]
    if hop_le:
        return hop_le[0], "VUNG_DAT_CHUAN", ung_vien
    # [VÁ M7] Không vùng nào đạt chuẩn -> fallback vùng điểm cao nhất VÀ
    # gắn cờ để tầng trên NÂNG NGƯỠNG R:R (target kém tin cậy).
    if ung_vien:
        return (max(ung_vien, key=lambda z: z["DIEM"]),
                "FALLBACK_DIEM_CAO_NHAT", ung_vien)
    return None, "KHONG_CO_VUNG", ung_vien


def in_ban_do(vungs, gia, tieu_de="", tp1_lo=None):
    if tieu_de:
        print(f"\n--- BẢN ĐỒ KHÁNG CỰ {tieu_de} (giá {gia:,.2f}) ---")
    if not vungs:
        print("   (không có vùng kháng cự cấu trúc phía trên)")
        return
    print(f"   {'Vùng':^19} {'Điểm':>5} {'RAW':>5} {'Hạng':<10} {'xATR':>5} "
          f"{'Khung':<5} {'Tuổi':>4} {'N':>2}  Chẩn đoán")
    for z in vungs:
        dau = "➜" if (tp1_lo is not None and abs(z["LO"] - tp1_lo) < 1e-6) else " "
        co = ("BOX " if z["BOX"] else "") + ("NGỦ " if z["TUONG_NGU"] else "")
        print(f" {dau} {z['LO']:>8,.2f}-{z['HI']:<9,.2f} {z['DIEM']:>5.1f} "
              f"{z['DIEM_RAW']:>5.1f} {z['HANG']:<10} {z['CACH_ATR']:>5.2f} "
              f"{z['KHUNG']:<5} {z['TUOI']:>4} {z['N_PIVOT']:>2}  {co}{z['C_NHAN']}")
    print("   ➜ = TP1 đang dùng | RAW = điểm trước suy giảm tuổi | "
          "NGỦ = tường cũ, vẫn cảnh giác")


print("✅ Ô 4B v7.6 — BẢN ĐỒ KHÁNG CỰ CÓ TRỌNG SỐ (SUPPLY_SCORE)")
print("   pivot_dinh_meta / gop_cum / lich_su_vung / cham_diem_vung")
print("   ban_do_khang_cu / chon_tp1 / in_ban_do")
print(f"   Phân hạng: TRONG SUỐT <{KC_THAM_SO['nguong_mang']:g} | "
      f"MÀNG {KC_THAM_SO['nguong_mang']:g}-{KC_THAM_SO['nguong_tuong']:g} | "
      f"TƯỜNG ≥{KC_THAM_SO['nguong_tuong']:g}")
print("   ⚠️ CHƯA BACKTEST — chạy Ô 4C trước khi tin số điểm.")

# ======================================================================
# Ô 5 — CHỈ BÁO KỸ THUẬT
# ======================================================================
import pandas as pd
import numpy as np


def rsi_wilder(close, n=14):
    d = close.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def macd(close, nhanh=12, cham=26, tin_hieu=9):
    ema_n = close.ewm(span=nhanh, adjust=False).mean()
    ema_c = close.ewm(span=cham, adjust=False).mean()
    line = ema_n - ema_c
    sig = line.ewm(span=tin_hieu, adjust=False).mean()
    return line, sig, line - sig


def atr14(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]


def atr14_tuan(df, n=14):
    """[SỬA v7.4 — BUG C] ATR khung TUẦN, tính trên tuần ĐÃ ĐÓNG.
    Cần cho việc đo độ dày cổng khi mốc neo là MA20W (khung tuần).
    Dùng ATR NGÀY để đo một mốc khung TUẦN làm cổng trông dày gấp ~2.7 lần
    so với thực tế (VNINDEX 28/08: 0.40×ATR_D nhưng chỉ 0.147×ATR_W)."""
    try:
        w = gop_tuan(df, bo_tuan_dang_chay=True)
    except Exception:
        return float("nan")
    if len(w) < n + 1:
        return float("nan")
    return atr14(w, n)


def chi_bao_tuan(df):
    """
    [VÁ 18] Chỉ báo khung TUẦN tính trên TUẦN ĐÃ ĐÓNG.
    Trước đây Ô 8 lấy nguong_vol_120 của khung NGÀY rồi đem so với
    VOLUME TUẦN -> ngưỡng thấp hơn ~5 lần, gate volume tuần vô hiệu.
    """
    w = gop_tuan(df, bo_tuan_dang_chay=True)
    if len(w) < 20:
        return None
    v = w["volume"]
    mav20 = float(v.rolling(20).mean().iloc[-1])
    return {"n_tuan": len(w),
            "ngay_tuan_cuoi": pd.to_datetime(w["time"].iloc[-1]),
            "close": float(w["close"].iloc[-1]),
            "mav20_tuan": mav20,
            "nguong_vol_120_tuan": mav20 * 1.2,
            "vol_tuan_cuoi": float(v.iloc[-1]),
            "vol_cuoi_pct_tuan": float(v.iloc[-1] / mav20 * 100) if mav20 > 0 else np.nan}


def kiem_tra_tuan(df):
    """Bộ lọc xu hướng tuần: giá trên MA10W và MA10W dốc lên.
    [VÁ 15] Chỉ dùng tuần ĐÃ ĐÓNG — tuần chạy dở làm MA10W nhảy mỗi phiên."""
    try:
        w = gop_tuan(df, bo_tuan_dang_chay=True)
    except Exception as e:
        return None, f"THIẾU dữ liệu tuần ({e})"
    if len(w) < 14:
        return None, "THIẾU dữ liệu tuần"
    ma10w = w["close"].rolling(10).mean()
    tren = w["close"].iloc[-1] > ma10w.iloc[-1]
    doc = ma10w.iloc[-1] > ma10w.iloc[-5]
    ok = bool(tren and doc)
    return ok, ("1W ✅" if ok else
                f"1W ❌ ({'dưới MA10W' if not tren else 'MA10W dốc xuống'})")


def tinh_chi_bao(df):
    c, v = df["close"], df["volume"]
    r = {}
    r["close"] = float(c.iloc[-1])
    r["ma20"] = c.rolling(20).mean().iloc[-1]
    r["ma50"] = c.rolling(50).mean().iloc[-1]
    r["ma200"] = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else np.nan
    ma50s = c.rolling(50).mean()
    r["ma50_doc_len"] = bool(ma50s.iloc[-1] > ma50s.iloc[-11]) if len(c) >= 61 else False
    r["rsi"] = rsi_wilder(c).iloc[-1]
    ml, ms, mh = macd(c)
    r["macd_line"], r["macd_signal"], r["macd_hist"] = (
        float(ml.iloc[-1]), float(ms.iloc[-1]), float(mh.iloc[-1]))
    r["mav20"] = v.rolling(20).mean().iloc[-1]
    r["vol_cuoi_pct"] = float(v.iloc[-1] / r["mav20"] * 100) if r["mav20"] > 0 else np.nan
    r["nguong_vol_120"] = float(r["mav20"] * 1.2) if r["mav20"] > 0 else np.nan
    # giá vnstock đơn vị nghìn đồng -> (c*v)/1e6 = tỷ đồng
    r["gtgd20"] = (c * v).rolling(20).mean().iloc[-1] / 1e6
    r["atr"] = atr14(df)
    r["ext_atr"] = (c.iloc[-1] - r["ma20"]) / r["atr"] if r["atr"] > 0 else np.nan
    high52 = df["high"].iloc[-250:].max() if len(df) >= 250 else df["high"].max()
    r["cach_dinh"] = (1 - c.iloc[-1] / high52) * 100
    r["ret_4w"] = (c.iloc[-1] / c.iloc[-21] - 1) * 100 if len(c) >= 21 else np.nan
    r["ret_12w"] = (c.iloc[-1] / c.iloc[-61] - 1) * 100 if len(c) >= 61 else np.nan
    r["run_5p"] = (c.iloc[-1] / c.iloc[-6] - 1) * 100 if len(c) >= 6 else np.nan
    r["vol5_vs_mav20"] = (v.iloc[-5:].mean() / r["mav20"] * 100
                          if r["mav20"] > 0 else np.nan)
    return r


def tren_ma20w(df, n=20):
    """[PHƯƠNG ÁN B — cổng mã S1] Giá mã có đứng trên MA20W của chính nó không.
    Trả (bool|None, ghi_chú)."""
    try:
        w = gop_tuan(df, bo_tuan_dang_chay=True)
    except Exception as e:
        return None, f"THIẾU tuần ({e})"
    if len(w) < n:
        return None, f"THIẾU tuần (<{n} nến)"
    ma = float(w["close"].rolling(n).mean().iloc[-1])
    c = float(w["close"].iloc[-1])
    return bool(c >= ma), f"MA20W {ma:,.2f} | close_W {c:,.2f}"


print("✅ Ô 5 v7.4 — thêm atr14_tuan() [BUG C] và tren_ma20w() [cổng mã S1]")

# ======================================================================
# Ô 5B — KHUNG v3: BỘ LỌC CỨNG · NHẬN DIỆN SETUP · THOÁT LỆNH 2 TẦNG
# ----------------------------------------------------------------------
# Nguồn phương pháp (tài liệu công khai):
#   Stan Weinstein   — Stage Analysis, MA30W            -> F1
#   Mark Minervini   — Trend Template, progressive exposure, expectancy
#                                                        -> F2, sizing, Ô 11
#   Kristjan Kullamägi — xếp hạng RS đa khung, episodic pivot, bộ lọc
#                        MA10/20 của chỉ số, thoát 2 tầng -> F3, setup, exit
#   William O'Neil   — nghiên cứu mã thắng lịch sử       -> nền tảng F3
#   Linda Raschke    — pullback ADX/MA, kỷ luật giữ lãi  -> setup C
#
# NGUYÊN TẮC BẤT DI BẤT DỊCH CỦA Ô NÀY:
#   Mọi hàm ở đây trả PASS/FAIL hoặc None(=thiếu dữ liệu).
#   KHÔNG hàm nào ở đây được trả về một "điểm số" dùng để bù trừ cho
#   một bộ lọc đã trượt. Bù trừ chính là lỗi kiến trúc mà v3 tồn tại để sửa.
# ======================================================================
import pandas as pd
import numpy as np


# ---------------------------------------------------------------- #
# 5B.0 TIỆN ÍCH                                                     #
# ---------------------------------------------------------------- #
def _tuan_da_dong(df):
    """Nến TUẦN đã đóng. None nếu không dựng được."""
    try:
        w = gop_tuan(df, bo_tuan_dang_chay=True)
    except Exception:
        return None
    return w if (w is not None and len(w)) else None


def _f(v):
    """float an toàn -> nan nếu không đổi được."""
    try:
        x = float(v)
        return x if np.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _so(v, k=2):
    """Làm tròn an toàn -> None nếu không phải số hữu hạn (dùng cho cột bảng)."""
    x = _f(v)
    return round(x, k) if np.isfinite(x) else None


# ---------------------------------------------------------------- #
# 5B.1 F1 — GIAI ĐOẠN WEINSTEIN (khung TUẦN)                        #
# ---------------------------------------------------------------- #
def giai_doan_weinstein(df):
    """
    Trọng tài xu hướng của Weinstein là QUAN HỆ giữa giá và MA30W CỘNG với
    ĐỘ DỐC của MA30W. Chỉ Stage 2 mới được mua.
        Stage 1 BASING     — giá dưới/quanh MA30W đi ngang  -> theo dõi
        Stage 2 ADVANCING  — giá trên MA30W dốc lên         -> ĐƯỢC MUA
        Stage 3 TOPPING    — MA30W đi ngang sau uptrend dài -> ngừng mua, siết stop
        Stage 4 DECLINING  — giá dưới MA30W dốc xuống       -> tránh tuyệt đối
    """
    n, k = MA_STAGE_TUAN, STAGE_DOC_LEN_SO_TUAN
    w = _tuan_da_dong(df)
    if w is None or len(w) < n + k:
        co = 0 if w is None else len(w)
        return {"STAGE": None, "TEN": "THIẾU dữ liệu tuần",
                "GHI_CHU": f"cần ≥ {n + k} tuần đã đóng, có {co}",
                "MA30W": None, "DOC_PCT": None, "TREN_MA": None}
    ma = w["close"].rolling(n).mean()
    ma_ht, ma_truoc = _f(ma.iloc[-1]), _f(ma.iloc[-1 - k])
    close_w = _f(w["close"].iloc[-1])
    if not np.isfinite(ma_ht) or not np.isfinite(ma_truoc) or ma_truoc <= 0:
        return {"STAGE": None, "TEN": "THIẾU MA30W", "GHI_CHU": "MA30W = NaN",
                "MA30W": None, "DOC_PCT": None, "TREN_MA": None}

    doc = (ma_ht / ma_truoc - 1) * 100
    tren = bool(close_w >= ma_ht)
    hi52 = _f(w["high"].tail(52).max())
    cach_dinh = (1 - close_w / hi52) * 100 if np.isfinite(hi52) and hi52 > 0 else np.nan
    di_ngang = abs(doc) <= STAGE_DOC_NGUONG_PCT

    if tren and doc > STAGE_DOC_NGUONG_PCT:
        stage, ten = 2, "Stage 2 ADVANCING"
    elif (not tren) and doc < -STAGE_DOC_NGUONG_PCT:
        stage, ten = 4, "Stage 4 DECLINING"
    elif tren and di_ngang:
        # MA đi ngang mà giá còn trên: TOPPING nếu vừa từ đỉnh xuống,
        # BASING nếu giá còn xa đỉnh 52W.
        if np.isfinite(cach_dinh) and cach_dinh <= 15:
            stage, ten = 3, "Stage 3 TOPPING"
        else:
            stage, ten = 1, "Stage 1 BASING"
    elif tren:                                  # trên MA nhưng MA còn dốc xuống
        stage, ten = 1, "Stage 1 BASING (giành lại MA30W, MA còn dốc xuống)"
    else:
        stage, ten = 1, "Stage 1 BASING"

    return {"STAGE": stage, "TEN": ten,
            "MA30W": round(ma_ht, 2), "CLOSE_W": round(close_w, 2),
            "DOC_PCT": round(doc, 2), "TREN_MA": tren,
            "CACH_DINH_52W_PCT": (round(cach_dinh, 1)
                                  if np.isfinite(cach_dinh) else None),
            "GHI_CHU": (f"close_W {close_w:,.2f} "
                        f"{'≥' if tren else '<'} MA{n}W {ma_ht:,.2f}, "
                        f"độ dốc {k} tuần {doc:+.2f}%")}


# ---------------------------------------------------------------- #
# 5B.2 F2 — TREND TEMPLATE (Minervini)                              #
# ---------------------------------------------------------------- #
def trend_template(df):
    """8 điều kiện. Minervini: trượt MỘT điều kiện là KHÔNG phải ứng viên mua."""
    c = df["close"]
    can = 200 + TT_MA200_DOC_SO_PHIEN + 1
    if len(c) < can:
        return {"DAT": None, "SO_DAT": None, "TONG": 8, "CHI_TIET": [],
                "GHI_CHU": f"THIẾU (<{can} phiên, có {len(c)})"}
    ma50 = _f(c.rolling(50).mean().iloc[-1])
    ma150 = _f(c.rolling(150).mean().iloc[-1])
    ma200s = c.rolling(200).mean()
    ma200 = _f(ma200s.iloc[-1])
    ma200_truoc = _f(ma200s.iloc[-1 - TT_MA200_DOC_SO_PHIEN])
    close = _f(c.iloc[-1])
    lo52 = _f(df["low"].tail(250).min())
    hi52 = _f(df["high"].tail(250).max())

    dk = [
        ("close > MA50", close > ma50),
        ("close > MA150", close > ma150),
        ("close > MA200", close > ma200),
        ("MA150 > MA200", ma150 > ma200),
        (f"MA200 dốc lên ≥{TT_MA200_DOC_SO_PHIEN}p", ma200 > ma200_truoc),
        ("MA50 > MA150 > MA200", (ma50 > ma150) and (ma150 > ma200)),
        (f"≥{TT_CACH_DAY_52W_MIN:g}% trên đáy 52W",
         close >= lo52 * (1 + TT_CACH_DAY_52W_MIN / 100)),
        (f"≤{TT_CACH_DINH_52W_MAX:g}% dưới đỉnh 52W",
         close >= hi52 * (1 - TT_CACH_DINH_52W_MAX / 100)),
    ]
    dk = [(t, bool(v) if v == v else False) for t, v in dk]
    so_dat = sum(1 for _, v in dk if v)
    truot = [t for t, v in dk if not v]
    return {"DAT": bool(so_dat >= TT_SO_DK_TOI_THIEU), "SO_DAT": so_dat,
            "TONG": 8, "CHI_TIET": dk, "TRUOT": truot,
            "MA150": round(ma150, 2) if np.isfinite(ma150) else None,
            "GHI_CHU": (f"{so_dat}/8" + (f" — trượt: {'; '.join(truot)}"
                                         if truot else ""))}


# ---------------------------------------------------------------- #
# 5B.3 F3 — HIỆU SUẤT ĐA KHUNG + NỀN TẢNG                           #
# ---------------------------------------------------------------- #
def loi_nhuan_da_khung(df, khung=None):
    """% thay đổi giá trên từng khung (số phiên). NaN khi không đủ dữ liệu."""
    khung = khung or RS_KHUNG
    c = df["close"]
    out = {}
    for k in khung:
        out[k] = (_f(c.iloc[-1] / c.iloc[-1 - k] - 1) * 100
                  if len(c) > k else np.nan)
    return out


def nen_tang_gan_nhat(df, cua_so=None):
    """
    Đợt tăng nền tảng: từ đáy thấp nhất TRƯỚC đỉnh cao nhất, trong cửa sổ.
    Mã chưa từng chứng minh được đợt tăng thứ nhất thì không có cơ sở nào
    để cược vào đợt thứ hai (O'Neil / Kullamägi — nghiên cứu mã thắng).
    """
    cua_so = cua_so or NEN_TANG_CUA_SO
    c = df["close"].tail(cua_so).reset_index(drop=True)
    if len(c) < 40:
        return np.nan
    i_max = int(np.argmax(c.to_numpy()))
    if i_max == 0:
        return 0.0
    day = _f(c.iloc[:i_max + 1].min())
    if not np.isfinite(day) or day <= 0:
        return np.nan
    return _f(c.iloc[i_max] / day - 1) * 100


def xep_hang_pct(chuoi):
    """Phân vị 0-100 trong rổ đã quét. NaN giữ nguyên NaN."""
    s = pd.Series(chuoi, dtype="float64")
    if s.notna().sum() < 3:
        return pd.Series([np.nan] * len(s), index=s.index)
    return s.rank(pct=True) * 100


# ---------------------------------------------------------------- #
# 5B.4 F4 — ADR (biên độ ngày trung bình)                           #
# ---------------------------------------------------------------- #
def adr_pct(df, n=None):
    """ADR% = (trung bình High/Low của n phiên − 1) × 100."""
    n = n or ADR_SO_PHIEN
    d = df.tail(n)
    if len(d) < n:
        return np.nan
    r = (d["high"] / d["low"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < max(5, n // 2):
        return np.nan
    return _f((r.mean() - 1) * 100)


# ---------------------------------------------------------------- #
# 5B.5 F5 — CỔNG CHẤT LƯỢNG ĐIỂM VÀO  (THAY CHO CỔNG R:R)           #
# ---------------------------------------------------------------- #
def cong_chat_luong_vao(gia, sl, atr, la_ep=False):
    """
    Đây là thay đổi CỐT LÕI của v3.

    v2 hỏi: "mục tiêu có đủ xa để R:R ≥ 2 không?"  -> đòi biết trước đỉnh
            -> trong pha markup luôn trả lời KHÔNG -> deadlock.
    v3 hỏi: "điểm dừng lỗ có đủ CHẶT để đây thực sự là một điểm vào không?"
            -> chỉ cần dữ liệu quá khứ, không cần biết tương lai.

    Kullamägi bỏ lệnh khi stop rộng hơn ADR của mã. Bản VN nới thành cửa sổ
    [1.5 ; 2.5]×ATR vì T+2.5 không cho phép stop chặt hơn 1.5×ATR.
    """
    if gia is None or sl is None or not np.isfinite(_f(atr)) or _f(atr) <= 0:
        return {"DAT": None, "GHI_CHU": "THIẾU giá/SL/ATR"}
    gia, sl, atr = _f(gia), _f(sl), _f(atr)
    if gia <= sl:
        return {"DAT": False, "GHI_CHU": "giá ≤ SL — không tính được"}
    d_atr = (gia - sl) / atr
    d_pct = (gia - sl) / gia * 100
    lo, hi = SL_CUA_SO_ATR
    if la_ep:
        hi = max(hi, EP_SL_TOI_DA_ATR)
    ly_do = []
    if d_atr < lo - 1e-9:
        ly_do.append(f"stop {d_atr:.2f}×ATR < {lo:g}×ATR — quá chặt cho T+2.5")
    if d_atr > hi + 1e-9:
        ly_do.append(f"stop {d_atr:.2f}×ATR > {hi:g}×ATR — nền CHƯA SIẾT, "
                     f"chưa phải điểm vào (chờ nền co lại, không mua rộng)")
    if d_pct > SL_TOI_DA_PCT + 1e-9:
        ly_do.append(f"stop {d_pct:.2f}% > {SL_TOI_DA_PCT:g}% giá vào")
    return {"DAT": len(ly_do) == 0, "SL_ATR": round(d_atr, 2),
            "SL_PCT": round(d_pct, 2), "CUA_SO": (lo, hi), "TRUOT": ly_do,
            "GHI_CHU": (f"stop {d_atr:.2f}×ATR / {d_pct:.2f}%"
                        + ("" if not ly_do else " — " + "; ".join(ly_do)))}


# ---------------------------------------------------------------- #
# 5B.6 NHẬN DIỆN SETUP                                              #
# ---------------------------------------------------------------- #
def adx_wilder(df, n=14):
    h, l, c = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    if len(c) < n * 3:
        return np.nan
    up, dn = h.diff(), -l.diff()
    p_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=c.index)
    m_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=c.index)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
                   axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean().replace(0, np.nan)
    pdi = 100 * p_dm.ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * m_dm.ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return _f(dx.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def do_co_that(df, cua_so=None, so_doan=None):
    """
    Kiểm tra CO THẮT BIẾN ĐỘNG (VCP). Nền hợp lệ khi biên độ từng đoạn
    NÔNG DẦN. Nền đi ngang lỏng (biên độ không co) KHÔNG phải VCP —
    khác biệt này là toàn bộ giá trị của mẫu hình.
    """
    cua_so = cua_so or BO_NEN_CUA_SO
    so_doan = so_doan or BO_NEN_SO_DOAN
    d = df.tail(cua_so)
    if len(d) < cua_so:
        return {"CO_THAT": None, "GHI_CHU": f"THIẾU (<{cua_so} phiên)", "BIEN": []}
    L = len(d) // so_doan
    bien = []
    for i in range(so_doan):
        seg = d.iloc[i * L:(i + 1) * L] if i < so_doan - 1 else d.iloc[i * L:]
        hi, lo = _f(seg["high"].max()), _f(seg["low"].min())
        bien.append((hi / lo - 1) * 100 if (np.isfinite(lo) and lo > 0) else np.nan)
    if any(not np.isfinite(b) for b in bien):
        return {"CO_THAT": None, "GHI_CHU": "biên độ = NaN", "BIEN": bien}
    ok = all(bien[i + 1] <= bien[i] * BO_NEN_CO_THAT_TY for i in range(len(bien) - 1))
    # đáy sau cao hơn đáy trước
    day = []
    for i in range(so_doan):
        seg = d.iloc[i * L:(i + 1) * L] if i < so_doan - 1 else d.iloc[i * L:]
        day.append(_f(seg["low"].min()))
    day_nang = all(day[i + 1] >= day[i] for i in range(len(day) - 1))
    # ĐỈNH NỀN phải loại nến HIỆN TẠI, nếu không "close >= đỉnh nền" là điều
    # kiện tự quy chiếu và KHÔNG BAO GIỜ đúng (close luôn <= high của chính nó).
    dinh_nen = _f(d.iloc[:-1]["high"].max())
    return {"CO_THAT": bool(ok), "DAY_NANG": bool(day_nang),
            "BIEN": [round(b, 2) for b in bien],
            "DINH_NEN": round(dinh_nen, 2) if np.isfinite(dinh_nen) else None,
            "GHI_CHU": ("biên độ " + " → ".join(f"{b:.1f}%" for b in bien)
                        + (" (co thắt ✅)" if ok else " (KHÔNG co thắt)")
                        + (", đáy nâng dần" if day_nang else ", đáy KHÔNG nâng"))}


def _episodic_pivot(df, x):
    """EP phiên bản VN: HOSE ±7% nên không có gap 10% — dùng phiên gần trần."""
    c, v = df["close"], df["volume"]
    if len(c) < EP_NGU_QUEN_PHIEN + EP_CUA_SO_PHIEN + 25:
        return None
    mav20 = _f(x.get("mav20"))
    if not np.isfinite(mav20) or mav20 <= 0:
        return None
    ch = c.pct_change() * 100
    for k in range(1, EP_CUA_SO_PHIEN + 1):
        i = -k
        tang = _f(ch.iloc[i])
        vol_lan = _f(v.iloc[i]) / mav20
        if tang >= EP_TANG_PCT_MIN and vol_lan >= EP_VOL_LAN:
            # điều kiện THEN CHỐT: trước đó phải BỊ LÃNG QUÊN
            truoc = c.iloc[i - EP_NGU_QUEN_PHIEN:i]
            if len(truoc) < EP_NGU_QUEN_PHIEN:
                continue
            lo, hi = _f(truoc.min()), _f(truoc.max())
            if not (np.isfinite(lo) and lo > 0):
                continue
            bien = (hi / lo - 1) * 100
            if bien <= EP_NGU_QUEN_BIEN_PCT:
                return {"PHIEN_TRUOC": k - 1, "TANG_PCT": round(tang, 2),
                        "VOL_LAN": round(vol_lan, 1),
                        "BIEN_NGU_QUEN_PCT": round(bien, 1),
                        "DINH_EP": round(_f(df["high"].iloc[i]), 2),
                        "DAY_EP": round(_f(df["low"].iloc[i]), 2)}
    return None


def nhan_dien_setup(df, x, co_that=None):
    """
    Trả (MÃ_SETUP, mô tả). None = KHÔNG CÓ SETUP.
    Quy tắc v3: không có setup thì KHÔNG CÓ LỆNH, kể cả khi điểm cao.
    Chỉ A/B/C tự động hoá được. D (Wyckoff/LPS) phải xác nhận bằng mắt.
    """
    co_that = co_that or do_co_that(df)
    close = _f(x.get("close"))
    vol_pct = _f(x.get("vol_cuoi_pct"))

    # --- B · Episodic Pivot (ưu tiên cao nhất: sự kiện định giá lại) ---
    ep = _episodic_pivot(df, x)
    if ep:
        return ("B", f"EP-VN: phiên {ep['TANG_PCT']:+.1f}% vol ×{ep['VOL_LAN']:.1f} "
                     f"cách đây {ep['PHIEN_TRUOC']} phiên, trước đó ngủ quên "
                     f"{EP_NGU_QUEN_PHIEN}p biên {ep['BIEN_NGU_QUEN_PCT']:.0f}% "
                     f"| kích hoạt: vượt {ep['DINH_EP']:,.2f}, SL dưới {ep['DAY_EP']:,.2f}",
                ep)

    # --- A · Breakout nền co thắt (VCP / flat base) ---
    if co_that.get("CO_THAT"):
        dinh_nen = co_that.get("DINH_NEN")
        if dinh_nen and close >= dinh_nen - 1e-9 and np.isfinite(vol_pct):
            if vol_pct >= BO_VOL_PCT:
                return ("A", f"BO nền co thắt ĐÃ KÍCH HOẠT: close {close:,.2f} ≥ "
                             f"đỉnh nền {dinh_nen:,.2f}, vol {vol_pct:.0f}% "
                             f"≥ {BO_VOL_PCT:g}% | {co_that['GHI_CHU']}", co_that)
            if vol_pct >= BO_VOL_PCT_TOI_THIEU:
                return ("A-", f"BO CHẤT LƯỢNG THẤP: vol {vol_pct:.0f}% chỉ đạt "
                              f"{BO_VOL_PCT_TOI_THIEU:g}-{BO_VOL_PCT:g}% → size ×0.5 "
                              f"hoặc bỏ qua | {co_that['GHI_CHU']}", co_that)
            return ("A?", f"Phá đỉnh nền NHƯNG vol {vol_pct:.0f}% < "
                          f"{BO_VOL_PCT_TOI_THIEU:g}% — cung chưa được hấp thụ, "
                          f"KHÔNG mua | {co_that['GHI_CHU']}", co_that)
        return ("A-CHỜ", f"Nền co thắt hợp lệ, CHƯA phá. Kích hoạt: đóng cửa > "
                         f"{dinh_nen:,.2f} kèm vol ≥ {BO_VOL_PCT:g}% MA20 | "
                         f"{co_that['GHI_CHU']}", co_that)

    # --- C · Pullback về MA (Raschke) ---
    # "Pullback" nghĩa là giá ĐÃ ĐI XUỐNG CHẠM đường MA rồi bật lên — không
    # phải chỉ tình cờ nằm gần nó. Trong một xu hướng mượt, giá luôn ở gần MA;
    # thiếu điều kiện CHẠM thì mọi phiên đều bị gán nhãn setup C.
    adx = adx_wilder(df)
    if np.isfinite(adx) and adx >= ADX_TOI_THIEU and len(df) >= 25:
        c = df["close"]
        for n_ma in PULLBACK_MA:
            ma = _f(c.rolling(n_ma).mean().iloc[-1])
            if not np.isfinite(ma) or ma <= 0:
                continue
            khe = abs(close / ma - 1) * 100
            cham = _f(df["low"].tail(3).min()) <= ma      # thật sự chạm MA
            tren = close > ma                            # và đóng cửa lại ở trên
            if khe <= PULLBACK_KHE_PCT and cham and tren:
                dinh_truoc = _f(df["high"].iloc[-2])
                dao_chieu = bool(close > dinh_truoc)
                return ("C", f"Pullback MA{n_ma} (ADX {adx:.0f} ≥ {ADX_TOI_THIEU:g}), "
                             f"đã chạm MA và đóng cửa lại trên, khe {khe:.1f}% "
                             f"| kích hoạt: đóng cửa > đỉnh nến trước "
                             f"{dinh_truoc:,.2f}"
                             + (" — ĐÃ kích hoạt" if dao_chieu else " — CHƯA kích hoạt"),
                        {"ADX": round(adx, 1), "MA": n_ma, "KICH_HOAT": dao_chieu})
    return (None, "KHÔNG khớp setup A/B/C — v3: không có setup thì không có lệnh "
                  "(D/Wyckoff phải xác nhận bằng mắt trên chart)", None)


# ---------------------------------------------------------------- #
# 5B.7 TÍN HIỆU THOÁT CHỦ ĐỘNG (thay setup parabolic short)         #
# ---------------------------------------------------------------- #
def tin_hieu_thoat_parabolic(df, x):
    """VN không bán khống -> logic 'dây thun' của Kullamägi chuyển thành
    tín hiệu THOÁT cho vị thế long đang có. Cần ≥ 2 dấu hiệu."""
    dh = []
    c, v = df["close"], df["volume"]
    if len(c) > PARA_CUA_SO:
        tang = _f(c.iloc[-1] / c.iloc[-1 - PARA_CUA_SO] - 1) * 100
        if tang >= PARA_TANG_PCT:
            dh.append(f"tăng {tang:.0f}% trong {PARA_CUA_SO} phiên")
    ch = c.diff()
    chuoi = 0
    for val in reversed(ch.tail(10).tolist()):
        if val is not None and val == val and val > 0:
            chuoi += 1
        else:
            break
    if chuoi >= PARA_CHUOI_XANH:
        dh.append(f"{chuoi} phiên tăng liên tiếp")
    vp = _f(x.get("vol_cuoi_pct"))
    if np.isfinite(vp) and vp >= PARA_VOL_CLIMAX:
        dh.append(f"vol climax {vp:.0f}% MA20")
    ext = _f(x.get("ext_atr"))
    if np.isfinite(ext) and ext > HE_SO_DUOI:
        dh.append(f"ExtATR {ext:.2f} > {HE_SO_DUOI:g}")
    return {"KICH_HOAT": len(dh) >= 2, "DAU_HIEU": dh,
            "GHI_CHU": ("; ".join(dh) if dh else "không có dấu hiệu parabolic")}


# ---------------------------------------------------------------- #
# 5B.8 KẾ HOẠCH THOÁT 2 TẦNG                                        #
# ---------------------------------------------------------------- #
def ke_hoach_thoat(gia_vao, sl, df=None):
    """
    Thay TP1/TP2 CỐ ĐỊNH bằng quy trình:
        Tầng 1 — bán 1/2 khi đạt +2R HOẶC vào đợt mạnh đầu tiên (3-5 phiên),
                 tuỳ điều kiện nào ĐẾN TRƯỚC; dời stop phần còn lại về hoà vốn.
        Tầng 2 — trail theo MA20 (hoặc MA10 nếu mã chạy nhanh);
                 thoát khi ĐÓNG CỬA dưới đường đã chọn (wick KHÔNG tính).
    Đây là lý do v3 không cần biết trước đỉnh — và cũng là lý do bỏ được
    cổng R:R gây deadlock.
    """
    gia_vao, sl = _f(gia_vao), _f(sl)
    if not np.isfinite(gia_vao) or not np.isfinite(sl) or gia_vao <= sl:
        return None
    R = gia_vao - sl
    kh = {"R_VND": round(R, 2),
          "TP_TANG1": round(gia_vao + TP_TANG1_R * R, 2),
          "TY_LE_BAN_TANG1": TY_LE_BAN_TANG1,
          "SL_SAU_TANG1": round(gia_vao, 2),
          "MA_TRAIL": MA_TRAIL, "MA_TRAIL_NHANH": MA_TRAIL_NHANH}
    if df is not None and len(df) >= MA_TRAIL:
        c = df["close"]
        kh["MA_TRAIL_GIA"] = round(_f(c.rolling(MA_TRAIL).mean().iloc[-1]), 2)
        kh["MA_TRAIL_NHANH_GIA"] = round(_f(c.rolling(MA_TRAIL_NHANH).mean().iloc[-1]), 2)
    kh["MO_TA"] = (
        f"Tầng 1: bán {TY_LE_BAN_TANG1:.0%} tại {kh['TP_TANG1']:,.2f} (+{TP_TANG1_R:g}R) "
        f"HOẶC vào đợt mạnh đầu tiên {TP_TANG1_PHIEN[0]}-{TP_TANG1_PHIEN[1]} phiên "
        f"sau điểm vào — cái nào đến trước; sau đó dời stop về hoà vốn "
        f"{kh['SL_SAU_TANG1']:,.2f}. "
        f"Tầng 2: trail MA{MA_TRAIL} ngày"
        + (f" (hiện {kh['MA_TRAIL_GIA']:,.2f})" if "MA_TRAIL_GIA" in kh else "")
        + f", thoát khi ĐÓNG CỬA dưới đường — wick xuyên KHÔNG tính.")
    return kh


# ---------------------------------------------------------------- #
# 5B.9 PROGRESSIVE EXPOSURE (Minervini)                             #
# ---------------------------------------------------------------- #
def _chuoi_cuoi_dau(vals, duong=True):
    n = 0
    for v in reversed(list(vals)):
        v = _f(v)
        if not np.isfinite(v):
            break
        if (v > 0) == duong and v != 0:
            n += 1
        else:
            break
    return n


def rui_ro_pct_hien_hanh(chuoi_R=None, cong_nhanh_ok=True, stage_idx=None):
    """
    Không vào full size ngay. Vào nhỏ để LẤY PHẢN HỒI THỊ TRƯỜNG, chỉ tăng
    khi các lệnh nhỏ bắt đầu chạy — và hạ ngay khi chúng bị quét.
    """
    chuoi_R = CHUOI_R_GAN_NHAT if chuoi_R is None else chuoi_R
    thua = _chuoi_cuoi_dau(chuoi_R, duong=False)
    thang = _chuoi_cuoi_dau(chuoi_R, duong=True)
    if not cong_nhanh_ok:
        return RUI_RO_PCT_THAM_DO, ("cổng nhanh MA10<MA20 của chỉ số → "
                                    "vị thế THĂM DÒ")
    if thua >= 2:
        return RUI_RO_PCT_THAM_DO, f"{thua} lệnh thua liên tiếp → vị thế THĂM DÒ"
    if thang >= 2 and stage_idx == 2:
        return RUI_RO_PCT_TOI_DA, (f"{thang} lệnh thắng liên tiếp + chỉ số "
                                   f"Stage 2 → size tối đa")
    if not chuoi_R:
        return RUI_RO_PCT_BINH_THUONG, "chưa có lịch sử lệnh → mức mặc định"
    return RUI_RO_PCT_BINH_THUONG, "điều kiện bình thường"


# ---------------------------------------------------------------- #
# 5B.10 CỔNG NHANH MA10/MA20 CỦA CHỈ SỐ (Kullamägi)                 #
# ---------------------------------------------------------------- #
def cong_nhanh_ma1020(df_idx):
    """
    Tầng CHẬM là DE_RISK (MA20W). Tầng NHANH là MA10 vs MA20 NGÀY của chỉ số.
    MA10 > MA20 -> môi trường thuận cho breakout.
    MA10 < MA20 -> breakout thất bại hàng loạt; hạ exposure, không mua mới.
    """
    c = df_idx["close"]
    if len(c) < 25:
        return {"OK": None, "GHI_CHU": "THIẾU (<25 phiên)"}
    ma10 = _f(c.rolling(10).mean().iloc[-1])
    ma20 = _f(c.rolling(20).mean().iloc[-1])
    ok = bool(ma10 > ma20)
    return {"OK": ok, "MA10": round(ma10, 2), "MA20": round(ma20, 2),
            "F": 1.0 if ok else F_MA1020_KHI_DUOI,
            "GHI_CHU": (f"MA10 {ma10:,.2f} {'>' if ok else '<'} MA20 {ma20:,.2f}"
                        f" → {'MỞ (f=1.00)' if ok else f'ĐÓNG (f={F_MA1020_KHI_DUOI:.2f})'}")}


def ap_cong_nhanh(ngan_sach_pct, cn):
    """Nhân hệ số cổng nhanh vào ngân sách của Phương án B."""
    if not BAT_CONG_MA1020 or cn is None or cn.get("OK") is None:
        return round(float(ngan_sach_pct), 2), "cổng nhanh TẮT/thiếu dữ liệu"
    f = cn["F"]
    return (round(float(ngan_sach_pct) * f, 2),
            f"× f_MA1020 {f:.2f} ({cn['GHI_CHU']})")


# ---------------------------------------------------------------- #
# 5B.11 ĐIỂM v3 — CHỈ XẾP HẠNG CÁC MÃ ĐÃ QUA BỘ LỌC                 #
# ---------------------------------------------------------------- #
def diem_v3(setup_ma, rank_min, kn, rs_nganh_duong, ext_atr):
    """
    Σ(điểm × trọng số) / Σ(trọng số các lớp CÓ DỮ LIỆU).
    Lớp thiếu dữ liệu bị LOẠI KHỎI MẪU SỐ — quy tắc Phần 3 của prompt mà
    bản notebook cũ chưa bao giờ thực thi (điểm cũ cộng thẳng, thiếu = 0đ,
    tức là ngầm chấm 0 cho cái mình KHÔNG BIẾT).

    Hàm này KHÔNG BAO GIỜ được dùng để chặn hay để cứu một bộ lọc đã trượt.
    """
    tp, ts = 0.0, 0.0

    # L1 — cấu trúc & setup.
    # QUAN TRỌNG: "không tìm thấy setup" là một KẾT LUẬN, không phải THIẾU
    # DỮ LIỆU. Nó phải được chấm 0 và GIỮ trong mẫu số. Chỉ khi không đánh
    # giá được (setup_ma == "?") mới loại khỏi mẫu số.
    if setup_ma != "?":
        diem_setup = {"A": 1.0, "B": 0.95, "C": 0.8, "A-": 0.6,
                      "A-CHỜ": 0.5, "A?": 0.2}.get(setup_ma, 0.0)
        tp += diem_setup * TRONG_SO_V3["L1"]; ts += TRONG_SO_V3["L1"]

    # L2 — động lượng (thứ hạng RS đa khung, không phải RSI/MACD)
    if rank_min is not None and np.isfinite(_f(rank_min)):
        tp += (_f(rank_min) / 100) * TRONG_SO_V3["L2"]; ts += TRONG_SO_V3["L2"]

    # L3 — dòng tiền: CHỈ tính khi đủ số phiên. Thiếu -> loại khỏi mẫu số.
    if kn and kn.get("du_10"):
        ban = kn.get("so_phien_ban", 10)
        v = 1.0 if ban <= 2 else (0.7 if ban <= 4 else (0.3 if ban <= 6 else 0.0))
        tp += v * TRONG_SO_V3["L3"]; ts += TRONG_SO_V3["L3"]

    # L4 — liên thị trường (sức mạnh ngành)
    if rs_nganh_duong is not None:
        tp += (1.0 if rs_nganh_duong else 0.35) * TRONG_SO_V3["L4"]
        ts += TRONG_SO_V3["L4"]

    # L6 — tâm lý: phạt mua đuổi
    e = _f(ext_atr)
    if np.isfinite(e):
        v = 1.0 if abs(e) <= 1.5 else (0.5 if abs(e) <= 2.5 else 0.0)
        tp += v * TRONG_SO_V3["L6"]; ts += TRONG_SO_V3["L6"]

    # Mẫu quá mỏng thì KHÔNG chấm điểm. Một mã thiếu 3/5 lớp có thể ra 100đ
    # trên mẫu 35% và nhảy lên đầu bảng — đó là ảo giác, không phải chất lượng.
    if ts < MAU_TOI_THIEU_CHAM_DIEM:
        return None, int(ts)
    return round(tp / ts * 100, 1), int(ts)


print("✅ Ô 5B v3 — BỘ LỌC CỨNG + SETUP + THOÁT 2 TẦNG")
print("   F1 giai_doan_weinstein · F2 trend_template · F3 loi_nhuan_da_khung/")
print("   nen_tang_gan_nhat/xep_hang_pct · F4 adr_pct · F5 cong_chat_luong_vao")
print("   nhan_dien_setup · ke_hoach_thoat · rui_ro_pct_hien_hanh ·")
print("   cong_nhanh_ma1020 · tin_hieu_thoat_parabolic · diem_v3")
print("   ⚠️ F5 THAY THẾ cổng R:R. R:R vẫn được TÍNH và GHI LOG, nhưng")
print(f"      RR_LA_CONG_CHAN = {RR_LA_CONG_CHAN} → "
      + ("vẫn chặn như v7.6" if RR_LA_CONG_CHAN else "KHÔNG còn chặn lệnh."))

# ======================================================================
# Ô 6 — KHỐI NGOẠI THEO GIÁ TRỊ VND   [VÁ 5 + v7.3]
#   Chạy SAU 15h00 mỗi phiên. Sau 10 phiên mới đủ KN10.
#   --- SỬA v7.3 ---
#   [VÁ 27] except Exception gộp MỌI lỗi vào một thông điệp SAI.
#           RetryError(OSError) do mạng/đĩa bị báo là "gửi danh sách cột
#           để cập nhật bộ dò" -> chẩn đoán sai, người dùng sửa nhầm chỗ.
#           Nay phân loại: MẠNG / QUYỀN-ĐĨA / CỘT / KHÁC, mỗi loại một
#           hướng xử lý riêng.
#   [VÁ 28] Bóc RetryError để lấy nguyên nhân GỐC (tenacity chôn nó trong
#           last_attempt.exception()).
#   [VÁ 29] Chia lô + retry ở tầng của ta. price_board 75 mã một lần
#           rất dễ OSError/timeout.
#   [VÁ 30] Fallback nguồn theo NGUON_UU_TIEN thay vì cứng "VCI".
#   [VÁ 31] Ghi file NGUYÊN TỬ (tmp -> replace) + xác thực đọc lại,
#           tránh mất log khi ghi dở.
# ======================================================================
import os
import time
import pandas as pd
import numpy as np
from datetime import date

MA_CAN_LAY = sorted(set(list(DANH_MUC_HIEN_TAI.keys()) + UNG_VIEN))


# ---------------------------------------------------------------- #
# 6.1 TIỆN ÍCH CHẨN ĐOÁN                                            #
# ---------------------------------------------------------------- #
def _nguyen_nhan_goc(e, sau=0):
    """[VÁ 28] Bóc RetryError / ExceptionGroup để lấy lỗi thật bên trong."""
    if sau > 5:
        return e
    ten = type(e).__name__
    if ten == "RetryError":
        try:
            return _nguyen_nhan_goc(e.last_attempt.exception(), sau + 1)
        except Exception:
            return e
    if getattr(e, "__cause__", None) is not None:
        return _nguyen_nhan_goc(e.__cause__, sau + 1)
    return e


def _phan_loai_loi(e):
    """Trả (nhãn, hướng xử lý). Không đoán bừa 'lỗi cột' cho lỗi mạng."""
    g = _nguyen_nhan_goc(e)
    ten, msg = type(g).__name__, str(g).lower()

    if isinstance(g, (ImportError, ModuleNotFoundError)):
        return "THƯ VIỆN", [
            "Thiếu/hỏng thư viện vnstock trong runtime này.",
            "→ Chạy lại Ô 1 (cài đặt), rồi Runtime ▸ Restart session, rồi Ô 2."]

    if isinstance(g, RuntimeError) and ("cột" in str(g) or "column" in msg):
        return "CỘT DỮ LIỆU", [
            "Nguồn đổi tên cột — bộ dò không khớp.",
            "→ Copy dòng 'Cột nguồn trả về: [...]' ở trên và gửi để cập nhật bộ dò."]

    if ten in ("PermissionError", "FileNotFoundError", "IsADirectoryError") or \
       any(k in msg for k in ("read-only", "no such file", "permission",
                              "transport endpoint", "input/output error")):
        return "QUYỀN / ĐĨA", [
            f"Không ghi/đọc được đường dẫn: {DUONG_DAN_KN}",
            "Nguyên nhân thường gặp: Drive mount hỏng giữa chừng.",
            "→ Runtime ▸ Disconnect and delete runtime, chạy lại từ Ô 1."]

    if ten == "OSError" or any(k in msg for k in (
            "connection", "timed out", "timeout", "ssl", "temporarily",
            "unreachable", "reset by peer", "max retries", "429", "502", "503")):
        chi_tiet = str(g).strip()
        return "MẠNG / API", [
            "Nguồn dữ liệu không phản hồi (KHÔNG phải lỗi cột).",
            ("⚠️ OSError không kèm mô tả — cũng có thể do Drive rớt giữa chừng. "
             f"Trạng thái Drive hiện tại: {'GHI ĐƯỢC' if DRIVE_OK else 'HỎNG'}."
             if not chi_tiet else ""),
            "→ Chờ 3-5 phút rồi chạy lại DUY NHẤT Ô 6.",
            f"→ Nếu lặp lại: giảm KICH_THUOC_LO (đang {KICH_THUOC_LO}) hoặc "
            f"tăng CHO_KHI_LIMIT (đang {CHO_KHI_LIMIT}s)."]

    return f"KHÁC ({ten})", ["→ Gửi nguyên văn dòng [LỖI] ở trên."]


def _ghi_csv_an_toan(df, duong_dan):
    """[VÁ 31] Ghi nguyên tử + đọc lại xác thực. Trả (ok, số_dòng_đọc_lại, note)."""
    tmp = duong_dan + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, duong_dan)
    lai = pd.read_csv(duong_dan)
    if len(lai) != len(df):
        return False, len(lai), (f"⛔ Ghi {len(df)} dòng nhưng đọc lại {len(lai)} "
                                 f"— file KHÔNG toàn vẹn.")
    return True, len(lai), "✅ Ghi và đọc lại khớp."


# ---------------------------------------------------------------- #
# 6.2 DÒ CỘT                                                        #
# ---------------------------------------------------------------- #
def _lam_phang_cot(bg):
    if isinstance(bg.columns, pd.MultiIndex):
        bg.columns = ["_".join(str(x) for x in c if x and str(x) != "nan")
                      for c in bg.columns]
    bg.columns = [str(c) for c in bg.columns]
    return bg


def _tim_cot(cols, phai_co, khong_duoc_co=()):
    ra = []
    for c in cols:
        cl = c.lower()
        if all(k in cl for k in phai_co) and not any(k in cl for k in khong_duoc_co):
            ra.append(c)
    return ra


def _tai_price_board(ma_list, nguon):
    """Một lần gọi API cho một lô mã."""
    from vnstock import Trading
    return _lam_phang_cot(Trading(source=nguon).price_board(ma_list))


def _tai_theo_lo(ma_list, nguon, kich_thuoc=None, so_lan_thu=3):
    """[VÁ 29] Chia lô + retry. [VÁ 30] gọi cho từng nguồn ở tầng trên."""
    kich_thuoc = kich_thuoc or KICH_THUOC_LO
    lo = [ma_list[i:i + kich_thuoc] for i in range(0, len(ma_list), kich_thuoc)]
    phan, that_bai = [], []
    # [VÁ 35] Lỗi KHÔNG tự khỏi thì đừng retry — thư viện thiếu, sai chữ ký hàm...
    # retry 18 lần chỉ tốn 2 phút rồi vẫn hỏng, lại che mất nguyên nhân thật.
    KHONG_RETRY = (ImportError, ModuleNotFoundError, AttributeError,
                   TypeError, NameError, KeyError)
    for k, nhom in enumerate(lo, 1):
        for lan in range(1, so_lan_thu + 1):
            try:
                phan.append(_tai_price_board(nhom, nguon))
                print(f"   lô {k}/{len(lo)} ({len(nhom)} mã): OK")
                break
            except Exception as e:
                g = _nguyen_nhan_goc(e)
                if isinstance(g, KHONG_RETRY):
                    raise RuntimeError(
                        f"Lỗi KHÔNG tự khỏi ({type(g).__name__}: {g}) — "
                        f"dừng ngay, không retry.") from g
                if lan == so_lan_thu:
                    that_bai.extend(nhom)
                    print(f"   lô {k}/{len(lo)}: ⚠️ bỏ qua sau {so_lan_thu} lần "
                          f"— {type(g).__name__}")
                else:
                    cho = 5 * lan
                    print(f"   lô {k}/{len(lo)}: thử lại lần {lan + 1}/{so_lan_thu} "
                          f"sau {cho}s ({type(g).__name__})")
                    time.sleep(cho)
        time.sleep(60 / max(GIOI_HAN_RPM, 1))
    if not phan:
        raise RuntimeError(f"Không lô nào tải được từ nguồn {nguon}.")
    return pd.concat(phan, ignore_index=True), that_bai


def thu_thap_khoi_ngoai(ma_list):
    """[VÁ 30] Thử lần lượt các nguồn trong NGUON_UU_TIEN + VCI."""
    nguon_thu = list(dict.fromkeys(list(NGUON_UU_TIEN) + ["VCI"]))
    loi_cuoi = None
    for nguon in nguon_thu:
        try:
            print(f"→ Thử nguồn {nguon} ({len(ma_list)} mã, "
                  f"lô {KICH_THUOC_LO})...")
            bg, thieu = _tai_theo_lo(ma_list, nguon)
            break
        except Exception as e:
            g = _nguyen_nhan_goc(e)
            if "KHÔNG tự khỏi" in str(e):
                raise                      # [VÁ 35] đừng thử nguồn khác vô ích
            loi_cuoi = e
            print(f"   ⚠️ Nguồn {nguon} thất bại: {type(g).__name__}")
            continue
    else:
        raise loi_cuoi if loi_cuoi else RuntimeError("Không nguồn nào phản hồi.")

    cols = list(bg.columns)
    c_ma = (_tim_cot(cols, ["symbol"]) or _tim_cot(cols, ["ticker"]))
    if not c_ma:
        raise RuntimeError(f"Không dò được cột mã.\nCột nguồn trả về: {cols}")
    c_ma = c_ma[0]

    v_mua = _tim_cot(cols, ["foreign", "buy", "value"]) or _tim_cot(cols, ["fr", "buy", "val"])
    v_ban = _tim_cot(cols, ["foreign", "sell", "value"]) or _tim_cot(cols, ["fr", "sell", "val"])
    kl_mua = _tim_cot(cols, ["foreign", "buy"], khong_duoc_co=["value", "val"])
    kl_ban = _tim_cot(cols, ["foreign", "sell"], khong_duoc_co=["value", "val"])
    c_gia = (_tim_cot(cols, ["match", "price"]) or _tim_cot(cols, ["close"])
             or _tim_cot(cols, ["last", "price"]))

    out = pd.DataFrame()
    out["ma"] = bg[c_ma].astype(str).str.upper()

    if v_mua and v_ban:
        out["kn_gia_tri"] = (pd.to_numeric(bg[v_mua[0]], errors="coerce")
                             - pd.to_numeric(bg[v_ban[0]], errors="coerce"))
        cach = f"cột giá trị sẵn có ({v_mua[0]} - {v_ban[0]}) | nguồn {nguon}"
    elif kl_mua and kl_ban and c_gia:
        kl_rong = (pd.to_numeric(bg[kl_mua[0]], errors="coerce")
                   - pd.to_numeric(bg[kl_ban[0]], errors="coerce"))
        gia = pd.to_numeric(bg[c_gia[0]], errors="coerce")
        he_so = 1000 if gia.median() < 1000 else 1
        out["kn_gia_tri"] = kl_rong * gia * he_so
        out["kn_khoi_luong"] = kl_rong
        cach = (f"KL ({kl_mua[0]} - {kl_ban[0]}) × giá ({c_gia[0]}) × {he_so} "
                f"| nguồn {nguon}")
    else:
        raise RuntimeError(
            "Không dò được cột khối ngoại.\n"
            f"Cột nguồn trả về: {cols}\n"
            "→ Gửi danh sách cột này để cập nhật bộ dò.")

    out = out.dropna(subset=["kn_gia_tri"])
    return out, cach, thieu


def kiem_dinh_don_vi(series_gia_tri):
    """Phát hiện nhầm đơn vị: giá trị ròng thật phải ở thang tỷ VND."""
    s = pd.to_numeric(series_gia_tri, errors="coerce").abs().dropna()
    if len(s) == 0:
        return False, "Không có số liệu."
    med = s.median()
    if med < 1e6:
        return False, (f"⛔ Trung vị |KN| = {med:,.0f} — quá nhỏ để là VND. "
                       f"Nhiều khả năng đang ghi SỐ LƯỢNG CP. KHÔNG dùng cho Lớp 3.")
    if med > 1e12:
        return False, f"⛔ Trung vị |KN| = {med:,.0f} — quá lớn, nghi nhân nhầm hệ số."
    return True, f"✅ Trung vị |KN| = {med / 1e9:,.2f} tỷ VND — thang giá trị hợp lý."


# ---------------------------------------------------------------- #
# 6.3 CHẠY                                                          #
# ---------------------------------------------------------------- #
def _ngay_phien():
    """
    [VÁ 34] LỖI v7.3: `"NGAY_MOC" in dir()` chỉ kiểm tra biến TỒN TẠI.
    Ô 3 khởi tạo NGAY_MOC = None rồi mới gán trong hàm -> nếu Ô 6 chạy
    trước khi hàm đó được gọi, biến là None -> None.strftime() = AttributeError.
    Ô 6 phải chạy được ĐỘC LẬP: không có mốc chuẩn thì tự suy ra ngày phiên.
    """
    nm = globals().get("NGAY_MOC")
    if nm is not None:
        try:
            return pd.to_datetime(nm).strftime("%Y-%m-%d"), "mốc chuẩn từ Ô 3"
        except Exception:
            pass
    # Không có mốc chuẩn -> suy ra phiên gần nhất theo giờ VN
    bh = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=7)
    ngay = bh.normalize()
    ghi_chu = "tự suy (chưa chạy Ô 3)"
    if ngay.weekday() >= 5:                       # T7/CN -> lùi về thứ Sáu
        ngay -= pd.Timedelta(days=ngay.weekday() - 4)
        ghi_chu += " — cuối tuần, lùi về thứ Sáu"
    elif bh.hour < 15:                            # chưa đóng cửa
        ghi_chu += f" — ⚠️ đang {bh:%H:%M}, phiên CHƯA ĐÓNG (số liệu KN chưa chốt)"
    return ngay.strftime("%Y-%m-%d"), ghi_chu



def chay_khoi_ngoai():
    """Ô 6 — thu thập khối ngoại và ghi log tích luỹ. Lỗi ở đây KHÔNG
    chặn phần còn lại: hệ quả duy nhất là Lớp 3 bị loại khỏi mẫu số."""
    global NGAY_HOM_NAY
    NGAY_HOM_NAY, _nguon_ngay = _ngay_phien()

    print("=" * 66)
    print(f"KHỐI NGOẠI — phiên {NGAY_HOM_NAY}  [{_nguon_ngay}]")
    print("=" * 66)
    if "chưa chạy Ô 3" in _nguon_ngay:
        print("   ℹ️ Chạy Ô 3 trước sẽ lấy đúng mốc phiên của VNINDEX.")
        print("      Ô 6 vẫn chạy được độc lập, chỉ cần ngày ghi log đúng.")
    if "CHƯA ĐÓNG" in _nguon_ngay:
        print("   🚨 KN trong phiên KHÔNG phải số chốt — chạy lại sau 15h00.")
    try:
        kn_hom_nay, cach_tinh, ma_thieu = thu_thap_khoi_ngoai(MA_CAN_LAY)
        ok_dv, note_dv = kiem_dinh_don_vi(kn_hom_nay["kn_gia_tri"])

        print(f"\nCách tính : {cach_tinh}")
        print(f"Kiểm định : {note_dv}")
        print(f"Số mã     : {len(kn_hom_nay)}/{len(MA_CAN_LAY)}")
        if ma_thieu:
            print(f"⚠️ Thiếu {len(ma_thieu)} mã: {', '.join(ma_thieu)}")
            print("   → Các mã này sẽ hiện KN10 = '—' ở Ô 7.")

        hien = kn_hom_nay.copy()
        hien["kn_ty_vnd"] = (hien["kn_gia_tri"] / 1e9).round(2)
        hien = hien.sort_values("kn_ty_vnd")
        print("\n5 mã bán ròng mạnh nhất:")
        print(hien.head(5)[["ma", "kn_ty_vnd"]].to_string(index=False))
        print("\n5 mã mua ròng mạnh nhất:")
        print(hien.tail(5)[["ma", "kn_ty_vnd"]].to_string(index=False))

        # --- Ghi log tích lũy ---
        kn_hom_nay.insert(0, "ngay", NGAY_HOM_NAY)
        if os.path.exists(DUONG_DAN_KN):
            cu = pd.read_csv(DUONG_DAN_KN)
            if "ngay" in cu.columns:
                cu = cu[cu["ngay"].astype(str) != NGAY_HOM_NAY]
            kn_hom_nay = pd.concat([cu, kn_hom_nay], ignore_index=True)

        ok_ghi, n_lai, note_ghi = _ghi_csv_an_toan(kn_hom_nay, DUONG_DAN_KN)
        so_phien = kn_hom_nay["ngay"].nunique()
        print(f"\n💾 {DUONG_DAN_KN}")
        print(f"   {note_ghi} ({n_lai} dòng)")
        print(f"   Lịch sử tích lũy: {so_phien}/{KN_SO_PHIEN} phiên", end=" ")
        print("— ĐỦ cho KN10 ✅" if so_phien >= KN_SO_PHIEN
              else f"— còn thiếu {KN_SO_PHIEN - so_phien} phiên ⚠️")
        if so_phien < KN_SO_PHIEN:
            print("   → Lớp 3 (20% trọng số) vẫn bị loại khỏi mẫu số cho tới khi đủ.")
        if not ok_dv:
            print("\n🚨 KHÔNG dùng file này cho Lớp 3 cho tới khi sửa được đơn vị.")

    except Exception as e:
        g = _nguyen_nhan_goc(e)
        nhan, huong = _phan_loai_loi(e)
        print("\n" + "=" * 66)
        print(f"[LỖI — {nhan}] {type(g).__name__}: {g}")
        if type(g).__name__ != type(e).__name__:
            print(f"   (lớp ngoài: {type(e).__name__} — đã bóc để lấy nguyên nhân gốc)")
        print("=" * 66)
        for h in huong:
            if h:
                print(f"   {h}")
        print("\n   ℹ️ Ô 6 hỏng KHÔNG chặn Ô 7-10 chạy. Hệ quả duy nhất:")
        print("      Lớp 3 (20%) bị loại khỏi mẫu số, điểm tổng hợp tính trên 80% còn lại.")


# ======================================================================
# Ô 7 — SCREENER CHÍNH
#   [VÁ 1] Cổng đóng -> ghi đè mọi nhãn ✅/🔥 thành 👀
#   [VÁ 2] RS12w < RS_TOI_THIEU_SETUP -> cấm gắn SETUP
#   [VÁ 3] R:R cấu trúc cho từng mã, TP/SL từ pivot
#   [VÁ 6] Bộ lọc ngành chỉ chạy khi danh mục khác rỗng
#   [VÁ 7] Cờ rủi ro unwind FTSE
# ======================================================================
import os
import pandas as pd
import numpy as np
from datetime import datetime, date


# ---------------------------------------------------------------- #
# 7.1 UNIVERSE                                                      #
# ---------------------------------------------------------------- #
def xay_universe():
    if DANH_SACH_TAY:
        return [m.upper() for m in DANH_SACH_TAY], "DANH_SACH_TAY (tự chọn)"
    if os.path.exists(DUONG_DAN_UNI):
        try:
            u = pd.read_csv(DUONG_DAN_UNI)
            u = u.sort_values("GTGD20", ascending=False).head(SO_MA_UNIVERSE)
            ds = u["Mã"].astype(str).str.upper().tolist()
            if len(ds) >= 20:
                ngay = u["NgayCapNhat"].iloc[0] if "NgayCapNhat" in u.columns else "?"
                return ds, f"TOP {len(ds)} theo GTGD20 (cập nhật {ngay})"
        except Exception as e:
            print(f"   ⚠️ Lỗi đọc universe_rank.csv: {e}")
    n = len(UNG_VIEN)
    return UNG_VIEN, (f"LẦN ĐẦU — quét {n} mã để xếp hạng GTGD "
                      f"(~{int(n / GIOI_HAN_RPM) + 1} phút)")


# ---------------------------------------------------------------- #
# 7.2 ĐỌC KN10 THEO GIÁ TRỊ                                         #
# ---------------------------------------------------------------- #
def nap_khoi_ngoai():
    if not os.path.exists(DUONG_DAN_KN):
        return None, None, f"THIẾU file {DUONG_DAN_KN} — chạy Ô 6 mỗi phiên"
    try:
        kn = pd.read_csv(DUONG_DAN_KN)
    except Exception as e:
        return None, None, f"Lỗi đọc: {e}"

    cols = {c.lower().strip(): c for c in kn.columns}
    c_ma = next((g for l, g in cols.items() if l in ("ma", "symbol", "ticker")), None)
    c_gt = next((g for l, g in cols.items()
                 if "gia_tri" in l or "value" in l or l == "kn_gia_tri"), None)
    c_ngay = next((g for l, g in cols.items() if l in ("ngay", "date", "time")), None)
    if not (c_ma and c_gt and c_ngay):
        return None, None, f"Không dò được cột. Hiện có: {list(kn.columns)}"

    ok_dv, note_dv = kiem_dinh_don_vi(kn[c_gt])
    if not ok_dv:
        return None, None, f"{note_dv} → LOẠI Lớp 3 khỏi mẫu số"

    kn[c_ngay] = pd.to_datetime(kn[c_ngay], errors="coerce")
    kn = kn.dropna(subset=[c_ngay]).sort_values(c_ngay)
    so_phien = kn[c_ngay].nunique()

    def tra(ma):
        # [SỬA v7.4 — BUG D] Hai lỗi trong bản cũ:
        #   1) KHÔNG khử trùng ngày -> nếu log có 2 dòng cùng phiên cho 1 mã
        #      (chạy Ô 6 hai lần) thì tail(10) lấy nhầm 10 DÒNG chứ không phải
        #      10 PHIÊN -> so_phien_ban sai.
        #   2) Thiếu 1 phiên là trả None -> mất TOÀN BỘ dữ liệu, kể cả khi đã
        #      có 8-9 phiên. Lớp 3 bị loại hoàn toàn thay vì hạ độ tin cậy.
        s = kn[kn[c_ma].astype(str).str.upper() == ma.upper()]
        s = (s.drop_duplicates(subset=[c_ngay], keep="last")
               .sort_values(c_ngay).tail(KN_SO_PHIEN))
        gt = pd.to_numeric(s[c_gt], errors="coerce").dropna()
        n = len(gt)
        if n == 0:
            return None
        return {"so_phien_co": n,
                "du_10": bool(n >= KN_SO_PHIEN),
                "so_phien_ban": int((gt < 0).sum()),
                "tong_ty_vnd": round(float(gt.sum()) / 1e9, 2),
                "chuoi_ban_lien_tiep": int(_chuoi_cuoi(gt.tolist()))}

    return tra, so_phien, f"OK ({len(kn)} dòng / {so_phien} phiên) — {note_dv}"


def _chuoi_cuoi(vals):
    """Số phiên bán ròng LIÊN TIẾP tính từ phiên gần nhất."""
    n = 0
    for v in reversed(vals):
        if v < 0:
            n += 1
        else:
            break
    return n


# ---------------------------------------------------------------- #
# 7.3 TẦNG 0 — CỔNG CHẾ ĐỘ                                          #
# ---------------------------------------------------------------- #
print("=" * 66)
print("TẦNG -1 — UNIVERSE")
print("=" * 66)
DANH_SACH, uni_note = xay_universe()
print(f"{uni_note}\nSố mã: {len(DANH_SACH)} | API: {GIOI_HAN_RPM} req/phút "
      f"| Ước tính ~{int(len(DANH_SACH) / GIOI_HAN_RPM) + 1} phút")

print("\n" + "=" * 66)
print("TẦNG 0 — CỔNG CHẾ ĐỘ THỊ TRƯỜNG")
print("=" * 66)
NGUON, vni_df = do_nguon()
if vni_df is None:
    raise SystemExit("⚠️ Không dò được nguồn (KBS/VCI). Chờ 5-10 phút rồi chạy lại.")
print(f"Nguồn: {NGUON} | Số phiên VNINDEX: {len(vni_df)}\n")

# ---------------------------------------------------------------- #
# [PORT] CHẶN CHẠY LẠI KHI CHƯA CÓ PHIÊN MỚI                        #
# ---------------------------------------------------------------- #
# Cron chạy T2–T6, nhưng thị trường nghỉ lễ thì nguồn vẫn trả nến CŨ. Chạy
# tiếp sẽ: (a) đốt ~8 phút quota API cho kết quả y hệt, (b) ghi thêm một dòng
# khối ngoại mang ngày KHÔNG PHẢI phiên giao dịch — bẩn đúng cái log mà KN10
# phụ thuộc. Không có phiên mới thì dừng, và dừng là đúng.
_phien_moi = str(pd.to_datetime(NGAY_MOC).date())
_phien_cu = None
try:
    # LƯU Ý: KHÔNG đặt tên handle là `_f`. Ở module scope, `with ... as _f`
    # ghi đè vĩnh viễn hàm helper _f() (float an toàn) — biến KHÔNG bị xoá
    # khi thoát khối with. Mọi lời gọi _f(...) sau đó nổ TypeError.
    with open("out/latest.json", encoding="utf-8") as _fh:
        _phien_cu = _json.load(_fh).get("phien")
except Exception:
    pass
if _phien_cu == _phien_moi and not _env_raw("CHAY_LAI"):
    print(f"⏹ Phiên {_phien_moi} đã có trong out/latest.json — chưa có phiên "
          f"mới, dừng tại đây.")
    print("   Muốn chạy lại đè lên: đặt biến môi trường CHAY_LAI=1.")
    raise SystemExit(0)

# [PORT] Ô 6 chạy Ở ĐÂY, không phải trước Ô 7 như thứ tự Colab.
# Trong Colab, Ô 6 chạy trước Ô 3 nên NGAY_MOC còn None -> _ngay_phien() tự
# suy ngày theo đồng hồ. Hôm nào nguồn trả nến trễ, log khối ngoại mang ngày
# HÔM NAY trong khi giá là phiên CŨ — hai lịch sử lệch nhau âm thầm.
# Đặt sau do_nguon() thì NGAY_MOC đã có, log ghi đúng mốc phiên của giá.
chay_khoi_ngoai()
print()

KQ_CONG = tinh_de_risk(vni_df)
DE_RISK_LEVEL = KQ_CONG["DE_RISK_LEVEL"]
CONG_MO = KQ_CONG["CONG_MO"]

RR_IDX = tinh_rr(vni_df, KQ_CONG["GIA"], atr=None, de_risk_level=DE_RISK_LEVEL,
                 tp_min_pct=TP_CACH_TOI_THIEU_PCT_IDX,
                 sl_min_pct=SL_CACH_TOI_THIEU_PCT_IDX)
in_cong(KQ_CONG, RR_IDX)

vni = tinh_chi_bao(vni_df)
_, vni_tuan_note = kiem_tra_tuan(vni_df)

# Kiểm tra ĐÃ GÃY theo định nghĩa Phần 3
c = vni_df["close"]
da_gay_a = bool(c.iloc[-1] < INVALIDATION and
                vni_df["volume"].iloc[-1] >= vni["nguong_vol_120"])
da_gay_b = bool(len(c) >= 2 and c.iloc[-1] < INVALIDATION and c.iloc[-2] < INVALIDATION)
# [SỬA v7.4 — BUG E] Điều kiện (b2) "đóng cửa TUẦN dưới ngưỡng" — theo Phần 3 là
# điều kiện CÓ HIỆU LỰC CAO NHẤT — chưa bao giờ được kiểm tra ở tầng chỉ số.
# kiem_tra_gay() có code cho (b2) nhưng nằm ở Ô 9 và KHÔNG được gọi cho VNINDEX
# (hàm chết). Hệ quả: chỉ số có thể đóng cửa TUẦN dưới invalidation mà cổng vẫn
# báo 🟢 CHƯA GÃY.
_w_dong = gop_tuan(vni_df, bo_tuan_dang_chay=True)
da_gay_c = bool(len(_w_dong) and float(_w_dong["close"].iloc[-1]) < INVALIDATION)
DA_GAY = da_gay_a or da_gay_b or da_gay_c
_ly_do_gay = [t for t, ok in (("(a) close ngày + vol≥120%", da_gay_a),
                              ("(b1) 2 phiên liên tiếp", da_gay_b),
                              ("(b2) ĐÓNG CỬA TUẦN", da_gay_c)) if ok]
print(f"Kiểm tra ĐÃ GÃY ({INVALIDATION:,.2f}): "
      f"{'🔴 ĐÃ GÃY — ' + '; '.join(_ly_do_gay) if DA_GAY else '🟢 CHƯA GÃY'} "
      f"| Tuần: {vni_tuan_note}")
print(f"   (b2) đóng cửa TUẦN đã đóng gần nhất: "
      f"{float(_w_dong['close'].iloc[-1]):,.2f} vs {INVALIDATION:,.2f}")

# Bậc giải ngân
hom_nay = date.today()
if not CONG_MO:
    BAC, TRAN_NAV, HE_SO_SIZE = 0, 0, 0.0
    mo_ta_bac = "Cổng đóng — 0% NAV. Không mở vị thế mới."
elif hom_nay <= NGAY_FTSE_HIEU_LUC:
    BAC, TRAN_NAV, HE_SO_SIZE = 1, 30, 0.5
    mo_ta_bac = (f"Bậc 1 — trần 30% NAV, size ×0.5 "
                 f"(rủi ro unwind FTSE tới {NGAY_FTSE_HIEU_LUC:%d/%m/%Y})")
elif (hom_nay - NGAY_FTSE_HIEU_LUC).days <= NGAY_CHO_SAU_FTSE:
    BAC, TRAN_NAV, HE_SO_SIZE = 1, 30, 0.5
    mo_ta_bac = "Bậc 1 — chờ xác nhận 1 đóng cửa tuần sau rebalancing FTSE"
else:
    BAC, TRAN_NAV, HE_SO_SIZE = 2, 60, 1.0
    mo_ta_bac = "Bậc 2 — trần 60% NAV, size đầy đủ"
TRAN_BAC_GOC = TRAN_NAV          # trần của BẬC, trước mọi điều chỉnh cổng
# [VÁ 16] Cổng mở nhưng MỎNG -> hạ trần NAV, không hạ size.
# [v7.4] Ở chế độ B, độ mỏng cổng ĐÃ nằm trong BANG_TRAN_CONG(D). Áp thêm
# TRAN_NAV_CONG_MONG ở đây là phạt CHỒNG cùng một rủi ro hai lần.
if (CHE_DO_CONG != "B" and CONG_MO
        and not KQ_CONG.get("CONG_DAY", True) and TRAN_NAV > TRAN_NAV_CONG_MONG):
    TRAN_NAV = TRAN_NAV_CONG_MONG
    mo_ta_bac += (f" | ⚠️ CỔNG MỎNG ({KQ_CONG['DAY_CONG_ATR']}×ATR) "
                  f"→ trần NAV hạ còn {TRAN_NAV_CONG_MONG}% "
                  f"tới khi đóng cửa ≥ {KQ_CONG['MUC_CONG_DAY']:,.2f}")
print(f"Bậc giải ngân   : {mo_ta_bac}")

# ---- NGÂN SÁCH GIẢI NGÂN [PHƯƠNG ÁN B] ----
_ct_tuan_idx = chi_bao_tuan(vni_df)
NS = tinh_ngan_sach(KQ_CONG, vni, _ct_tuan_idx, tran_bac=TRAN_BAC_GOC)
NGAN_SACH_NAV = NS["NGAN_SACH_PCT"] if CHE_DO_CONG == "B" else TRAN_NAV
if CHE_DO_CONG == "B":
    in_ngan_sach(NS)
    print(f"➜ TRẦN GIẢI NGÂN HIỆU LỰC: {NGAN_SACH_NAV:.2f}% NAV "
          f"(mọi lệnh bị cap bởi mốc này)")

# ---------------------------------------------------------------- #
# [v3] CỔNG THỊ TRƯỜNG 2 TẦNG                                       #
#   Tầng CHẬM  = DE_RISK (MA20W/MA200D) — đã tính ở trên.           #
#   Tầng NHANH = MA10 vs MA20 NGÀY của chỉ số (Kullamägi).          #
#   Kullamägi ước tính: tuân thủ đúng bộ lọc nhanh này sẽ cắt ~90%  #
#   khoản lỗ 2022 của chính ông. Nó KHÔNG phải tuỳ chọn.            #
# ---------------------------------------------------------------- #
STAGE_IDX  = {"STAGE": None, "TEN": "v3 TẮT", "GHI_CHU": ""}
CONG_NHANH = {"OK": None, "F": 1.0, "GHI_CHU": "v3 TẮT"}
RUI_RO_V3, LY_DO_RUI_RO = RUI_RO_MOI_LENH_PCT, "khung v2 — cố định"
CHAN_INDEX = CHAN_NHANH = None

if BAT_KHUNG_V3 and "giai_doan_weinstein" not in globals():
    raise NameError(
        "BAT_KHUNG_V3=True nhưng chưa chạy Ô 5B. "
        "Thứ tự đúng: Ô 4 → Ô 4B → Ô 5 → Ô 5B → Ô 6 → Ô 7. "
        "(Hoặc đặt BAT_KHUNG_V3=False ở Ô 2 để dùng lại nguyên vẹn v7.6-B.)")

if BAT_KHUNG_V3:
    # Chốt chặn: nếu có chỗ nào lại ghi đè _f bằng file handle / giá trị khác,
    # báo lỗi NGAY tại đây với type thật, thay vì TypeError mơ hồ sâu bên trong
    # giai_doan_weinstein().
    assert callable(_f), f"_f đã bị ghi đè, hiện là {type(_f).__name__}"
    STAGE_IDX  = giai_doan_weinstein(vni_df)
    CONG_NHANH = cong_nhanh_ma1020(vni_df)
    print("\n" + "-" * 66)
    print("CỔNG THỊ TRƯỜNG 2 TẦNG  [v3]")
    print(f"  Tầng CHẬM  — Weinstein : {STAGE_IDX['TEN']}  ({STAGE_IDX['GHI_CHU']})")
    print(f"  Tầng NHANH — MA10/MA20 : {CONG_NHANH['GHI_CHU']}")
    _ns0 = float(NGAN_SACH_NAV)
    NGAN_SACH_NAV, _note_cn = ap_cong_nhanh(NGAN_SACH_NAV, CONG_NHANH)
    print(f"  Ngân sách {_ns0:.2f}% {_note_cn} → {NGAN_SACH_NAV:.2f}% NAV")

    if STAGE_IDX.get("STAGE") is not None and STAGE_IDX["STAGE"] not in STAGE_CHO_PHEP:
        NGAN_SACH_NAV = 0.0
        CHAN_INDEX = f"chỉ số Stage {STAGE_IDX['STAGE']} (v3 chỉ mua ở Stage 2)"
        print(f"  ⛔ {CHAN_INDEX} → CẤM mở vị thế mới, ngân sách về 0% NAV.")
        print("     Weinstein: không mua trong Stage 3/4, bất kể mã đẹp đến đâu.")
    elif STAGE_IDX.get("STAGE") is None:
        print("  ❔ Không xác định được Stage chỉ số → giữ ngân sách, nhưng mọi")
        print("     kết luận phụ thuộc F1 phải đánh dấu ĐỘ TIN CẬY THẤP.")

    if BAT_CONG_MA1020 and CONG_NHANH.get("OK") is False:
        CHAN_NHANH = "MA10 < MA20 của chỉ số — breakout thất bại hàng loạt"
        print(f"  ⏳ {CHAN_NHANH} → KHÔNG mở breakout mới, chỉ giữ/quản lý.")

    RUI_RO_V3, LY_DO_RUI_RO = rui_ro_pct_hien_hanh(
        CHUOI_R_GAN_NHAT, CONG_NHANH.get("OK"), STAGE_IDX.get("STAGE"))
    print(f"  Progressive exposure   : {RUI_RO_V3:g}% NAV rủi ro/lệnh — {LY_DO_RUI_RO}")
    print("-" * 66)

# [VÁ 19] BẾ TẮC CẤP CHỈ SỐ: cửa sổ [cổng, GiáTrầnRR] rỗng.
BE_TAC_IDX = False
if CONG_MO and RR_IDX.get("GIA_TRAN_RR") and RR_IDX["GIA_TRAN_RR"] < DE_RISK_LEVEL:
    BE_TAC_IDX = True
    _hut = DE_RISK_LEVEL - RR_IDX["GIA_TRAN_RR"]
    if CHE_DO_CONG == "B":
        print(f"ℹ️ BẾ TẮC CHỈ SỐ (THAM KHẢO — KHÔNG CHẶN LỆNH ở chế độ B): "
              f"cổng {DE_RISK_LEVEL:,.2f} > GiáTrầnRR "
              f"{RR_IDX['GIA_TRAN_RR']:,.2f}, hụt {_hut:,.2f} điểm.")
        print("   [B] Ý nghĩa duy nhất: chỉ số đang xa MA20W. Điều đó ĐÃ được "
              "phản ánh vào f_ext của ngân sách — không cần chặn lần thứ hai.")
    else:
        print(f"🚨 BẾ TẮC CHỈ SỐ: cổng {DE_RISK_LEVEL:,.2f} > GiáTrầnRR "
              f"{RR_IDX['GIA_TRAN_RR']:,.2f} — hụt {_hut:,.2f} điểm. "
              f"Không tồn tại giá thỏa cả hai điều kiện.")
        print("   → Lối ra: (a) MA20D dâng làm ExtATR tự nén, (b) pivot đáy mới "
              "cao hơn, (c) MA20W suy giảm. KHÔNG hạ chuẩn R:R.")

tra_kn, kn_so_phien, kn_note = nap_khoi_ngoai()
print(f"Khối ngoại (KN10): {kn_note}")


# ---------------------------------------------------------------- #
# 7.4 QUÉT                                                          #
# ---------------------------------------------------------------- #
# [SỬA v7.4 — BUG I] Không có checkpoint: quét 75 mã, chết ở mã 15 -> mất
# sạch 14 mã đã tải, phải quét lại từ đầu (và lại đốt quota từ đầu).
# TIEN_TRINH sống qua các lần chạy lại Ô 7 trong CÙNG runtime.
# [v3] Dòng checkpoint của bản cũ THIẾU các trường v3. Trộn vào bảng mới sẽ
# làm TẦNG 2 chấm "❔ THIẾU" cho những mã thực ra đã quét xong. Khoá theo phiên bản.
_TT_VER = "v8.0-v3"
if ("TIEN_TRINH" not in globals() or not KHOI_PHUC_TIEN_TRINH
        or globals().get("TIEN_TRINH_VER") != _TT_VER):
    if globals().get("TIEN_TRINH") and globals().get("TIEN_TRINH_VER") != _TT_VER:
        print("♻️ Checkpoint thuộc phiên bản khác → xoá, quét lại từ đầu.")
    TIEN_TRINH = {}
TIEN_TRINH_VER = _TT_VER
ket_qua, loi, ma_cu = [], [], []
# [v8.1 / PORT] Tương đương CACHE dùng chung của Ô 7↔Ô 9/10 trong notebook.
# Ở đây không cần khoá theo NGAY_MOC: mỗi lần chạy Actions là một tiến trình
# mới, không có runtime sống qua đêm để phục vụ nến hôm qua.
OHLCV_CACHE = {}
ma_dang_giu = set(DANH_MUC_HIEN_TAI.keys())
nganh_dang_giu = {NGANH.get(m) for m in ma_dang_giu if NGANH.get(m)}
so_tc_dang_giu = sum(1 for m in ma_dang_giu if NGANH.get(m) in NHOM_TAI_CHINH)

print(f"\nBắt đầu quét {len(DANH_SACH)} mã...\n")
_da_co = sum(1 for m in DANH_SACH if m in TIEN_TRINH)
if _da_co:
    print(f"♻️ Khôi phục {_da_co}/{len(DANH_SACH)} mã đã quét ở lần chạy trước "
          f"— chỉ tải phần còn thiếu.\n")

for i, ma in enumerate(DANH_SACH, 1):
    if ma in TIEN_TRINH:                       # [BUG I] đã có -> không gọi API lại
        ket_qua.append(TIEN_TRINH[ma])
        continue
    try:
        df, src_ma, ngay_ma, bi_cu = lay_du_lieu_moi_nhat(ma)
    except KeyboardInterrupt:
        print(f"\n⏹ Dừng tay ở mã {ma} ({i}/{len(DANH_SACH)}). "
              f"Đã lưu {len(TIEN_TRINH)} mã — chạy lại Ô 7 để tiếp tục.")
        break
    except BaseException as e:                 # kể cả SystemExit lọt lưới
        loi.append(ma)
        print(f" [{i}/{len(DANH_SACH)}] {ma}: ⚠️ {type(e).__name__} — bỏ qua, "
              f"tiến trình {len(TIEN_TRINH)} mã vẫn được giữ")
        continue
    if df is None:
        loi.append(ma)
        print(f" [{i}/{len(DANH_SACH)}] {ma}: ⚠️ lỗi")
        continue

    OHLCV_CACHE[ma] = df
    x = tinh_chi_bao(df)
    tuan_ok, tuan_note = kiem_tra_tuan(df)
    # [PHƯƠNG ÁN B — cổng mã S1] Chỉ số không còn phủ quyết bằng R:R,
    # nên tầng mã phải tự gánh: giá mã phải đứng trên MA20W của CHÍNH NÓ.
    ma20w_ok, ma20w_note = (tren_ma20w(df) if BAT_COng_MA_MA20W else (True, ""))
    _canh = ""
    if bi_cu:
        ma_cu.append(ma)
        _canh = f"  ⚠️ DỮ LIỆU CŨ ({ngay_ma:%d/%m} < {NGAY_MOC:%d/%m})"
    print(f" [{i}/{len(DANH_SACH)}] {ma}: OK (GTGD {x['gtgd20']:.0f} tỷ){_canh}")

    tk_ok = x["gtgd20"] >= GTGD_TOI_THIEU
    xu_huong_ok = bool(x["close"] > x["ma50"] and x["ma20"] > x["ma50"]
                       and x["ma50_doc_len"] and x["cach_dinh"] <= CACH_DINH_52W)
    dao_roi = bool(x["close"] < x["ma50"] and x["ma20"] < x["ma50"])

    if not np.isnan(x["ret_12w"]) and not np.isnan(vni["ret_12w"]):
        rs_12w = x["ret_12w"] - vni["ret_12w"]
        rs_4w = x["ret_4w"] - vni["ret_4w"]
        rs_ok = rs_12w > 0
    else:
        rs_12w = rs_4w = np.nan
        rs_ok = None

    da_chay_xa = bool((not np.isnan(x["ext_atr"]) and x["ext_atr"] > HE_SO_DUOI)
                      or x["rsi"] > 70
                      or (not np.isnan(x["run_5p"]) and x["run_5p"] > 15))

    # ---- [VÁ 2] guard RS cho SETUP ----
    rs_du_manh = (not np.isnan(rs_12w)) and rs_12w >= RS_TOI_THIEU_SETUP
    setup_ky_thuat = bool(
        (not np.isnan(x["ext_atr"]) and abs(x["ext_atr"]) <= HE_SO_SETUP)
        and RSI_SETUP[0] <= x["rsi"] <= RSI_SETUP[1]
        and (np.isnan(x["vol5_vs_mav20"]) or x["vol5_vs_mav20"] < 110))
    setup_ok = setup_ky_thuat and rs_du_manh

    ghi_chu = []
    # [VÁ 20] Cảnh báo RS phải ĐỘC LẬP với ExtATR.
    # Bản cũ chỉ bắn khi setup_ky_thuat=True -> MBB (RS 4.2, ExtATR 2.15)
    # rớt chuẩn RS mà không có dòng nào ghi lại.
    if (not np.isnan(rs_12w)) and not rs_du_manh:
        if setup_ky_thuat:
            ghi_chu.append(f"ExtATR thấp nhưng RS12w {rs_12w:.1f} "
                           f"< {RS_TOI_THIEU_SETUP} → YẾU, không phải nén")
        else:
            ghi_chu.append(f"RS12w {rs_12w:.1f} < {RS_TOI_THIEU_SETUP} "
                           f"→ CHẶN SETUP (bất kể ExtATR)")

    # ---- Phân loại ----
    if not tk_ok:
        trang_thai = "❌ LOẠI (thanh khoản)"
    elif dao_roi:
        trang_thai = "❌ LOẠI (dao rơi)"
    elif not xu_huong_ok:
        trang_thai = "❌ LOẠI (xu hướng)"
    elif rs_ok is False:
        trang_thai = "⚠️ YẾU HƠN INDEX"
    elif da_chay_xa:
        trang_thai = "🔥 ĐÃ CHẠY XA — chờ pullback MA20"
    elif setup_ok:
        trang_thai = "✅ SETUP — soi trigger hàng ngày"
    else:
        trang_thai = "👀 THEO DÕI"

    if tuan_ok is False and trang_thai[0] in ("✅", "🔥"):
        trang_thai = "👀 THEO DÕI"
        ghi_chu.append(tuan_note)
    elif tuan_ok is None:
        ghi_chu.append(tuan_note)

    # [PHƯƠNG ÁN B] Hai cổng CỨNG ở tầng mã, thay cho việc chỉ số phủ quyết.
    if ma20w_ok is False:
        ghi_chu.append(f"S1 ❌ dưới MA20W của mã ({ma20w_note}) → CHẶN VÀO LỆNH")
        if trang_thai[0] in ("✅", "🔥"):
            trang_thai = "👀 THEO DÕI"
    elif ma20w_ok is None and BAT_COng_MA_MA20W:
        ghi_chu.append(f"S1 ? {ma20w_note}")
    if (not np.isnan(rs_12w)) and rs_12w <= RS_TOI_THIEU_VAO_LENH:
        ghi_chu.append(f"S2 ❌ RS12w {rs_12w:.1f} ≤ {RS_TOI_THIEU_VAO_LENH} "
                       f"→ CHẶN VÀO LỆNH")
        if trang_thai[0] in ("✅", "🔥"):
            trang_thai = "👀 THEO DÕI"

    # [VÁ 17] Hệ số GTGD phải ĐƯỢC ÁP vào tinh_size, không chỉ ghi chú suông.
    hs_gtgd = 1.0
    if GTGD_TOI_THIEU <= x["gtgd20"] < GTGD_CANH_BAO:
        hs_gtgd = 0.5
        ghi_chu.append(f"GTGD {x['gtgd20']:.1f} tỷ < {GTGD_CANH_BAO} "
                       f"→ size ×0.5 (ĐÃ áp vào SốCP)")

    # ---- KN10 ----
    kn = tra_kn(ma) if tra_kn else None
    if kn is None:
        kn_hien = "—"
        ghi_chu.append("THIẾU KN10")
    else:
        _n = kn["so_phien_co"]
        kn_hien = (f"{kn['tong_ty_vnd']:+.0f}tỷ/{kn['so_phien_ban']}b"
                   + ("" if kn["du_10"] else f"@{_n}p"))
        if not kn["du_10"]:
            # [SỬA v7.4 — BUG D] Có dữ liệu một phần: DÙNG được nhưng chỉ để
            # tham khảo, KHÔNG được dùng làm cổng chặn (mẫu quá nhỏ).
            ghi_chu.append(f"KN chỉ {_n}/{KN_SO_PHIEN} phiên — tham khảo, "
                           f"KHÔNG dùng làm cổng; Lớp 3 độ tin cậy THẤP")
        elif kn["so_phien_ban"] >= KN_NGUONG_BAN and trang_thai.startswith("✅"):
            trang_thai = "👀 THEO DÕI"
            ghi_chu.append(f"KN bán ròng {kn['so_phien_ban']}/{KN_SO_PHIEN}")
        elif kn["so_phien_ban"] >= KN_NGUONG_BAN:
            ghi_chu.append(f"KN bán {kn['so_phien_ban']}/{KN_SO_PHIEN}")

    # ---- [VÁ 3] R:R cấu trúc ----
    rr = tinh_rr(df, x["close"], atr=x["atr"], de_risk_level=None,
                 tp_min_pct=TP_CACH_TOI_THIEU_PCT_CP,
                 sl_min_pct=SL_CACH_TOI_THIEU_PCT_CP)

    # ---- [v3] BỘ LỌC CỨNG CẤP MÃ + SETUP + KẾ HOẠCH THOÁT ----
    # F3 (xếp hạng dẫn dắt) cần cả rổ nên được tính SAU vòng lặp, ở TẦNG 2.
    v3_stage = {"STAGE": None, "TEN": "", "GHI_CHU": ""}
    v3_tt    = {"DAT": None, "SO_DAT": None, "GHI_CHU": ""}
    v3_adr, v3_nen, v3_ret = float("nan"), float("nan"), {}
    v3_setup, v3_mota, v3_meta = None, "", None
    v3_f5    = {"DAT": None, "GHI_CHU": "", "TRUOT": []}
    v3_thoat = None
    v3_para  = {"KICH_HOAT": False, "GHI_CHU": ""}
    if BAT_KHUNG_V3:
        try:
            v3_stage = giai_doan_weinstein(df)
            v3_tt    = trend_template(df)
            v3_adr   = adr_pct(df)
            v3_ret   = loi_nhuan_da_khung(df)
            v3_nen   = nen_tang_gan_nhat(df)
            v3_ct    = do_co_that(df)
            v3_setup, v3_mota, v3_meta = nhan_dien_setup(df, x, v3_ct)
            v3_f5    = cong_chat_luong_vao(x["close"], rr["SL"], x["atr"],
                                           la_ep=(v3_setup == "B"))
            v3_thoat = ke_hoach_thoat(x["close"], rr["SL"], df)
            v3_para  = tin_hieu_thoat_parabolic(df, x)
        except BaseException as _e:
            ghi_chu.append(f"⚠️ v3 lỗi tính: {type(_e).__name__} — {_e}")
        if v3_mota:
            ghi_chu.append((f"SETUP {v3_setup}: " if v3_setup else "") + v3_mota)
        if v3_f5.get("DAT") is False:
            ghi_chu.append("F5 ✗ " + v3_f5.get("GHI_CHU", ""))
        if v3_para.get("KICH_HOAT"):
            ghi_chu.append("⚠️ THOÁT PARABOLIC: " + v3_para["GHI_CHU"]
                           + " → nếu ĐANG GIỮ: bán vào sức mạnh, siết trail về "
                           + f"MA{MA_TRAIL_NHANH}")
    # [VÁ 13] In ĐÚNG lý do trượt. Bản cũ luôn in "R:R x < 2.0" kể cả khi
    # nguyên nhân thật là BREAKOUT -> sinh câu vô lý "R:R 2.5 < 2.0" (STB 26/08).
    # [v3] R:R KHÔNG CÒN LÀ CỔNG CHẶN khi RR_LA_CONG_CHAN = False.
    # Cổng R:R đòi biết TRƯỚC đỉnh. Trong pha markup, kháng cự gần nhất luôn
    # nằm ngay trên đầu → R:R luôn < 2 → chặn 100% vốn đúng lúc thị trường
    # tăng (đúng ca VNM/HDB/MBB và 9/10 mã "KẸP" phiên 28/08).
    # v3 chuyển cổng sang KHOẢNG CÁCH STOP (F5). R:R vẫn được tính, in, ghi log
    # — chỉ không còn quyền phủ quyết.
    _rr_chan = (RR_LA_CONG_CHAN if BAT_KHUNG_V3 else True)
    if not rr["DAT_RR"] and trang_thai.startswith("✅"):
        if _rr_chan:
            trang_thai = ("👀 KẸP KHÁNG CỰ" if rr.get("KEP_KHANG_CU")
                          else "👀 THEO DÕI")
        _msg = (("KẸP KHÁNG CỰ — " if rr.get("KEP_KHANG_CU")
                 else "R:R KHÔNG ĐẠT — ") + "; ".join(rr["LY_DO_TRUOT"]))
        if rr.get("KEP_KHANG_CU"):
            # [v7.6] Ngưỡng volume phá theo HẠNG vùng, không còn cứng 120%.
            # Phá một TƯỜNG (cung dày) cần lực lớn hơn phá một MÀNG.
            _msg += (f" → MỐC KÍCH HOẠT: đóng cửa > {rr['MOC_KICH_HOAT']} "
                     f"kèm vol ≥ {rr.get('VOL_PHA_PCT', 120)}% MA20")
            if rr.get("TP1_HANG"):
                _msg += (f" [vùng {rr['TP1_HANG']}, {rr['TP1_DIEM']:.0f}đ — "
                         f"{rr['TP1_CHAN_DOAN']}]")
        elif rr["GIA_TRAN_RR"] and not rr["DA_TRONG_VUNG"]:
            _msg += f" → chờ về ≤ {rr['GIA_TRAN_RR']}"
        ghi_chu.append(("" if _rr_chan else "[v3: ĐO, không chặn] ") + _msg)
    elif rr["DAT_RR"] and rr["DA_TRONG_VUNG"]:
        ghi_chu.append(f"Giá ĐÃ trong vùng R:R (≤ {rr['GIA_TRAN_RR']}) — "
                       f"không phải chờ thêm")

    # ---- [v7.6] ĐỐI CHỨNG độ thổi R:R do bỏ qua vùng yếu ----
    if rr.get("DO_PHONG_RR") and rr["DO_PHONG_RR"] >= 2.0:
        ghi_chu.append(f"⚠️ THỔI R:R ×{rr['DO_PHONG_RR']:.1f} so với v7.5 "
                       f"(TP1 {rr['TP1_V75']} → {rr['TP1']}) — dựa trên trọng "
                       f"số CHƯA BACKTEST, đối chiếu chart trước khi vào")
    if rr.get("TRONG_BOX"):
        ghi_chu.append("GIÁ TRONG BOX — mọi vùng phía trên là ĐỈNH BOX, "
                       "không có kháng cự cấu trúc để neo TP1")

    # ---- [VÁ 7] cờ FTSE ----
    co_ftse = ""
    if ma in FTSE_ALL_WORLD or ma in FTSE_ALL_CAP:
        rot = "All-World" if ma in FTSE_ALL_WORLD else "All-Cap"
        if hom_nay <= NGAY_FTSE_HIEU_LUC:
            co_ftse = f"FTSE {rot}"
            ghi_chu.append(f"⚠️ FTSE {rot} — rủi ro unwind sau "
                           f"{NGAY_FTSE_HIEU_LUC:%d/%m}")
            if trang_thai.startswith("✅"):
                trang_thai = "👀 THEO DÕI"

    # ---- [VÁ 6] ngành: chỉ chạy khi danh mục KHÁC RỖNG ----
    nganh_ma = NGANH.get(ma, "?")
    if ma_dang_giu:
        if ma in ma_dang_giu:
            ghi_chu.append("ĐANG GIỮ")
        elif nganh_ma in nganh_dang_giu:
            ghi_chu.append(f"Chồng lấn ngành: {nganh_ma}")
            if trang_thai.startswith("✅"):
                trang_thai = "👀 THEO DÕI"
        if (nganh_ma in NHOM_TAI_CHINH
                and so_tc_dang_giu >= GIOI_HAN_SLOT_TAI_CHINH
                and ma not in ma_dang_giu):
            ghi_chu.append(f"Hết slot tài chính ({so_tc_dang_giu}"
                           f"/{GIOI_HAN_SLOT_TAI_CHINH})")
            if trang_thai.startswith("✅"):
                trang_thai = "👀 THEO DÕI"

    # ---- [VÁ 10] Dữ liệu cũ -> không được gắn SETUP ----
    if bi_cu:
        ghi_chu.append(f"DỮ LIỆU CŨ: nến cuối {ngay_ma:%d/%m/%Y} "
                       f"< mốc {NGAY_MOC:%d/%m/%Y} — chỉ báo lệch 1 phiên")
        if trang_thai[0] in ("✅", "🔥"):
            trang_thai = "👀 THEO DÕI"

    # ---- Cảnh báo SL không có cấu trúc ----
    hs_slatr = 1.0
    if rr["SL_CAP"]:
        # [VÁ 12 — v7.3] Chỉ kích hoạt khi pivot > NGUONG_KICH_HOAT_SL_CAP×ATR.
        hs_slatr = HE_SO_SIZE_KHI_SL_CAP
        ghi_chu.append(f"SL_CAP: pivot gốc {rr['SL_PIVOT_GOC']} cách "
                       f">{NGUONG_KICH_HOAT_SL_CAP}×ATR → cap về {rr['SL']}; "
                       f"R:R hiển thị {rr['RR']} nhưng theo SL cấu trúc thật chỉ "
                       f"{rr['RR_GOC']} → ngưỡng nâng lên {rr['RR_MIN']:g}, size ×{hs_slatr}")
    if rr["SL_ATR"] and rr["SL_ATR"] > SL_TOI_DA_ATR and trang_thai.startswith("✅"):
        trang_thai = "👀 THEO DÕI"
        ghi_chu.append(f"SL {rr['SL_ATR']}×ATR — không còn cấu trúc đặt stop")
    if rr["BREAKOUT"]:
        ghi_chu.append(f"BREAKOUT: TP1 = measured move {TP_FALLBACK_RR}R → "
                       f"R:R {rr['RR']} là hệ quả CÔNG THỨC, không phải cấu trúc")

    # ---- [VÁ 1] CỔNG ĐÓNG GHI ĐÈ TẤT CẢ ----
    if not CONG_MO and trang_thai[0] in ("✅", "🔥"):
        trang_thai = "👀 THEO DÕI (CỔNG ĐÓNG)"
        ghi_chu.append(f"Cổng {DE_RISK_LEVEL:,.2f} đóng → watchlist-only")
    # [SỬA v7.4 — BUG E] ĐÃ GÃY là điều kiện nhị phân thứ hai của cổng,
    # trước đây chỉ được IN ra chứ không chặn gì.
    if DA_GAY and trang_thai[0] in ("✅", "🔥"):
        trang_thai = "👀 THEO DÕI (ĐÃ GÃY)"
        ghi_chu.append(f"Chỉ số ĐÃ GÃY {INVALIDATION:,.2f} → watchlist-only")
    if CHE_DO_CONG == "B" and NGAN_SACH_NAV <= 0 and trang_thai[0] in ("✅", "🔥"):
        trang_thai = "👀 THEO DÕI (NGÂN SÁCH 0%)"
        ghi_chu.append("Ngân sách giải ngân = 0% NAV")

    # ---- Điểm ----
    diem = 0
    diem += 25 if xu_huong_ok else 0
    diem += 10 if tuan_ok else 0
    diem += 10 if (not np.isnan(x["ma200"]) and x["close"] > x["ma200"]) else 0
    if not np.isnan(rs_12w):
        diem += min(max(rs_12w, 0), 20)
    if not np.isnan(rs_4w):
        diem += min(max(rs_4w, 0), 10)
    diem += 15 if setup_ok else 0
    diem += 5 if tk_ok else 0
    if kn is not None and kn.get("du_10") and kn["so_phien_ban"] <= 3:
        diem += 5
    diem = round(min(diem, 100), 1)

    # [VÁ 21] Size tính ở HAI mốc giá:
    #   SốCP@HT  = nếu vào NGAY hôm nay tại giá hiện tại
    #   SốCP@Vào = nếu vào tại GiáTrầnRR2 như khuyến nghị "chờ về ≤ X"
    # Bản cũ chỉ có mốc thứ nhất, mâu thuẫn với chính ghi chú của nó.
    # [PHƯƠNG ÁN B] Mọi size bị cap bởi NGÂN SÁCH của cổng.
    # [v3] rủi ro/lệnh KHÔNG còn cố định 1% — theo progressive exposure.
    sz = (tinh_size(x["close"], rr["SL"], rui_ro_pct=RUI_RO_V3, he_so=HE_SO_SIZE,
                    he_so_gtgd=hs_gtgd, he_so_slatr=hs_slatr,
                    tran_pct=NGAN_SACH_NAV)
          if rr["SL"] else None)
    sz_vao = (tinh_size(rr["GIA_TRAN_RR"], rr["SL"], rui_ro_pct=RUI_RO_V3,
                        he_so=HE_SO_SIZE,
                        he_so_gtgd=hs_gtgd, he_so_slatr=hs_slatr,
                        tran_pct=NGAN_SACH_NAV)
              if (rr["SL"] and rr["GIA_TRAN_RR"]) else None)

    _dong = {
        "Mã": ma,
        "Ngày": ngay_ma.strftime("%d/%m") if ngay_ma is not None else "?",
        "Ngành": nganh_ma,
        "Giá": round(x["close"], 2),
        "GTGD20": round(x["gtgd20"], 1),
        "ExtATR": round(x["ext_atr"], 2) if not np.isnan(x["ext_atr"]) else None,
        "RSI": round(x["rsi"], 1),
        "RS12w": round(rs_12w, 1) if not np.isnan(rs_12w) else None,
        "1W": "✅" if tuan_ok else ("❌" if tuan_ok is False else "?"),
        "KN10": kn_hien,
        "ATR14": rr["ATR14"],
        "SL": rr["SL"], "SL×ATR": rr["SL_ATR"], "SL_CAP": "⚑" if rr["SL_CAP"] else "",
        "TP1": rr["TP1"], "TP×ATR": rr.get("TP_ATR"),
        "KẸP": "⚑" if rr.get("KEP_KHANG_CU") else "",
        "Kíchhoạt": rr.get("MOC_KICH_HOAT"),
        "R:R": rr["RR"], "R:Rgốc": rr["RR_GOC"],
        "RRcần": rr["RR_MIN"],
        # --- v7.6: bản đồ kháng cự + đối chứng v7.5 ---
        "Hạng": rr.get("TP1_HANG") or "",
        "ĐiểmKC": rr.get("TP1_DIEM"),
        "R:R_v75": rr.get("RR_V75"),
        "Thổi×": rr.get("DO_PHONG_RR"),
        "Vùng": rr.get("N_VUNG"),
        "Tường": rr.get("N_VUNG_TUONG"),
        "Box": "⚑" if rr.get("TRONG_BOX") else "",
        "BO": "⚑" if rr["BREAKOUT"] else "",
        "DatRR": bool(rr["DAT_RR"]),
        # [VÁ 4] VùngVào -> GiáTrầnRR2: giá VÀO TỐI ĐA để đạt R:R >= ngưỡng.
        f"GiáTrầnRR{RR_TOI_THIEU:g}": rr["GIA_TRAN_RR"],
        "SốCP@HT": sz["SO_CP"] if sz else None,
        "SốCP@Vào": sz_vao["SO_CP"] if sz_vao else None,
        "Hệsố": sz["HE_SO"] if sz else None,
        "%NAV": sz["TY_TRONG_PCT"] if sz else None,
        "TrầnNS%": round(NGAN_SACH_NAV, 2),
        "S1_MA20W": ("✅" if ma20w_ok else ("❌" if ma20w_ok is False else "?")),
        "FTSE": co_ftse,
        # --- v3: BỘ LỌC CỨNG (F3 hoàn tất ở TẦNG 2 sau vòng lặp) ---
        "Stage": v3_stage.get("STAGE"),
        "TT": (f"{v3_tt.get('SO_DAT')}/8" if v3_tt.get("SO_DAT") is not None else None),
        "TT_DAT": v3_tt.get("DAT"),
        "ADR%": _so(v3_adr),
        "R1M%": _so(v3_ret.get(RS_KHUNG[0])),
        "R3M%": _so(v3_ret.get(RS_KHUNG[1])),
        "R6M%": _so(v3_ret.get(RS_KHUNG[2])),
        "Nền%": _so(v3_nen, 1),
        "Setup": (v3_setup or ""),
        "SetupKichHoat": (v3_meta.get("KICH_HOAT")
                          if isinstance(v3_meta, dict) else None),
        "F5": ("✅" if v3_f5.get("DAT") is True
               else ("❌" if v3_f5.get("DAT") is False else "?")),
        "F5_DAT": v3_f5.get("DAT"),
        "F5_LY_DO": ("; ".join(v3_f5.get("TRUOT") or []) or None),
        "TP_T1": (v3_thoat["TP_TANG1"] if v3_thoat else None),
        "TrailMA": (v3_thoat.get("MA_TRAIL_GIA") if v3_thoat else None),
        "Para": ("⚑" if v3_para.get("KICH_HOAT") else ""),
        "KN_DU10": (kn.get("du_10") if kn else None),
        "KN_BAN": (kn.get("so_phien_ban") if kn else None),
        "RủiRo%": RUI_RO_V3,
        "Điểm": diem,
        "Trạng thái": trang_thai,
        "Ghi chú": "; ".join(ghi_chu),
    }
    TIEN_TRINH[ma] = _dong          # [BUG I] chốt checkpoint từng mã
    ket_qua.append(_dong)

if not ket_qua:
    raise SystemExit("⛔ Không quét được mã nào — xem lỗi phía trên (thường là "
                     "rate limit). Chờ 1-2 phút rồi chạy lại Ô 7.")
bang = pd.DataFrame(ket_qua)

# ====================================================================== #
# 7.5 [v3] TẦNG 2 — BỘ LỌC CỨNG PASS/FAIL                                #
# ---------------------------------------------------------------------- #
# Chạy SAU vòng quét vì F3 (xếp hạng dẫn dắt) cần TOÀN BỘ rổ mới tính được.
#
# NGUYÊN TẮC: trượt BẤT KỲ bộ lọc nào -> ĐỨNG NGOÀI. Không có điểm số nào
# cứu được. Đây chính là thứ v2 thiếu: điểm trung bình có trọng số cho phép
# một lớp mạnh che một lớp đã gãy (FRT 80đ với R:R 0,07 và không có chỗ đặt
# stop). Không trader chuyên nghiệp nào giao dịch bằng điểm trung bình.
# ====================================================================== #
if BAT_KHUNG_V3 and len(bang):
    _vni_ret = loi_nhuan_da_khung(vni_df)
    _map_ret = {21: "R1M%", 63: "R3M%", 126: "R6M%"}

    # --- F3a: phân vị hiệu suất trong rổ đã quét ---
    _rank_cols = []
    for _k, _cot in _map_ret.items():
        if _cot in bang.columns:
            _rc = "H" + _cot.replace("%", "")
            bang[_rc] = xep_hang_pct(bang[_cot])
            _rank_cols.append(_rc)
    bang["HạngMin"] = (bang[_rank_cols].min(axis=1, skipna=False).round(1)
                       if _rank_cols else np.nan)
    _nguong_hang = 100.0 - RS_TOP_PCT

    # --- Lớp 4: sức mạnh NGÀNH (trung bình R3M% của các mã cùng ngành) ---
    _rs_nganh = {}
    if "R3M%" in bang.columns:
        for _n, _v in bang.groupby("Ngành")["R3M%"].mean().items():
            _rs_nganh[_n] = (None if pd.isna(_v)
                             else bool(_v > _vni_ret.get(63, 0.0)))

    _v3, _v3ok, _dv3, _mau3, _tomtat = [], [], [], [], {}
    for _i, _r in bang.iterrows():
        _truot, _thieu, _cho = [], [], []

        # ---- F1 · Giai đoạn Weinstein (chỉ Stage 2 được mua) ----
        _st = _r.get("Stage")
        if _st is None or pd.isna(_st):
            _thieu.append("F1 Stage")
        elif int(_st) not in STAGE_CHO_PHEP:
            _truot.append(f"F1 Stage {int(_st)}")

        # ---- F2 · Trend Template (Minervini) ----
        _tt = _r.get("TT_DAT")
        if _tt is None or (isinstance(_tt, float) and pd.isna(_tt)):
            _thieu.append("F2 TrendTemplate")
        elif not bool(_tt):
            _truot.append(f"F2 TT {_r.get('TT')}")

        # ---- F3 · Xếp hạng dẫn dắt đa khung + nền tảng ----
        _hm = _r.get("HạngMin")
        if _hm is None or pd.isna(_hm):
            _thieu.append("F3 hiệu suất")
        else:
            if _hm < _nguong_hang:
                _truot.append(f"F3 hạng {_hm:.0f} < {_nguong_hang:.0f} "
                              f"(ngoài top {RS_TOP_PCT:g}%)")
            if RS_DUONG_BAT_BUOC:
                _yeu = [_c for _k, _c in _map_ret.items()
                        if _c in bang.columns and not pd.isna(_r.get(_c))
                        and _r[_c] <= _vni_ret.get(_k, 0.0)]
                if _yeu:
                    _truot.append("F3 yếu hơn VNINDEX ở " + ",".join(_yeu))
        _nen = _r.get("Nền%")
        if _nen is None or pd.isna(_nen):
            _thieu.append("F3 nền tảng")
        elif not (NEN_TANG_MIN_PCT <= _nen <= NEN_TANG_MAX_PCT):
            _truot.append(f"F3 nền {_nen:.0f}% ngoài "
                          f"[{NEN_TANG_MIN_PCT:g};{NEN_TANG_MAX_PCT:g}]%")

        # ---- F4 · Thanh khoản & biên độ ----
        _g = _r.get("GTGD20")
        if _g is None or pd.isna(_g):
            _thieu.append("F4 GTGD")
        elif _g < GTGD_TOI_THIEU:
            _truot.append(f"F4 GTGD {_g:.0f} < {GTGD_TOI_THIEU:g} tỷ")
        _adr = _r.get("ADR%")
        if _adr is None or pd.isna(_adr):
            _thieu.append("F4 ADR")
        elif _adr < ADR_TOI_THIEU_PCT:
            _truot.append(f"F4 ADR {_adr:.2f}% < {ADR_TOI_THIEU_PCT:g}%")

        # ---- F5 · CỔNG CHẤT LƯỢNG ĐIỂM VÀO (thay cổng R:R) ----
        _f5 = _r.get("F5_DAT")
        if _f5 is None or (isinstance(_f5, float) and pd.isna(_f5)):
            _thieu.append("F5 điểm vào")
        elif not bool(_f5):
            _truot.append("F5 " + str(_r.get("F5_LY_DO") or "stop ngoài cửa sổ"))

        # ---- F6 · Cơ bản (nhập tay) — THIẾU thì hạ 1 bậc, KHÔNG chặn ----
        _cb = CO_BAN_TAY.get(_r["Mã"])
        if not _cb:
            _thieu.append("F6 cơ bản")
        else:
            _eps = _cb.get("eps_yoy")
            if _eps is None and not _cb.get("catalyst"):
                _thieu.append("F6 cơ bản")
            elif (_eps is not None and _eps < EPS_YOY_TOI_THIEU
                  and not _cb.get("catalyst")):
                _truot.append(f"F6 EPS {_eps:.0f}% < {EPS_YOY_TOI_THIEU:g}% "
                              f"và không có catalyst")

        # ---- SETUP: không có setup thì KHÔNG CÓ LỆNH ----
        _sp = _r.get("Setup")
        _sp = None if (_sp is None or (isinstance(_sp, float) and pd.isna(_sp))
                       or _sp in ("", "—")) else str(_sp)
        if _sp is None:
            _truot.append("KHÔNG khớp setup A/B/C")
        elif _sp in ("A-CHỜ",):
            _cho.append("nền co thắt CHƯA phá")
        elif _sp == "A?":
            _truot.append("phá nền nhưng VOL KHÔNG XÁC NHẬN")
        elif _sp == "C" and _r.get("SetupKichHoat") is False:
            _cho.append("pullback CHƯA có nến kích hoạt")

        # ---- Kết luận ----
        # THIẾU DỮ LIỆU KHÔNG PHẢI LÀ ĐẠT. Mọi bộ lọc trừ F6 đều xử lý
        # "không biết" như "không đạt" — đây là điểm khác biệt với bản cũ,
        # nơi thiếu dữ liệu bị ngầm chấm 0 điểm rồi vẫn lọt qua nhờ lớp khác.
        _thieu_chan = [t for t in _thieu if not t.startswith("F6")]
        if _truot:
            _nhan = "⛔ " + "; ".join(_truot[:3]) + ("…" if len(_truot) > 3 else "")
            _ok = 0
        elif _thieu_chan:
            _nhan = "❔ THIẾU: " + ", ".join(_thieu_chan[:3])
            _ok = 0
        elif _cho:
            _nhan = "⏳ CHỜ KÍCH HOẠT — " + "; ".join(_cho)
            _ok = 1
        else:
            _nhan = "🟢 ĐỦ ĐK VÀO"
            _ok = 2
        if _ok and _thieu:
            _nhan += "  (⚠️ thiếu " + ",".join(t for t in _thieu) + " → hạ 1 bậc)"

        # ---- Cổng THỊ TRƯỜNG ghi đè kết luận cấp mã ----
        # Stage 3/4 của chỉ số: cấm tuyệt đối (Weinstein).
        # MA10 < MA20: không cấm giữ, nhưng cấm MỞ breakout mới (Kullamägi).
        if CHAN_INDEX and _ok > 0:
            _nhan, _ok = f"⛔ {CHAN_INDEX}", 0
        elif CHAN_NHANH and _ok == 2:
            _nhan, _ok = f"⏳ {CHAN_NHANH} — không mở mới | {_nhan}", 1
        for _t in _truot:
            _key = _t.split()[0]
            if _key in ("KHÔNG", "phá"):
                _key = "SETUP"
            _tomtat[_key] = _tomtat.get(_key, 0) + 1

        _v3.append(_nhan)
        _v3ok.append(_ok)
        _kn_d = ({"du_10": bool(_r.get("KN_DU10")),
                  "so_phien_ban": int(_r.get("KN_BAN") or 0)}
                 if _r.get("KN_DU10") is not None
                 and not (isinstance(_r.get("KN_DU10"), float)
                          and pd.isna(_r.get("KN_DU10"))) else None)
        _d, _m = diem_v3(_sp, _r.get("HạngMin"), _kn_d,
                         _rs_nganh.get(_r.get("Ngành")), _r.get("ExtATR"))
        _dv3.append(_d)
        _mau3.append(_m)

    bang["V3"] = _v3
    bang["_v3ok"] = _v3ok
    bang["ĐiểmV3"] = _dv3
    bang["Mẫu%"] = _mau3

    # Trượt v3 -> KHÔNG được giữ nhãn ✅/🔥. Hai cột không bao giờ mâu thuẫn.
    for _i, _r in bang.iterrows():
        if _r["_v3ok"] == 0 and str(_r["Trạng thái"])[0] in ("✅", "🔥"):
            bang.at[_i, "Trạng thái"] = "👀 THEO DÕI (trượt v3)"

    bang = bang.sort_values(["_v3ok", "ĐiểmV3", "Điểm"],
                            ascending=[False, False, False]).reset_index(drop=True)

    print("\n" + "=" * 66)
    print("TẦNG 2 — BỘ LỌC CỨNG v3 (F1→F6 + SETUP)")
    print("=" * 66)
    print(f"  🟢 ĐỦ ĐIỀU KIỆN VÀO : {int((bang['_v3ok'] == 2).sum())} mã")
    print(f"  ⏳ CHỜ KÍCH HOẠT    : {int((bang['_v3ok'] == 1).sum())} mã")
    print(f"  ⛔/❔ TRƯỢT hoặc THIẾU: {int((bang['_v3ok'] == 0).sum())} mã")
    if _tomtat:
        print("  Bộ lọc chặn nhiều nhất: "
              + ", ".join(f"{k}×{v}" for k, v in
                          sorted(_tomtat.items(), key=lambda z: -z[1])[:6]))
    if int((bang["_v3ok"] >= 1).sum()) == 0:
        print("  ➜ KHÔNG mã nào qua bộ lọc → ĐỨNG NGOÀI. Đây là ĐẦU RA HỢP LỆ")
        print("    và HOÀN CHỈNH của khung, không phải lỗi quét.")
else:
    bang = bang.sort_values("Điểm", ascending=False).reset_index(drop=True)
_thieu = [m for m in DANH_SACH if m not in TIEN_TRINH]
print(f"\n✅ Quét xong {len(bang)}/{len(DANH_SACH)} mã."
      + (f" Lỗi: {', '.join(loi)}" if loi else ""))
if _thieu:
    print(f"⚠️ CÒN THIẾU {len(_thieu)} mã: {', '.join(_thieu)}")
    print("   → CHẠY LẠI Ô 7: các mã đã có sẽ được khôi phục, chỉ tải phần thiếu.")
    print("   → Bảng dưới đây CHƯA ĐẦY ĐỦ, không dùng để ra quyết định.")
if ma_cu:
    print(f"\n🚨 {len(ma_cu)} mã có DỮ LIỆU CŨ hơn mốc {NGAY_MOC:%d/%m/%Y}: "
          f"{', '.join(ma_cu)}")
    print("   Nguyên nhân thường gặp: nguồn cập nhật EOD cổ phiếu trễ hơn chỉ số.")
    print("   → Chạy lại sau 30-60 phút. Mọi chỉ báo của các mã này lệch 1 phiên.")


# ======================================================================
# XUẤT JSON  — thay cho Ô 8 / Ô 9 / Ô 10 (in bảng)
# ======================================================================
from export_v3 import xuat_json

# Phiên bản thư viện đi thẳng vào JSON. Trong giai đoạn chạy song song, khi
# bản tay và bản tự động lệch nhau thì đây là chỗ nhìn đầu tiên: vnstock 4.x
# đổi sang "Unified UI", một con số khác nhau đủ để giải thích cả bảng khác nhau.
def _phien_ban():
    import importlib.metadata as _md
    ra = {}
    for _g in ("vnstock", "pandas", "numpy"):
        try:
            ra[_g] = _md.version(_g)
        except Exception:
            ra[_g] = None
    return ra

_duong_dan = xuat_json(
    bang=bang,
    vni_df=vni_df,
    vni=vni,
    kq_cong=KQ_CONG,
    rr_idx=RR_IDX,
    ns=NS,
    ohlcv=OHLCV_CACHE,
    boi_canh={
        "nguon": NGUON,
        "ngay_moc": NGAY_MOC,
        "cong_mo": CONG_MO,
        "da_gay": DA_GAY,
        "ly_do_gay": _ly_do_gay,
        "invalidation": INVALIDATION,
        "de_risk_level": DE_RISK_LEVEL,
        "bac_giai_ngan": mo_ta_bac,
        "ngan_sach_nav_pct": NGAN_SACH_NAV,
        "che_do_cong": CHE_DO_CONG,
        "bat_khung_v3": BAT_KHUNG_V3,
        "rr_la_cong_chan": RR_LA_CONG_CHAN,
        "stage_index": STAGE_IDX,
        "cong_nhanh": CONG_NHANH,
        "rui_ro_pct": RUI_RO_V3,
        "ly_do_rui_ro": LY_DO_RUI_RO,
        "chan_index": CHAN_INDEX,
        "chan_nhanh": CHAN_NHANH,
        "kn_so_phien": kn_so_phien,
        "kn_note": kn_note,
        "ma_loi": loi,
        "ma_du_lieu_cu": ma_cu,
        "ma_thieu": [m for m in DANH_SACH if m not in TIEN_TRINH],
        "phien_ban_thu_vien": _phien_ban(),
        "nghi_le": NGHI_LE,
        "gio_chay_ict": (datetime.utcnow() + timedelta(hours=7)).strftime(
            "%Y-%m-%d %H:%M"),
    },
    gop_tuan=gop_tuan,
    kn_so_phien_can=KN_SO_PHIEN,
    chi_bao_tuan_vni=_ct_tuan_idx,
    danh_muc=DANH_MUC_HIEN_TAI,
)
print(f"\n💾 JSON: {_duong_dan}")
