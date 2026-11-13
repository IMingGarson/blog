from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.utils.crypto import get_random_string
from django.utils import timezone

from users.models import User, VerificationCode, SubscriptionPayment
from .serializers import (
    UserRegistrationSerializer,
    OTPVerificationSerializer,
    UserInvoiceProfileSerializer,
    SubscriptionPaymentSerializer,
)
from users.services import send_sns_otp_sms, send_otp_email
from django.shortcuts import redirect
from rest_framework.permissions import IsAuthenticated


# ==========================================
# Rate Limit
# ==========================================
class RegisterThrottle(AnonRateThrottle):
    """註冊頻率限制：防護惡意註冊攻擊"""

    # 給一個符合原生語法的預設值，避免 DRF 啟動時檢查噴錯
    rate = "1/m"

    def parse_rate(self, rate):
        # 直接回傳： (允許次數, 週期秒數)
        # 10 分鐘 = 600 秒
        return (1, 600)


class OTPRequestThrottle(AnonRateThrottle):
    """OTP 請求頻率限制：防護簡訊/發信成本與洗錢風險"""

    rate = "1/m"

    def parse_rate(self, rate):
        # 10 分鐘內只能 2 次
        return (2, 600)


# ==========================================
# 業務邏輯 API Views
# ==========================================
class RegisterAPIView(APIView):
    permission_classes = []
    throttle_classes = [RegisterThrottle]

    @transaction.atomic
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            _ = serializer.save()
            return Response(
                {"message": "註冊成功，請前往驗證信箱與手機門號。"},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestOTPAPIView(APIView):
    """請求發送 OTP (同時發送 Email 與 Phone 驗證碼)"""

    permission_classes = []
    throttle_classes = [OTPRequestThrottle]

    @transaction.atomic
    def post(self, request):
        email = request.data.get("email")
        phone_number = request.data.get("phone_number")

        if not email or not phone_number:
            return Response(
                {"error": "必須同時提供信箱與手機門號"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email=email, phone_number=phone_number).first()
        if not user:
            return Response(
                {"error": "找不到符合此信箱與手機的帳號資料"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_email_verified and user.is_phone_verified:
            return Response(
                {"error": "此帳號已經完成雙重驗證，無需再次發送。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 產生兩組 6 位數驗證碼
        email_code = get_random_string(length=6, allowed_chars="0123456789")
        phone_code = get_random_string(length=6, allowed_chars="0123456789")

        # 寫入資料庫
        if not user.is_email_verified:
            VerificationCode.objects.create(
                user=user, target_type="EMAIL", code=email_code
            )
        if not user.is_phone_verified:
            VerificationCode.objects.create(
                user=user, target_type="PHONE", code=phone_code
            )

        # ==========================================
        # 呼叫 Service 寄發真實的信件與簡訊
        # ==========================================
        email_sent = False
        sms_sent = False

        if not user.is_email_verified:
            email_sent = send_otp_email(email_address=email, code=email_code)

        if not user.is_phone_verified:
            sms_sent = send_sns_otp_sms(phone_number=phone_number, code=phone_code)

        # 防呆檢查：如果第三方服務異常，告知使用者
        if not email_sent or not sms_sent:
            return Response(
                {"error": "驗證碼發送部分失敗，請稍後再試或聯繫客服。"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"message": "驗證碼已成功發送至您的信箱與手機"}, status=status.HTTP_200_OK
        )


class VerifyOTPAPIView(APIView):
    """合併驗證 OTP (一次驗證兩組)"""

    permission_classes = []

    @transaction.atomic
    def post(self, request):
        serializer = OTPVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = User.objects.filter(
            email=data["email"], phone_number=data["phone_number"]
        ).first()

        if not user:
            return Response(
                {"error": "驗證失敗，帳號資料不符"}, status=status.HTTP_404_NOT_FOUND
            )

        now = timezone.now()
        email_record = (
            VerificationCode.objects.filter(
                user=user,
                target_type="EMAIL",
                code=data["email_code"],
                expires_at__gte=now,
            )
            .order_by("-created_at")
            .first()
        )

        phone_record = (
            VerificationCode.objects.filter(
                user=user,
                target_type="PHONE",
                code=data["phone_code"],
                expires_at__gte=now,
            )
            .order_by("-created_at")
            .first()
        )

        if not email_record or not phone_record:
            return Response(
                {"error": "驗證碼錯誤或已過期，請重新請求"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 雙重驗證皆通過，更新狀態
        user.is_email_verified = True
        user.is_phone_verified = True
        user.save(update_fields=["is_email_verified", "is_phone_verified"])

        # 資安：提早作廢這兩筆驗證碼 (防重放攻擊)
        email_record.expires_at = now
        phone_record.expires_at = now
        VerificationCode.objects.bulk_update(
            [email_record, phone_record], ["expires_at"]
        )

        return Response(
            {"message": "雙重驗證成功！您現在可以登入了。"}, status=status.HTTP_200_OK
        )


class ExternalLoginAPIView(APIView):
    """C端使用者登入"""

    permission_classes = []

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None:
            # 拒絕未通過驗證的登入
            if not (user.is_email_verified and user.is_phone_verified):
                return Response(
                    {"error": "請先完成雙重驗證才能登入。"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            login(request, user)
            return Response(
                {
                    "message": "登入成功",
                    "username": user.username,
                    "is_subscriber": user.has_active_subscription(),
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"error": "信箱或密碼錯誤"}, status=status.HTTP_401_UNAUTHORIZED
        )


class ExternalLogoutAPIView(APIView):
    """C端使用者登出"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return redirect("/")


class InvoiceProfileAPIView(APIView):
    """取得使用者預設發票設定 (供前端結帳頁自動帶入)"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "invoice_profile", None)
        if profile:
            serializer = UserInvoiceProfileSerializer(profile)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response({}, status=status.HTTP_200_OK)


class SubscriptionPaymentAPIView(APIView):
    """提交手動轉帳與發票資料"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        has_pending = SubscriptionPayment.objects.filter(
            user=request.user, status=SubscriptionPayment.Status.PENDING
        ).exists()

        if has_pending:
            return Response(
                {"error": "您目前已經有一筆待審核的訂閱紀錄，請耐心等候管理員確認。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SubscriptionPaymentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(
                {"message": "訂閱申請已提交，請等候管理員審核。"},
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
