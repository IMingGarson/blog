import logging
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_sns_otp_sms(phone_number: str, code: str) -> bool:
    """
    使用 AWS SNS 發送手機 OTP 驗證碼。
    :param phone_number: 台灣門號，格式預期為 '09xxxxxxxx'
    :param code: 6 位數驗證碼
    :return: bool 表示是否成功呼叫 AWS API
    """
    if phone_number.startswith("09") and len(phone_number) == 10:
        e164_number = f"+886{phone_number[1:]}"
    else:
        e164_number = phone_number

    message = f"【你的專案名稱】您的驗證碼為：{code}，請在 10 分鐘內輸入。請勿將此驗證碼告訴任何人。"

    try:
        sns_client = boto3.client(
            "sns",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, "AWS_S3_REGION_NAME", "ap-east-2"),
        )

        response = sns_client.publish(
            PhoneNumber=e164_number,
            Message=message,
            MessageAttributes={
                "AWS.SNS.SMS.SMSType": {
                    "DataType": "String",
                    "StringValue": "Transactional",
                }
            },
        )

        logger.info(
            f"SNS SMS sent to {e164_number} successfully. MessageId: {response.get('MessageId')}"
        )
        return True

    except (BotoCoreError, ClientError) as e:
        logger.error(f"Failed to send SNS SMS to {e164_number}. AWS Error: {str(e)}")
        return False


def send_otp_email(email_address: str, code: str) -> bool:
    """使用 Django 內建 SMTP 發送 Email OTP 驗證碼"""
    subject = "【Timmy Blog】註冊驗證碼"
    message = (
        f"歡迎加入 Timmy Blog！\n\n"
        f"您的 Email 驗證碼為：{code}\n\n"
        f"請在 10 分鐘內回到網站輸入此驗證碼。若您並未請求此驗證碼，請忽略這封信。"
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email="no-reply@timmycapital.com.tw",
            recipient_list=[email_address],
            fail_silently=False,
        )
        logger.info(f"OTP Email sent to {email_address} successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP Email to {email_address}. Error: {str(e)}")
        return False
