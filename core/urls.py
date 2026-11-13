from django.urls import path, include
from django.http import HttpResponse
from django.contrib.auth.views import LoginView, LogoutView
from posts.views import (
    InternalDashboardView,
    PostCreateView,
    InternalPostPreviewView,
    InternalPostEditView,
    InternalDraftPreviewView,
    InternalUserListView,
)


def robots_txt(request):
    lines = ["User-agent: *", "Disallow: /internal/", "Disallow: /api/internal/"]
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    # SEO 爬蟲設定
    path("robots.txt", robots_txt),
    # ------------------------------------------
    # C端 (External) 功能模組 (掛載於根目錄)
    # ------------------------------------------
    # 包含首頁 (/)、單篇文章 (/post/<id>) 與內部 API (/api/internal/...)
    path("", include("posts.urls")),
    # 包含註冊登入 (/signup, /login) 與 C端使用者 API (/api/users/...)
    path("", include("users.urls")),
    # 綠界金流 Webhook 與結帳 API
    path("api/payments/", include("payments.urls")),
    # ------------------------------------------
    # B端 (Internal) HTML 頁面路由
    # ------------------------------------------
    # 後台登入 / 登出
    path(
        "internal/login",
        LoginView.as_view(template_name="internal/login.html"),
        name="internal_login",
    ),
    path(
        "internal/logout",
        LogoutView.as_view(next_page="/internal/login"),
        name="internal_logout",
    ),
    # 後台 Dashboard
    path("internal", InternalDashboardView.as_view(), name="internal_dashboard"),
    # 使用者列表
    path("internal/users", InternalUserListView.as_view(), name="internal_user_list"),
    # 後台文章發布頁
    path(
        "internal/posts/create", PostCreateView.as_view(), name="internal_post_create"
    ),
    path(
        "internal/posts/<int:pk>/preview",
        InternalPostPreviewView.as_view(),
        name="internal_post_preview",
    ),
    path(
        "internal/posts/<int:pk>/edit",
        InternalPostEditView.as_view(),
        name="internal_post_edit",
    ),
    path(
        "internal/preview",
        InternalDraftPreviewView.as_view(),
        name="internal_draft_preview",
    ),
]
