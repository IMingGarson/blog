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
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.utils.html import strip_tags
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView


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

    @method_decorator(cache_page(86400))
    @method_decorator(vary_on_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        return (
            Post.objects.filter(is_published=True, deleted_at__isnull=True)
            .select_related("author")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for post in context["posts"]:
            raw_text = self.extract_text_from_editorjs(post.content)
            post.content = raw_text[:150] + "..."

        return context


class ExternalPostDetailView(EditorJSContentMixin, DetailView):
    """C端前台：文章閱讀頁 (Server-side 截斷)"""

    model = Post
    template_name = "external/post_detail.html"
    context_object_name = "post"

    @method_decorator(cache_page(86400))
    @method_decorator(vary_on_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        return Post.objects.filter(
            is_published=True, deleted_at__isnull=True
        ).select_related("author")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        user = self.request.user

        # 預設為擁有權限 (Rule 4: 任何人看 Public 都為 True)
        has_access = True
        visibility = int(post.visibility)  # 強制轉整數防呆

        # 管理員 (Bypass)
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
                    or getattr(user, "is_subscriber", False) == False
                ):
                    has_access = False

        # 伺服器端資料截斷與銷毀
        if not has_access:
            raw_text = self.extract_text_from_editorjs(post.content)
            context["teaser_content"] = raw_text[:150] + "..."
            post.content = ""

        context["has_access"] = has_access
        return context
