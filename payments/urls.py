# payments/urls.py
from django.urls import path
from payments.views import (
    ECPayCheckoutView,
    ECPayWebhookView,
    MockSubscriptionSuccessView,
)

app_name = "payments"

urlpatterns = [
    # 供前端呼叫，導向綠界付款頁面
    path("checkout", ECPayCheckoutView.as_view(), name="checkout"),
    # 供綠界背景呼叫的 Webhook (ReturnURL / PeriodReturnURL)
    path("webhook/ecpay", ECPayWebhookView.as_view(), name="webhook_ecpay"),
    path("mock-success", MockSubscriptionSuccessView.as_view(), name="mock_success"),
]
