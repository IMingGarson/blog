from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PostViewSet,
    ExternalPostListView,
    ExternalPostDetailView,
    AdminUserActionAPIView,
)

app_name = "posts"

# ==========================================
# DRF Router (專供後台 Internal API 使用)
# ==========================================
router = DefaultRouter(trailing_slash=False)
router.register(r"posts", PostViewSet, basename="post")

urlpatterns = [
    # ------------------------------------------
    # External API / HTML
    # ------------------------------------------
    # 網站 Home Page
    path("", ExternalPostListView.as_view(), name="post_list"),
    # 單篇文章閱讀頁
    path("post/<int:pk>", ExternalPostDetailView.as_view(), name="post_detail"),
    # ------------------------------------------
    # Internal API
    # ------------------------------------------
    # 使用者操作
    path(
        "api/internal/users/<int:pk>/<str:action>",
        AdminUserActionAPIView.as_view(),
        name="user_action",
    ),
    path("api/internal/", include(router.urls)),
]
