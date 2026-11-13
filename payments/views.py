import logging
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from payments.utils import get_ecpay_subscription_params, verify_ecpay_mac
from django.shortcuts import redirect

User = get_user_model()
logger = logging.getLogger(__name__)


class ECPayCheckoutView(APIView):
    """建立綠界訂單並回傳自動導向的 HTML 表單"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ecpay_params = get_ecpay_subscription_params(
            request.user.id, request.user.email
        )
        ecpay_url = "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5"

        form_inputs = "".join(
            [
                f"<input type='hidden' name='{k}' value='{v}'>"
                for k, v in ecpay_params.items()
            ]
        )

        html = f"""
        <!DOCTYPE html>
        <html lang="zh-TW">
        <head>
            <meta charset="UTF-8">
            <title>導向安全付款中心...</title>
            <style>
                body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f9fafb; }}
                .loader {{ text-align: center; color: #4b5563; }}
            </style>
        </head>
        <body>
            <div class="loader">
                <h2>安全連線中...</h2>
                <p>請勿關閉視窗，即將為您導向綠界付款頁面。</p>
            </div>
            <form id="ecpay-form" action="{ecpay_url}" method="POST">
                {form_inputs}
            </form>
            <script>document.getElementById("ecpay-form").submit();</script>
        </body>
        </html>
        """
        return HttpResponse(html)


@method_decorator(csrf_exempt, name="dispatch")
class ECPayWebhookView(APIView):
    """接收綠界付款結果 Webhook"""

    permission_classes = []

    @transaction.atomic
    def post(self, request):
        data = request.POST.dict()
        logger.info(f"收到綠界 Webhook 通知: {data}")

        if not data:
            return HttpResponse("0|Empty data", status=400, content_type="text/plain")

        # 1. 壓碼驗證 (使用 Timing-Safe 防護)
        if not verify_ecpay_mac(data):
            logger.warning("綠界 Webhook 壓碼驗證失敗！可能有惡意偽造請求。")
            return HttpResponse("0|Invalid MAC", status=400, content_type="text/plain")

        # 2. 防跨商戶攻擊驗證
        if data.get("MerchantID") != settings.ECPAY["MERCHANT_ID"]:
            logger.error("商戶代號不符！")
            return HttpResponse(
                "0|Invalid Merchant", status=400, content_type="text/plain"
            )

        # 3. 處理訂閱授權邏輯
        rtn_code = data.get("RtnCode")
        simulate_paid = data.get("SimulatePaid", "0")
        user_id = data.get("CustomField1")

        # 如果是綠界後台手動發起的模擬付款，且在正式環境，則不處理邏輯
        if simulate_paid == "1" and getattr(settings, "DJANGO_ENV", "dev") != "dev":
            logger.info("正式環境收到模擬付款，略過權限更新。")
            return HttpResponse("1|OK", content_type="text/plain")

        # RtnCode == '1' 代表交易/授權成功
        if rtn_code == "1" and user_id:
            # 加上 select_for_update 行級鎖，防止綠界瞬間發送兩次請求導致資料競寫 (Race Condition)
            user = User.objects.select_for_update().filter(id=user_id).first()
            if user:
                if not user.is_subscriber:
                    user.is_subscriber = True
                    user.save(update_fields=["is_subscriber"])
                    logger.info(f"使用者 {user_id} 訂閱/扣款成功！權限已開通。")
            else:
                logger.error(f"找不到使用者 ID: {user_id}")
                # 即使找不到使用者，仍須回傳 1|OK 避免綠界不斷重發

        # 4. 嚴格規範回傳格式[cite: 1]
        return HttpResponse("1|OK", content_type="text/plain")


class MockSubscriptionSuccessView(APIView):
    """
    [開發測試專用] 模擬綠界付款成功，直接升級帳號並導回個人頁面
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        # 模擬 Webhook 接收到成功通知後的資料庫更新行為
        if not user.is_subscriber:
            user.is_subscriber = True
            # 若你的 User model 是使用 has_active_subscription() 來判斷，請確保它會回傳這個欄位
            user.save(update_fields=["is_subscriber"])

        # 升級完成後，直接重新導向回個人帳號頁面
        return redirect("/profile")
