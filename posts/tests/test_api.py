# posts/tests/test_api.py
from rest_framework.test import APITestCase
from rest_framework import status
from .factories import UserFactory, AdminFactory, PostFactory
from posts.models import Post


class PostAPITests(APITestCase):
    def setUp(self):
        self.admin = AdminFactory()
        self.normal_user = UserFactory()
        self.post = PostFactory(author=self.admin)
        self.list_url = "/api/internal/posts"
        self.detail_url = f"/api/internal/posts/{self.post.id}"

    def test_api_permissions(self):
        """測試：只有 Admin 才能打 API，未登入或一般會員一律 403 (DRF 預設對未登入拋 403)"""
        # 1. 未登入
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. 一般使用者
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_excludes_soft_deleted_posts(self):
        """測試：取得列表時，應該排除已經軟刪除的文章"""
        self.client.force_authenticate(user=self.admin)

        # 將文章軟刪除
        self.post.soft_delete()

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)  # 列表應為空

    def test_create_post_and_xss_protection(self):
        """測試：Admin 建立文章，且惡意 script 標籤會被 Bleach 濾掉"""
        self.client.force_authenticate(user=self.admin)
        payload = {
            "title": "New Post",
            # 惡意代碼
            "content": '<p>Safe Text</p><script>alert("Hacked!");</script>',
            "visibility": Post.Visibility.PUBLIC,
            "is_published": True,
        }

        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 驗證 XSS 腳本已被過濾
        self.assertNotIn("<script>", response.data["content"])
        self.assertIn("<p>Safe Text</p>", response.data["content"])

        # 驗證 Author 是否自動綁定為當前 Admin
        new_post = Post.objects.get(id=response.data["id"])
        self.assertEqual(new_post.author, self.admin)

    def test_soft_delete_post(self):
        """測試：呼叫 DELETE API，資料表中的記錄不會不見，而是加上 deleted_at"""
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # 從 DB 重新抓取該文章，確認它還存在，但 deleted_at 已被設定
        self.post.refresh_from_db()
        self.assertIsNotNone(self.post.deleted_at)
