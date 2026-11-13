from django.test import TestCase
from django.urls import reverse
from .factories import UserFactory, AdminFactory


class AdminViewTests(TestCase):
    def setUp(self):
        self.admin = AdminFactory()
        self.normal_user = UserFactory()
        self.login_url = reverse("login")
        self.dashboard_url = reverse("internal_dashboard")

    def test_unauthenticated_user_redirects_to_login(self):
        """測試：未登入者應被導向登入頁"""
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.login_url, response.url)

    def test_normal_user_gets_403(self):
        """測試：一般使用者登入後存取 Admin 頁面應被阻擋 (403 Forbidden)"""
        self.client.force_login(self.normal_user)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 403)

    def test_admin_user_gets_200(self):
        """測試：Admin 登入後可正常存取"""
        self.client.force_login(self.admin)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_logout_redirect(self):
        """測試：登出行為是否正常導向"""
        self.client.force_login(self.admin)
        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.login_url)
