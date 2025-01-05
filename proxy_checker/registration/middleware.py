from rest_framework_simplejwt.tokens import RefreshToken


def get_user_access_token(user):
    # Получите или создайте объект RefreshToken для пользователя
    refresh = RefreshToken.for_user(user)
    # Верните access_token из объекта RefreshToken
    return str(refresh.access_token)


class AddAuthorizationHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Проверяем, авторизован ли пользователь
        if request.user.is_authenticated:
            # Получаем токен пользователя
            access_token = get_user_access_token(request.user)
            # Добавляем токен в заголовок Authorization
            request.META['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'

        response = self.get_response(request)
        return response
