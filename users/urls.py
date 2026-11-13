from django.urls import path
from users.views import ExternalSignupView, ExternalLoginView, UserProfileView
from users.api.views import (
    RegisterAPIView,
    RequestOTPAPIView,
    VerifyOTPAPIView,
    ExternalLoginAPIView,
    ExternalLogoutAPIView,
    InvoiceProfileAPIView,
    SubscriptionPaymentAPIView,
)

app_name = "users"

urlpatterns = [
    path("signup", ExternalSignupView.as_view(), name="signup"),
    path("login", ExternalLoginView.as_view(), name="login"),
    path("profile", UserProfileView.as_view(), name="profile"),
    path("api/users/register", RegisterAPIView.as_view(), name="api_register"),
    path("api/users/request-otp", RequestOTPAPIView.as_view(), name="api_request_otp"),
    path("api/users/verify-otp", VerifyOTPAPIView.as_view(), name="api_verify_otp"),
    path("api/users/login", ExternalLoginAPIView.as_view(), name="api_login"),
    path("api/users/logout", ExternalLogoutAPIView.as_view(), name="api_logout"),
    path(
        "api/users/invoice-profile",
        InvoiceProfileAPIView.as_view(),
        name="api_invoice_profile",
    ),
    path(
        "api/users/payments",
        SubscriptionPaymentAPIView.as_view(),
        name="api_subscription_payment",
    ),
]
