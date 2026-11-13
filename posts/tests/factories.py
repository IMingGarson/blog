import factory
from django.contrib.auth import get_user_model
from posts.models import Post

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    is_staff = False
    is_active = True


class AdminFactory(UserFactory):
    """繼承 UserFactory，專門產生 Admin 權限的使用者"""

    is_staff = True


class PostFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Post

    title = factory.Sequence(lambda n: f"Test Post {n}")
    content = "<p>This is a safe content.</p>"
    author = factory.SubFactory(AdminFactory)
    visibility = Post.Visibility.PUBLIC
    is_published = True
