from django.db import models
from django.conf import settings


class SubscriptionPlan(models.Model):
    class Period(models.IntegerChoices):
        MONTHLY = 30, "Monthly"
        YEARLY = 365, "Yearly"

    name = models.CharField(max_length=50)
    price = models.PositiveIntegerField()
    period_days = models.IntegerField(choices=Period.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "subscription_plans"


class PaymentRecord(models.Model):
    class Status(models.IntegerChoices):
        PENDING = 0, "Pending"
        SUCCESS = 1, "Success"
        FAILED = 2, "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, related_name="payments"
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.DO_NOTHING)

    merchant_trade_no = models.CharField(max_length=50, unique=True)

    amount = models.PositiveIntegerField()
    status = models.IntegerField(choices=Status.choices, default=Status.PENDING)

    trade_message = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payment_records"
        indexes = [
            models.Index(fields=["merchant_trade_no", "status"]),
            models.Index(fields=["user", "created_at"]),
        ]
