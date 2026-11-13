import urllib.parse
import hashlib
import hmac
from django.conf import settings
from datetime import datetime


def generate_ecpay_mac(params: dict) -> str:
    """
    產生綠界 ECPay CheckMacValue (符合 .NET URL Encode 特殊字元規範)
    """
    # 建立副本，避免修改到原始字典
    mac_params = params.copy()

    # 嚴格確保壓碼前剔除 CheckMacValue 本身
    mac_params.pop("CheckMacValue", None)

    # 1. 依照 Key 的字母順序(A~Z)排序
    sorted_keys = sorted(mac_params.keys())

    # 2. 串接字串 (首尾加上 HashKey 與 HashIV)
    raw_str = (
        f"HashKey={settings.ECPAY['HASH_KEY']}&"
        + "&".join([f"{k}={mac_params[k]}" for k in sorted_keys])
        + f"&HashIV={settings.ECPAY['HASH_IV']}"
    )

    # 3. URL Encode (使用 quote_plus 將空格轉為 +)
    encoded_str = urllib.parse.quote_plus(raw_str)

    # 4. 綠界 .NET URL Encode 特殊字元嚴格替換邏輯
    encoded_str = (
        encoded_str.lower()
        .replace("%2d", "-")
        .replace("%5f", "_")
        .replace("%2e", ".")
        .replace("%21", "!")
        .replace("%2a", "*")
        .replace("%28", "(")
        .replace("%29", ")")
        .replace("%20", "+")
    )

    # 5. SHA256 加密並轉大寫
    return hashlib.sha256(encoded_str.encode("utf-8")).hexdigest().upper()


def verify_ecpay_mac(data: dict) -> bool:
    """
    【資安升級】驗證綠界回傳資料的壓碼，防禦 Timing Attack 攻擊
    """
    received_mac = data.get("CheckMacValue", "")
    if not received_mac:
        return False

    expected_mac = generate_ecpay_mac(data)

    # 絕對不能使用 `==`，必須使用 timing-safe 比對
    return hmac.compare_digest(expected_mac, received_mac)


def get_ecpay_subscription_params(user_id: int, user_email: str) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    merchant_trade_no = f"SUB{user_id}T{timestamp}"
    trade_date = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    params = {
        "MerchantID": settings.ECPAY["MERCHANT_ID"],
        "MerchantTradeNo": merchant_trade_no,
        "MerchantTradeDate": trade_date,
        "PaymentType": "aio",
        "TotalAmount": 199,
        "TradeDesc": "Timmy Blog Premium Subscription",
        "ItemName": "Timmy Blog 深度內容訂閱 (每月)",
        "ReturnURL": settings.ECPAY["RETURN_URL"],
        "ChoosePayment": "Credit",
        "EncryptType": 1,
        # 定期定額專屬參數
        "PeriodAmount": 199,
        "PeriodType": "M",
        "Frequency": 1,
        "ExecTimes": 99,
        "PeriodReturnURL": settings.ECPAY["RETURN_URL"],
        "CustomField1": str(user_id),
        "CustomField2": user_email,
        "ClientBackURL": settings.ECPAY["CLIENT_BACK_URL"],
        # ==========================================
        # 綠界 B2C 電子發票自動開立參數
        # ==========================================
        "InvoiceMark": "Y",  # 啟用自動開立發票
        "RelateNumber": merchant_trade_no,  # 發票自訂編號 (通常與訂單編號相同)
        "CustomerEmail": user_email,  # 收件人 Email
        "TaxType": "1",  # 課稅類別 (1: 應稅)
        "SalesAmount": 199,  # 發票總金額
        "InvoiceItemName": "深度內容訂閱",  # 發票品名 (不可有特殊字元)
        "InvoiceItemCount": "1",  # 數量
        "InvoiceItemWord": "月",  # 單位
        "InvoiceItemPrice": "199",  # 單價
        "DelayDay": "0",  # 延遲開立天數 (0 為付款後立即開立)
        "InvType": "07",  # 字軌類別 (07: 一般稅額)
    }

    params["CheckMacValue"] = generate_ecpay_mac(params)
    return params
