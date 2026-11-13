from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta


class User(AbstractUser):
    email = models.EmailField("email address", unique=True)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)

    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)

    is_subscriber = models.BooleanField(default=False)
    subscription_end_date = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["phone_number"]),
            models.Index(fields=["is_subscriber", "is_active"]),
        ]

    def has_active_subscription(self):
        """判斷是否具備有效的付費訂閱資格"""
        if not self.is_subscriber:
            return False
        if self.subscription_end_date and self.subscription_end_date < timezone.now():
            return False
        return True


class VerificationCode(models.Model):
    """
    極簡的 OTP 驗證碼表，支援 Email 與 Phone 驗證。
    """

    class VerificationType(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        PHONE = "PHONE", "Phone"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="verification_codes"
    )
    target_type = models.CharField(max_length=5, choices=VerificationType.choices)
    code = models.CharField(max_length=6)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "verification_codes"
        indexes = [
            models.Index(fields=["user", "target_type", "code"]),
        ]

    def save(self, *args, **kwargs):
        # 預設驗證碼 10 分鐘後過期
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    def is_valid(self):
        return timezone.now() <= self.expires_at


# ==========================================
# 發票設定與轉帳紀錄
# ==========================================
class InvoiceType(models.IntegerChoices):
    B2C = 2, "二聯式 (個人)"
    B2B = 3, "三聯式 (公司)"


class UserInvoiceProfile(models.Model):
    """儲存使用者「記住我」的預設發票資訊"""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="invoice_profile"
    )
    invoice_type = models.IntegerField(
        choices=InvoiceType.choices, default=InvoiceType.B2C
    )

    # 二聯式常用
    buyer_name = models.CharField(max_length=100, blank=True)
    mobile_barcode = models.CharField(max_length=20, blank=True, default=None)

    # 三聯式必填
    company_name = models.CharField(max_length=100, blank=True)
    tax_id = models.CharField(max_length=8, blank=True)

    class Meta:
        db_table = "user_invoice_profiles"


class SubscriptionPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待審核"
        COMPLETED = "COMPLETED", "已核准"
        REJECTED = "REJECTED", "已拒絕"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="subscription_payments"
    )

    account_last_5 = models.CharField(max_length=5)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    invoice_type = models.IntegerField(
        choices=InvoiceType.choices, default=InvoiceType.B2C
    )
    invoice_buyer_name = models.CharField(max_length=100, blank=True)
    invoice_mobile_barcode = models.CharField(max_length=20, blank=True)
    invoice_company_name = models.CharField(max_length=100, blank=True)
    invoice_tax_id = models.CharField(max_length=8, blank=True)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    invoice_number = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_payments"
        ordering = ["-created_at"]
