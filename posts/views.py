from django.db import transaction
from rest_framework import viewsets, permissions
from posts.models import Post
from users.models import User, SubscriptionPayment
from .serializers import PostSerializer
from rest_framework import status
from django.db.models import Prefetch
from django.views.generic import TemplateView, ListView, DetailView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils.decorators import method_decorator
from django.utils.html import strip_tags
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from django.views.decorators.cache import never_cache

from django.core.cache import cache
from django.http import Http404
from types import SimpleNamespace

POST_CACHE_TTL = 60 * 60 * 72


class AdminRequiredMixin(UserPassesTestMixin):
    """保護 HTML 頁面，未登入或非 Admin 一律導回登入頁"""

    login_url = "/internal/login"

    def test_func(self):
        return (
            self.request.user.is_authenticated
            and self.request.user.is_staff
            and self.request.user.is_active
        )


class InternalAPICRUDPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_staff and request.user.is_active):
            return False
        if request.method not in permissions.SAFE_METHODS:
            return request.user.is_superuser
        return True


class EditorJSContentMixin:
    def extract_text_from_editorjs(self, content_json):
        if not isinstance(content_json, dict) or "blocks" not in content_json:
            return ""

        text_parts = []
        for block in content_json["blocks"]:
            data = block.get("data", {})
            if block["type"] in ["paragraph", "header", "quote"]:
                text_parts.append(strip_tags(data.get("text", "")))
            elif block["type"] == "list":
                for item in data.get("items", []):
                    if isinstance(item, dict):
                        text_parts.append(strip_tags(item.get("content", "")))

        return " ".join(text_parts)

    def _build_post_namespace(self, data):
        pk_val = data.get("pk") if data.get("pk") is not None else data.get("id")
        seo = data.get("seo_data") or {}
        author = data.get("author") or {}
        return SimpleNamespace(
            id=pk_val,
            pk=pk_val,
            title=data.get("title", ""),
            content=data.get("content", ""),
            visibility=int(data.get("visibility", 0)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            seo_data=SimpleNamespace(
                meta_title=seo.get("meta_title", ""),
                meta_description=seo.get("meta_description", ""),
                keywords=seo.get("keywords", ""),
                canonical_url=seo.get("canonical_url", ""),
            ),
            author=SimpleNamespace(
                id=author.get("id"),
                username=author.get("username", ""),
                email=author.get("email", ""),
            ),
        )

    def _extract_seo_dict(self, post):
        raw_seo = getattr(post, "seo_data", None) or {}
        if not isinstance(raw_seo, dict):
            raw_seo = {}
        return {
            "meta_title": raw_seo.get("meta_title", ""),
            "meta_description": raw_seo.get("meta_description", ""),
            "keywords": raw_seo.get("keywords", ""),
            "canonical_url": raw_seo.get("canonical_url", ""),
        }


class InternalDraftPreviewView(AdminRequiredMixin, TemplateView):
    """B端後台：純草稿預覽頁 (依賴前端 sessionStorage 傳遞資料)"""

    template_name = "internal/post_preview.html"


class InternalPostPreviewView(AdminRequiredMixin, DetailView):
    """B端後台：文章預覽頁 (無條件顯示完整內容，供所見即所得與 S3 圖片確認)"""

    model = Post
    template_name = "internal/post_preview.html"
    context_object_name = "post"

    def get_queryset(self):
        return Post.objects.all().select_related("author")


class InternalPostEditView(AdminRequiredMixin, DetailView):
    """B端後台：文章編輯頁 (僅限 Superuser 修改)"""

    model = Post
    template_name = "internal/post_edit.html"
    context_object_name = "post"

    def get_queryset(self):
        return Post.objects.filter(deleted_at__isnull=True)


class InternalDashboardView(AdminRequiredMixin, ListView):
    model = Post
    template_name = "internal/dashboard.html"
    context_object_name = "posts"
    paginate_by = 20

    def get_queryset(self):
        return Post.objects.all().select_related("author").order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not user.is_superuser and not getattr(user, "is_subscriber", False):
            for post in context["posts"]:
                if int(post.visibility) == 2:
                    post.content = "【系統提示：您無權限檢視此訂閱者專屬內容】"

        return context


class InternalUserListView(AdminRequiredMixin, ListView):
    """B端後台：會員管理列表"""

    model = User
    template_name = "internal/user_list.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        latest_payments = Prefetch(
            "subscription_payments",
            queryset=SubscriptionPayment.objects.order_by("-created_at"),
            to_attr="latest_payments",
        )

        return (
            User.objects.filter(is_superuser=False)
            .prefetch_related(latest_payments)
            .order_by("-date_joined")
        )


class AdminUserActionAPIView(AdminRequiredMixin, APIView):
    """B端後台：處理會員升級、停權、復原的 API"""

    permission_classes = [InternalAPICRUDPermission]

    @transaction.atomic
    def post(self, request, pk, action):
        user = get_object_or_404(User, pk=pk)

        if action == "upgrade":
            user.is_subscriber = True
            user.save(update_fields=["is_subscriber"])

            # 將最新一筆待審核的轉帳單設為「已核准」
            pending_payment = user.subscription_payments.filter(
                status=SubscriptionPayment.Status.PENDING
            ).first()
            if pending_payment:
                pending_payment.status = SubscriptionPayment.Status.COMPLETED
                # 如果有輸入發票號碼，這裡可以順便寫入 (假設前端有傳)
                invoice_number = request.data.get("invoice_number", None)
                if invoice_number:
                    pending_payment.invoice_number = invoice_number
                pending_payment.save(update_fields=["status", "invoice_number"])

            return Response({"message": "開通權限成功"}, status=status.HTTP_200_OK)

        elif action == "suspend":
            user.is_active = False
            user.save(update_fields=["is_active"])
            return Response({"message": "停權成功"}, status=status.HTTP_200_OK)

        elif action == "restore":
            user.is_active = True
            user.save(update_fields=["is_active"])
            return Response({"message": "復原成功"}, status=status.HTTP_200_OK)

        return Response({"error": "無效的操作"}, status=status.HTTP_400_BAD_REQUEST)


class PostCreateView(AdminRequiredMixin, TemplateView):
    template_name = "internal/post_create.html"


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [InternalAPICRUDPermission]

    def get_queryset(self):
        return Post.objects.all().select_related("author")

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def restore(self, request, pk=None):
        post = self.get_object()
        post.deleted_at = None
        post.save(update_fields=["deleted_at"])
        return Response({"status": "restored"})


class ExternalPostListView(EditorJSContentMixin, ListView):
    """C端前台首頁：文章列表 (SSR 渲染以利 SEO)"""

    model = Post
    template_name = "external/post_list.html"
    context_object_name = "posts"
    paginate_by = 10

    @method_decorator(never_cache)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        cache_key = "external:post_list:published"
        cached_posts = cache.get(cache_key)

        if cached_posts is not None:
            return [self._build_post_namespace(item) for item in cached_posts]

        print("LIST GET CACHED, THIS ONLY SHOWED ONCE PER POST")

        qs = (
            Post.objects.filter(is_published=True, deleted_at__isnull=True)
            .select_related("author")
            .order_by("-created_at")
        )

        serialized_posts = []
        for post in qs:
            raw_text = self.extract_text_from_editorjs(post.content)
            serialized_posts.append(
                {
                    "id": post.id,
                    "title": post.title,
                    "content": raw_text[:150] + "...",
                    "visibility": int(post.visibility),
                    "created_at": post.created_at,
                    "updated_at": post.updated_at,
                    "seo_data": self._extract_seo_dict(post),
                    "author": {
                        "id": post.author.id,
                        "username": getattr(post.author, "username", ""),
                        "email": getattr(post.author, "email", ""),
                    },
                }
            )

        cache.set(cache_key, serialized_posts, timeout=POST_CACHE_TTL)

        return [self._build_post_namespace(item) for item in serialized_posts]

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)


class ExternalPostDetailView(EditorJSContentMixin, DetailView):
    """C端前台：文章閱讀頁 (Server-side 截斷)"""

    model = Post
    template_name = "external/post_detail.html"
    context_object_name = "post"

    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_object(self, queryset=None):
        post_id = self.kwargs.get(self.pk_url_kwarg)
        cache_key = f"external:post_detail:{post_id}"
        cached_data = cache.get(cache_key)

        if cached_data is None:
            print("SINGLE POST GET CACHED, THIS ONLY SHOWED ONCE")
            post = get_object_or_404(
                Post.objects.filter(
                    is_published=True, deleted_at__isnull=True
                ).select_related("author"),
                pk=post_id,
            )
            cached_data = {
                "id": post.id,
                "title": post.title,
                "content": post.content,
                "visibility": int(post.visibility),
                "created_at": post.created_at,
                "updated_at": post.updated_at,
                "seo_data": self._extract_seo_dict(post),
                "author": {
                    "id": post.author.id,
                    "username": getattr(post.author, "username", ""),
                    "email": getattr(post.author, "email", ""),
                },
            }
            cache.set(cache_key, cached_data, timeout=POST_CACHE_TTL)

        return self._build_post_namespace(cached_data)

    def get_queryset(self):
        return Post.objects.filter(
            is_published=True, deleted_at__isnull=True
        ).select_related("author")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        user = self.request.user

        has_access = True
        visibility = int(post.visibility)

        if user.is_authenticated and (user.is_staff or user.is_superuser):
            has_access = True
        else:
            # 僅限註冊會員 (REGISTERED)
            if visibility == 1:
                if not user.is_authenticated:
                    has_access = False

            # 僅限訂閱者 (SUBSCRIBER)
            elif visibility == 2:
                if (
                    not user.is_authenticated
                    or getattr(user, "is_subscriber", False) is False
                ):
                    has_access = False

        if not has_access:
            raw_text = self.extract_text_from_editorjs(post.content)
            context["teaser_content"] = raw_text[:150] + "..."
            post.content = ""

        context["has_access"] = has_access
        return context
