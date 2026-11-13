import re
from django.db import transaction
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from users.models import UserInvoiceProfile, InvoiceType, SubscriptionPayment

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    外部使用者的註冊 Serializer
    """

    password = serializers.CharField(
        write_only=True, min_length=8, style={"input_type": "password"}
    )
    phone_number = serializers.CharField(required=True)
    username = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = ["email", "username", "phone_number", "password"]

    def validate_email(self, value):
        """業務與資安防護：限定網域，並明確阻擋重複註冊"""
        domain = value.split("@")[-1].lower()
        if domain not in ["gmail.com", "hotmail.com"]:
            raise serializers.ValidationError(
                "目前僅開放 @gmail.com 與 @hotmail.com 信箱註冊。"
            )

        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("此信箱已被註冊。")

        return value

    def validate_phone_number(self, value):
        """資料一致性與資安防護：嚴格檢查格式，並明確阻擋重複註冊"""
        if not re.match(r"^09\d{8}$", value):
            raise serializers.ValidationError(
                "手機門號格式錯誤，請輸入 09 開頭的 10 碼數字。"
            )

        # 明確的 DB 查詢阻擋
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("此手機門號已被註冊。")

        return value

    def create(self, validated_data):
        validated_data["password"] = make_password(validated_data.get("password"))
        validated_data["is_email_verified"] = False
        validated_data["is_phone_verified"] = False
        validated_data["is_subscriber"] = False

        return super().create(validated_data)


class OTPVerificationSerializer(serializers.Serializer):
    """
    用於接收與驗證 OTP 碼的 Serializer (配合前端 UI，一次驗證兩組)
    """

    email = serializers.EmailField(required=True)
    phone_number = serializers.CharField(required=True)

    email_code = serializers.CharField(max_length=6, min_length=6, required=True)
    phone_code = serializers.CharField(max_length=6, min_length=6, required=True)


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    remember_invoice = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = SubscriptionPayment
        fields = [
            "id",
            "account_last_5",
            "amount",
            "invoice_type",
            "invoice_buyer_name",
            "invoice_mobile_barcode",
            "invoice_company_name",
            "invoice_tax_id",
            "remember_invoice",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]

    def validate_account_last_5(self, value):
        if not re.match(r"^\d{5}$", value):
            raise serializers.ValidationError("請輸入正確的帳號後五碼 (5位數字)。")
        return value

    def validate_invoice_mobile_barcode(self, value):
        if value and not re.match(r"^\/[0-9A-Z.+\-]{7}$", value):
            raise serializers.ValidationError(
                "手機條碼載具格式錯誤 (應為 / 開頭加上 7 碼英數字)。"
            )
        return value

    def validate(self, data):
        invoice_type = data.get("invoice_type", InvoiceType.B2C)

        # 三聯式發票驗證
        if invoice_type == InvoiceType.B2B:
            if not data.get("invoice_company_name"):
                raise serializers.ValidationError(
                    {"invoice_company_name": "三聯式發票必須填寫公司抬頭。"}
                )

            tax_id = data.get("invoice_tax_id", "")
            if not re.match(r"^\d{8}$", tax_id):
                raise serializers.ValidationError(
                    {"invoice_tax_id": "三聯式發票必須填寫 8 碼統一編號。"}
                )

        return data

    @transaction.atomic
    def create(self, validated_data):
        remember_invoice = validated_data.pop("remember_invoice", False)

        payment = super().create(validated_data)

        if remember_invoice:
            user = payment.user
            UserInvoiceProfile.objects.update_or_create(
                user=user,
                defaults={
                    "invoice_type": payment.invoice_type,
                    "buyer_name": payment.invoice_buyer_name,
                    "mobile_barcode": payment.invoice_mobile_barcode,
                    "company_name": payment.invoice_company_name,
                    "tax_id": payment.invoice_tax_id,
                },
            )

        return payment


class UserInvoiceProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInvoiceProfile
        fields = [
            "invoice_type",
            "buyer_name",
            "mobile_barcode",
            "company_name",
            "tax_id",
        ]
