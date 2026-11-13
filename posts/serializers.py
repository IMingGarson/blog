from rest_framework import serializers
from posts.models import Post
import bleach


class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = [
            "id",
            "title",
            "content",
            "visibility",
            "is_published",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    # def validate_content(self, value):
    #     allowed_tags = list(bleach.ALLOWED_TAGS) + [
    #         "p",
    #         "h1",
    #         "h2",
    #         "h3",
    #         "br",
    #         "strong",
    #         "em",
    #         "u",
    #         "img",
    #         "div",
    #         "span",
    #         "iframe",
    #     ]

    #     allowed_attrs = {
    #         "*": ["class"],
    #         "img": ["src", "alt", "width", "height"],
    #         "iframe": ["src", "width", "height", "frameborder", "allowfullscreen"],
    #     }
    #     return bleach.clean(
    #         value, tags=allowed_tags, attributes=allowed_attrs, strip=True
    #     )
