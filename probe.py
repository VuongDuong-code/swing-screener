# -*- coding: utf-8 -*-
"""
probe.py — chạy TRONG COLAB (môi trường đang chạy được) để lấy 2 thông tin
còn treo, trước khi bật workflow tự động.

1. Phiên bản vnstock đang thực sự hoạt động  -> ghim vào requirements.txt
2. Trading.foreign_trade() có sẵn không       -> nếu có thì thay được khối
   dò tên cột mong manh ở Ô 6 bằng một API ổn định.
"""
import importlib.metadata as md
import inspect

for goi in ("vnstock", "pandas", "numpy"):
    try:
        print(f"{goi:10s} {md.version(goi)}")
    except Exception as e:
        print(f"{goi:10s} KHÔNG XÁC ĐỊNH ({type(e).__name__})")

print("\n--- Trading ---")
try:
    from vnstock import Trading
    t = Trading(source="VCI")
    ham = [m for m in dir(t) if not m.startswith("_")]
    print("Phương thức:", ", ".join(ham))
    if hasattr(t, "foreign_trade"):
        print("\n✅ CÓ foreign_trade")
        print("Chữ ký:", inspect.signature(t.foreign_trade))
        df = t.foreign_trade(["HPG", "SSI"])
        print("Cột:", list(df.columns))
        print(df.head())
    else:
        print("\n❌ KHÔNG có foreign_trade → giữ nguyên khối dò cột ở Ô 6.")
except Exception as e:
    print(f"Lỗi: {type(e).__name__}: {e}")

print("\n--- Quote (đường dẫn import 3.x vs 4.x) ---")
for duong_dan in ("vnstock.api.quote", "vnstock.explorer.vci", "vnstock"):
    try:
        m = __import__(duong_dan, fromlist=["Quote"])
        print(f"✅ {duong_dan}: Quote={'có' if hasattr(m, 'Quote') else 'KHÔNG'}")
    except Exception as e:
        print(f"❌ {duong_dan}: {type(e).__name__}")
