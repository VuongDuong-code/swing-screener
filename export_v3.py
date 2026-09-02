# -*- coding: utf-8 -*-
"""
export_v3.py — schema JSON cho KHUNG v3.

Thay cho Ô 8 / Ô 9 / Ô 10 của bản Colab (in bảng để copy tay).

NGUYÊN TẮC CỦA SCHEMA NÀY:
  1. Mỗi bộ lọc xuất GIÁ TRỊ ĐO ĐƯỢC, không chỉ pass/fail. "F2 trượt" là vô
     dụng khi đọc lại sau 3 tháng; "F2 6/8, trượt: MA50>MA150>MA200; MA200 dốc
     lên" thì kiểm chứng được.
  2. Kèm OHLCV thô. Mọi con số trong báo cáo phải truy được về nến gốc —
     đây chính là mục #1 và #2 của checklist Phần 0.
  3. THIẾU dữ liệu ghi là null kèm lý do, KHÔNG bao giờ điền 0. Chấm 0 cho cái
     mình không biết là một sai lầm khác hẳn với chấm 0 cho cái mình biết là kém.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

SCHEMA = "v3.1"
SO_NEN_NGAY = 30          # Phần 0 mục #1: 30 phiên 1D
SO_NEN_TUAN = 30          # Phần 0 mục #1: 30 tuần 1W
# [v8.1] Trần số mã kèm OHLCV — khớp TRAN_MA_BAO_CAO của Ô 10. Con số cứng
# tách rời khỏi kết quả lọc là sai cả hai chiều: phiên chặt thì kéo về đủ số
# bằng những mã ĐÃ BỊ LOẠI, phiên rộng thì cắt mất mã hợp lệ. Nên ở đây lấy
# TẤT CẢ mã còn sống, chỉ chặn bằng một trần và GHI RÕ phần bị cắt.
TRAN_MA_KEM_OHLCV = 25


# ---------------------------------------------------------------- #
# tiện ích                                                          #
# ---------------------------------------------------------------- #
def _s(v, k=2):
    """Số an toàn cho JSON: NaN/inf/pandas-NA -> None, không bao giờ -> 0."""
    if v is None:
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if not math.isfinite(f):
        return None
    return round(f, k)


def _b(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return bool(v)


def _t(v):
    """Chuỗi an toàn: rỗng -> None để phân biệt với '' có nghĩa."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return s or None


def _nen(df, n, moc_dong=None):
    """OHLCV thô, cũ -> mới. Kèm %VolMA20 vì mọi ngưỡng volume của khung đều
    tính theo MA20, không theo con số tuyệt đối.

    moc_dong: nến có `time` > mốc này được gắn chua_dong=True. Dùng cho khung
    TUẦN — nến tuần đang chạy vẫn phải xuất (Ô 10 hiển thị nó), nhưng phải
    gắn nhãn, nếu không mọi kết luận 'đóng cửa TUẦN' đều đọc nhầm nến dở."""
    if df is None or not len(df):
        return []
    d = df.copy()
    d["_mav20"] = d["volume"].rolling(20).mean()
    ra = []
    for _, r in d.tail(n).iterrows():
        vm = r["_mav20"]
        ra.append({
            "ngay": pd.to_datetime(r["time"]).strftime("%Y-%m-%d"),
            "o": _s(r["open"]), "h": _s(r["high"]),
            "l": _s(r["low"]), "c": _s(r["close"]),
            "v": int(r["volume"]) if pd.notna(r["volume"]) else None,
            "vol_pct_ma20": _s(r["volume"] / vm * 100, 0)
            if (pd.notna(vm) and vm > 0) else None,
        })
        if moc_dong is not None and pd.to_datetime(r["time"]) > moc_dong:
            ra[-1]["chua_dong"] = True
    return ra


# ---------------------------------------------------------------- #
# độ tin cậy dữ liệu (Phần 0) — giữ nguyên thang điểm của Ô 8.1     #
# ---------------------------------------------------------------- #
def _do_tin_cay(bang, vni_df, vni, rr_idx, kn_so_phien, kn_so_phien_can,
                tuan_ok):
    diem, chi_tiet = 0.0, []

    if len(vni_df) >= 200:
        diem += 3
        chi_tiet.append("OHLCV chỉ số đầy đủ (+3)")
    else:
        chi_tiet.append(f"⚠️ OHLCV chỉ số {len(vni_df)} < 200 phiên (+0)")

    if vni and not pd.isna(vni.get("rsi")) and not pd.isna(vni.get("ma200")):
        diem += 2
        chi_tiet.append("Chỉ báo tính được (+2)")
    else:
        chi_tiet.append("⚠️ Chỉ báo chỉ số thiếu (+0)")

    # [BUG J] Điểm KN phải tỷ lệ theo min(độ phủ mã, độ SÂU phiên). Bản trước
    # chỉ kiểm độ phủ -> báo 10/10 trong khi KN mới 1/10 phiên và Lớp 3 đang mù.
    n_thieu = int((bang["KN10"] == "—").sum()) if "KN10" in bang.columns else len(bang)
    phu = 1 - n_thieu / max(len(bang), 1)
    sau = min((kn_so_phien or 0) / kn_so_phien_can, 1.0) if kn_so_phien_can else 0.0
    them = round(3 * phu * sau, 1)
    diem += them
    chi_tiet.append(
        f"KN10 phủ {phu * 100:.0f}% mã, sâu {kn_so_phien or 0}/{kn_so_phien_can} "
        f"phiên (+{them})"
        + ("" if sau >= 1 else " — Lớp 3 KHÔNG dùng để ra quyết định"))

    chi_tiet.append("⚠️ Tự doanh: THIẾU HOÀN TOÀN (+0) — chưa có nguồn tự động")

    if tuan_ok:
        diem += 1
        chi_tiet.append("Dữ liệu tuần OK (+1)")

    if rr_idx and rr_idx.get("RR") is not None:
        diem += 1
        chi_tiet.append("R:R cấu trúc tính được (+1)")
    else:
        chi_tiet.append("⚠️ Không dò được pivot cho R:R (+0)")

    d = round(min(diem, 10), 1)
    return {
        "diem": d,
        "tren": 10,
        "chi_tiet": chi_tiet,
        "du_de_khuyen_nghi": d >= 5,
        "ghi_chu": None if d >= 5 else
        "< 5/10 → CHỈ nhận định cấu trúc, TỪ CHỐI khuyến nghị mua/bán cụ thể.",
    }


# ---------------------------------------------------------------- #
# một mã                                                            #
# ---------------------------------------------------------------- #
def _mot_ma(r, df, kem_ohlcv):
    gia, sl = _s(r.get("Giá")), _s(r.get("SL"))
    R = (gia - sl) if (gia is not None and sl) else None

    d = {
        "ma": r.get("Mã"),
        "nganh": _t(r.get("Ngành")),
        "ngay_nen_cuoi": _t(r.get("Ngày")),
        "gia": gia,

        # --- kết luận: bộ lọc cứng quyết định, điểm chỉ xếp hạng ---
        "ket_luan": {
            "v3": _t(r.get("V3")),
            "muc": int(r["_v3ok"]) if r.get("_v3ok") is not None else None,
            "muc_nghia": {0: "TRƯỢT/THIẾU — đứng ngoài",
                          1: "CHỜ KÍCH HOẠT",
                          2: "ĐỦ ĐIỀU KIỆN VÀO"}.get(
                              int(r["_v3ok"]) if r.get("_v3ok") is not None else -1),
            "trang_thai_v2": _t(r.get("Trạng thái")),
            "ghi_chu": _t(r.get("Ghi chú")),
        },

        # --- BỘ LỌC CỨNG: giá trị đo được, không chỉ pass/fail ---
        "bo_loc": {
            "F1_weinstein": {
                "stage": _s(r.get("Stage"), 0),
                "dat": (None if r.get("Stage") is None or pd.isna(r.get("Stage"))
                        else int(r["Stage"]) == 2),
                "yeu_cau": "Stage 2",
            },
            "F2_trend_template": {
                "so_dat": _t(r.get("TT")),
                "dat": _b(r.get("TT_DAT")),
                "yeu_cau": "8/8",
            },
            "F3_dan_dat": {
                "ret_1m_pct": _s(r.get("R1M%")),
                "ret_3m_pct": _s(r.get("R3M%")),
                "ret_6m_pct": _s(r.get("R6M%")),
                "hang_1m": _s(r.get("HR1M"), 1),
                "hang_3m": _s(r.get("HR3M"), 1),
                "hang_6m": _s(r.get("HR6M"), 1),
                "hang_min": _s(r.get("HạngMin"), 1),
                "nen_tang_pct": _s(r.get("Nền%"), 1),
                "rs_12w_vs_vni": _s(r.get("RS12w")),
            },
            "F4_thanh_khoan": {
                "gtgd20_ty": _s(r.get("GTGD20"), 1),
                "adr20_pct": _s(r.get("ADR%")),
            },
            "F5_diem_vao": {
                "dat": _b(r.get("F5_DAT")),
                "sl_atr": _s(r.get("SL×ATR")),
                "atr14": _s(r.get("ATR14")),
                "sl_pct": _s(R / gia * 100 if (R and gia) else None),
                "ly_do_truot": _t(r.get("F5_LY_DO")),
            },
            "F6_co_ban": {
                "nguon": "nhập tay qua secret CO_BAN_TAY",
                # F6 thiếu thì HẠ 1 BẬC, không chặn — xem cột ket_luan.ghi_chu
            },
        },

        # --- setup: không có setup = không có lệnh ---
        "setup": {
            "ma": _t(r.get("Setup")),
            "da_kich_hoat": _b(r.get("SetupKichHoat")),
        },

        # --- kế hoạch: đủ để thực thi, không cần quyết định thêm ---
        "ke_hoach": {
            "vung_vao": gia,
            "stoploss": sl,
            "R_vnd": _s(R),
            "moc_kich_hoat": _s(r.get("Kíchhoạt")),
            "so_cp": (int(r["SốCP@HT"]) if r.get("SốCP@HT") is not None
                      and not pd.isna(r.get("SốCP@HT")) else None),
            "ty_trong_pct_nav": _s(r.get("%NAV"), 1),
            "tp_tang1": _s(r.get("TP_T1")),
            "ma_trail_gia": _s(r.get("TrailMA")),
            "invalidation": sl,
        },

        # --- đo và ghi log, KHÔNG chặn lệnh (v3: F5 mới là cổng) ---
        "tham_khao": {
            "rr": _s(r.get("R:R")),
            "rr_goc": _s(r.get("R:Rgốc")),
            "rr_can": _s(r.get("RRcần")),
            "rr_la_cong_chan": False,
            "tp1": _s(r.get("TP1")),
            "tp_atr": _s(r.get("TP×ATR")),
            "kep_khang_cu": (r.get("KẸP") == "⚑"),
            "tp1_hang": _t(r.get("Hạng")),
            "tp1_diem_cung": _s(r.get("ĐiểmKC"), 1),
            "thoi_rr_lan": _s(r.get("Thổi×")),
            "trong_box": (r.get("Box") == "⚑"),
            "breakout": (r.get("BO") == "⚑"),
            "rsi": _s(r.get("RSI"), 1),
            "ext_atr": _s(r.get("ExtATR")),
            "kn10": _t(r.get("KN10")),
            "kn_du_10_phien": _b(r.get("KN_DU10")),
            "kn_so_phien_ban": _s(r.get("KN_BAN"), 0),
            "tin_hieu_thoat_parabolic": (r.get("Para") == "⚑"),
            "diem_v3": _s(r.get("ĐiểmV3"), 1),
            "mau_trong_so_pct": _s(r.get("Mẫu%"), 0),
        },
    }

    return d


# ---------------------------------------------------------------- #
# hàm chính                                                         #
# ---------------------------------------------------------------- #
def xuat_json(bang, vni_df, vni, kq_cong, rr_idx, ns, ohlcv, boi_canh,
              thu_muc="out", ten="latest.json", gop_tuan=None,
              kn_so_phien_can=10, chi_bao_tuan_vni=None, danh_muc=None):
    os.makedirs(thu_muc, exist_ok=True)
    gio_vn = datetime.now(timezone.utc) + timedelta(hours=7)

    if gop_tuan is None:
        import __main__
        gop_tuan = getattr(__main__, "gop_tuan", None)

    def _tuan(df):
        if gop_tuan is None or df is None:
            return []
        try:
            moc = pd.to_datetime(df["time"]).max()
            return _nen(gop_tuan(df), SO_NEN_TUAN, moc_dong=moc)
        except Exception:
            return []

    # ---- mã nào được kèm OHLCV — khớp quy tắc chọn mã của Ô 10 [v8.1] ----
    # Mã ĐANG GIỮ luôn có mặt, kể cả khi đã bị loại: đang cầm thì vẫn phải
    # biết nó đứng ở đâu.
    dang_giu = [m for m in bang["Mã"] if m in (danh_muc or {})]
    song = bang[~bang["Trạng thái"].astype(str).str.startswith(("❌", "⚠️"))].copy()
    _khoa = [c for c in ("_v3ok", "ĐiểmV3", "Điểm") if c in song.columns]
    if _khoa:
        song = song.sort_values(_khoa, ascending=[False] * len(_khoa))
    ds_song = [m for m in song["Mã"].tolist() if m not in dang_giu]
    con_lai = max(TRAN_MA_KEM_OHLCV - len(dang_giu), 0)
    kem = set(dang_giu + ds_song[:con_lai])
    bi_cat = ds_song[con_lai:]

    ma_list = []
    for _, r in bang.iterrows():
        d = _mot_ma(r, ohlcv.get(r["Mã"]), r["Mã"] in kem)
        d["dang_giu"] = r["Mã"] in (danh_muc or {})
        if r["Mã"] in kem:
            d["ohlcv_1d"] = _nen(ohlcv.get(r["Mã"]), SO_NEN_NGAY)
            d["ohlcv_1w"] = _tuan(ohlcv.get(r["Mã"]))
        ma_list.append(d)

    n2 = int((bang["_v3ok"] == 2).sum()) if "_v3ok" in bang.columns else 0
    n1 = int((bang["_v3ok"] == 1).sum()) if "_v3ok" in bang.columns else 0

    # ---- độ tươi dữ liệu ----
    # Phiên chạy thật 02/09 nhưng nguồn trả nến cuối 28/08 -> mọi chỉ báo lệch
    # vài phiên mà bảng vẫn trông hoàn toàn hợp lệ. Đây là loại sai nguy hiểm
    # nhất: không có dòng lỗi nào, chỉ có số cũ. Phải đo và ghi rõ.
    _phien = (pd.to_datetime(boi_canh.get("ngay_moc"))
              if boi_canh.get("ngay_moc") is not None else None)
    _tre = None
    if _phien is not None:
        _le = set(pd.to_datetime(boi_canh.get("nghi_le") or []).normalize())
        _ngay = pd.bdate_range(_phien.normalize(), gio_vn.date())
        _tre = int(sum(1 for d in _ngay[1:] if d.normalize() not in _le))
    do_tuoi = {
        "phien_du_lieu": _phien.strftime("%Y-%m-%d") if _phien is not None else None,
        "ngay_chay_ict": gio_vn.strftime("%Y-%m-%d %H:%M"),
        "tre_bao_nhieu_phien_giao_dich": _tre,
        "nghi_le_da_tru": boi_canh.get("nghi_le") or [],
        "tuoi": (None if _tre is None else _tre <= 1),
        "ghi_chu": (None if (_tre is None or _tre <= 1) else
                    f"Nguồn trả nến cuối {_phien:%d/%m} trong khi hôm nay "
                    f"{gio_vn:%d/%m} — trễ {_tre} phiên giao dịch (đã trừ "
                    f"nghỉ lễ). MỌI chỉ báo dưới đây lệch {_tre} phiên."),
    }

    out = {
        "schema": SCHEMA,
        "sinh_luc": gio_vn.strftime("%Y-%m-%d %H:%M:%S+07:00"),
        "phien": (pd.to_datetime(boi_canh.get("ngay_moc")).strftime("%Y-%m-%d")
                  if boi_canh.get("ngay_moc") is not None else None),
        "nguon": boi_canh.get("nguon"),
        "do_tuoi_du_lieu": do_tuoi,

        "do_tin_cay_du_lieu": _do_tin_cay(
            bang, vni_df, vni, rr_idx,
            boi_canh.get("kn_so_phien"), kn_so_phien_can,
            tuan_ok=bool(chi_bao_tuan_vni)),

        "thi_truong": {
            "vnindex": _s(kq_cong.get("GIA")),
            "ma20w": _s(kq_cong.get("MA20W")),
            "ma200d": _s(kq_cong.get("MA200D")),
            "neo": kq_cong.get("NEO"),
            "de_risk_level": _s(boi_canh.get("de_risk_level")),
            "cong_mo": _b(boi_canh.get("cong_mo")),
            "cong_day": _b(kq_cong.get("CONG_DAY")),
            "day_cong_atr": _s(kq_cong.get("DAY_CONG_ATR"), 3),
            "invalidation": _s(boi_canh.get("invalidation")),
            "da_gay": _b(boi_canh.get("da_gay")),
            "ly_do_gay": boi_canh.get("ly_do_gay") or [],
            "canh_bao": kq_cong.get("canh_bao") or [],

            # cổng 2 tầng — thứ quyết định CÓ ĐƯỢC MỞ VỊ THẾ hay không
            "cong_2_tang": {
                "cham_weinstein": {
                    "stage": (boi_canh.get("stage_index") or {}).get("STAGE"),
                    "ten": (boi_canh.get("stage_index") or {}).get("TEN"),
                    "ghi_chu": (boi_canh.get("stage_index") or {}).get("GHI_CHU"),
                    "ma30w": _s((boi_canh.get("stage_index") or {}).get("MA30W")),
                    "doc_pct": _s((boi_canh.get("stage_index") or {}).get("DOC_PCT")),
                },
                "nhanh_ma10_ma20": {
                    "ok": _b((boi_canh.get("cong_nhanh") or {}).get("OK")),
                    "ma10": _s((boi_canh.get("cong_nhanh") or {}).get("MA10")),
                    "ma20": _s((boi_canh.get("cong_nhanh") or {}).get("MA20")),
                    "he_so": _s((boi_canh.get("cong_nhanh") or {}).get("F")),
                },
                "chan_cap_thi_truong": boi_canh.get("chan_index"),
                "han_che_cap_thi_truong": boi_canh.get("chan_nhanh"),
            },

            "ngan_sach": {
                "nav_pct": _s(boi_canh.get("ngan_sach_nav_pct")),
                "che_do_cong": boi_canh.get("che_do_cong"),
                "bac_giai_ngan": boi_canh.get("bac_giai_ngan"),
                "ly_do": (ns or {}).get("LY_DO"),
                "chi_tiet": (ns or {}).get("CHI_TIET") or [],
                "moc_nang": [
                    {"gia": _s(g), "d_atr": _s(n, 2), "tran_pct": t}
                    for g, n, t in ((ns or {}).get("MOC_NANG") or [])
                ],
                "rui_ro_moi_lenh_pct": _s(boi_canh.get("rui_ro_pct")),
                "ly_do_rui_ro": boi_canh.get("ly_do_rui_ro"),
            },

            "rr_chi_so_tham_khao": {
                "sl": _s((rr_idx or {}).get("SL")),
                "tp1": _s((rr_idx or {}).get("TP1")),
                "rr": _s((rr_idx or {}).get("RR")),
                "ghi_chu": "Chế độ B: R:R chỉ số KHÔNG chặn lệnh cổ phiếu.",
            },

            "ohlcv_1d": _nen(vni_df, SO_NEN_NGAY),
            "ohlcv_1w": _tuan(vni_df),
            "chi_bao_1d": {
                "rsi14": _s(vni.get("rsi")),
                "macd_line": _s(vni.get("macd_line"), 3),
                "macd_signal": _s(vni.get("macd_signal"), 3),
                "macd_hist": _s(vni.get("macd_hist"), 3),
                "ma20": _s(vni.get("ma20")), "ma50": _s(vni.get("ma50")),
                "ma200": _s(vni.get("ma200")),
                "atr14": _s(vni.get("atr")),
                "ext_atr": _s(vni.get("ext_atr")),
                "vol_ma20": _s(vni.get("mav20"), 0),
                "nguong_vol_120": _s(vni.get("nguong_vol_120"), 0),
                "vol_nen_cuoi_pct_ma20": _s(vni.get("vol_cuoi_pct"), 0),
            },
        },

        "tom_tat": {
            "so_ma_quet": len(bang),
            "du_dieu_kien_vao": n2,
            "cho_kich_hoat": n1,
            "truot_hoac_thieu": len(bang) - n2 - n1,
            "dung_ngoai": (n2 + n1) == 0,
            "ghi_chu": ("Không mã nào qua bộ lọc → ĐỨNG NGOÀI. Đây là ĐẦU RA "
                        "HỢP LỆ VÀ HOÀN CHỈNH của khung, không phải lỗi quét."
                        if (n2 + n1) == 0 else None),
        },

        "canh_bao_du_lieu": {
            "ma_loi": boi_canh.get("ma_loi") or [],
            "ma_du_lieu_cu": boi_canh.get("ma_du_lieu_cu") or [],
            "ma_chua_quet": boi_canh.get("ma_thieu") or [],
            "khoi_ngoai": boi_canh.get("kn_note"),
            "khoi_ngoai_so_phien": boi_canh.get("kn_so_phien"),
            "tu_doanh": "THIẾU HOÀN TOÀN — chưa có nguồn tự động",
            "ma_bi_cat_khoi_ohlcv": bi_cat,
            "ghi_chu_cat": (
                f"{len(bi_cat)} mã còn sống bị cắt khỏi phần OHLCV do trần "
                f"{TRAN_MA_KEM_OHLCV}. Chúng vẫn có đủ bộ lọc và kế hoạch, "
                f"chỉ thiếu nến thô để kiểm chứng." if bi_cat else None),
        },

        "cau_hinh": {
            "bat_khung_v3": _b(boi_canh.get("bat_khung_v3")),
            "rr_la_cong_chan": _b(boi_canh.get("rr_la_cong_chan")),
            "phien_ban_thu_vien": boi_canh.get("phien_ban_thu_vien") or {},
        },

        "ma": ma_list,
    }

    p = os.path.join(thu_muc, ten)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # bản lưu trữ theo phiên: latest.json bị ghi đè, muốn đối chiếu về sau
    # thì phải có bản đóng băng.
    if out["phien"]:
        luu = os.path.join(thu_muc, "lich_su", f"{out['phien']}.json")
        os.makedirs(os.path.dirname(luu), exist_ok=True)
        with open(luu, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    return p
