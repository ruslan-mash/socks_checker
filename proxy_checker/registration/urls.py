from . import views, profile
from django.urls import path, include
from rest_framework import permissions
from drf_yasg import openapi
from drf_yasg.views import get_schema_view

schema_view = get_schema_view(
    openapi.Info(
        title='Registration API',
        default_version='v1',
        description='API for user registration',
        terms_of_service="",
        contact=openapi.Contact(email="contact@gmail.com"),
        license=openapi.License(name="Your_lic"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('register/', views.registration_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change_password/', views.change_password, name='change_password'),
    path('reset_password/', views.reset_password, name='reset_password'),
    path('profile/create/', profile.create_profile, name='create_profile'),
    path('profile/', profile.view_profile, name='view_profile'),
    path('profile/update/', profile.update_profile, name='update_profile'),
    path('profile/delete/', profile.delete_profile, name='delete_profile'),
]
