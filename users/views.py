from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class ExternalLoginRequiredMixin(LoginRequiredMixin):
    """
    外部頁面專用的權限驗證 Mixin
    如果未登入，強制導向外部的 /login，而不是後台的 /internal/login
    """

    login_url = "/login"


class ExternalSignupView(TemplateView):
    """C端註冊頁面"""

    template_name = "external/signup.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("/")
        return super().dispatch(request, *args, **kwargs)


class ExternalLoginView(TemplateView):
    template_name = "external/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("/")
        return super().dispatch(request, *args, **kwargs)


class UserProfileView(ExternalLoginRequiredMixin, TemplateView):
    """
    C端個人頁面 (管理訂閱內容)
    必須登入才能存取，未登入會被 Mixin 踢回 /login
    """

    template_name = "external/profile.html"
