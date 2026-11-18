from django.db import models
from django.conf import settings
from django.utils import timezone


class Post(models.Model):
    class Visibility(models.IntegerChoices):
        PUBLIC = 0, "Public"
        REGISTERED = 1, "Registered Only"
        SUBSCRIBER = 2, "Subscriber Only"

    title = models.CharField(max_length=255)
    content = models.JSONField(default=dict, blank=True)
    seo_data = models.JSONField(default=dict, blank=True)
    visibility = models.IntegerField(
        choices=Visibility.choices, default=Visibility.PUBLIC
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, related_name="posts"
    )
    is_published = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "posts"
        indexes = [
            models.Index(
                fields=["deleted_at", "is_published", "visibility", "-created_at"]
            ),
        ]

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])


class Media(models.Model):
    class MediaType(models.IntegerChoices):
        IMAGE = 0, "Image"
        VIDEO = 1, "Video"

    post = models.ForeignKey(
        Post,
        on_delete=models.DO_NOTHING,
        related_name="media_files",
        null=True,
        blank=True,
    )
    media_type = models.IntegerField(choices=MediaType.choices)
    s3_url = models.URLField(max_length=1024)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "post_media"
        indexes = [
            models.Index(fields=["post", "media_type"]),
        ]
