from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import permission_classes, api_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import UserProfile
from .serializers import UserProfileSerializer


@swagger_auto_schema(
    methods=['POST'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'description': openapi.Schema(type=openapi.TYPE_STRING, description='First name of the user'),
            'avatar': openapi.Schema(
                type=openapi.TYPE_FILE,
                description='User\'s photo',
            ),
        },
        required=['description', 'avatar'],
    ),
    responses={
        201: 'Created',
        400: 'Bad Request',
    },
)
@api_view(['POST'])
@permission_classes([AllowAny])
def create_profile(request):
    if request.method == 'POST':
        # Получаем текущего аутентифицированного пользователя
        user = request.user

        # Добавляем текущего пользователя как владельца профиля
        serializer = UserProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=user)  # Привязываем профиль к пользователю
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Представление для просмотра профиля пользователя
@api_view(['GET'])
@permission_classes([AllowAny])
def view_profile(request):
    profile = request.user.profile
    serializer = UserProfileSerializer(profile)
    data = serializer.data

    # Добавим поле "photo_url" для представления URL-адреса фото профиля
    # data['photo_url'] = request.build_absolute_url(profile.photo.url)

    return Response(data)


@swagger_auto_schema(
    methods=['PUT'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'description': openapi.Schema(type=openapi.TYPE_STRING, description='First name of the user'),
            'avatar': openapi.Schema(
                type=openapi.TYPE_FILE,
                description='User\'s photo',
            ),
        },
        required=['description', 'avatar'],
    ),
    responses={
        201: 'Created',
        400: 'Bad Request',
    },
)
@api_view(['PUT'])
@permission_classes([AllowAny])
def update_profile(request):
    profile = request.user.profile
    serializer = UserProfileSerializer(profile, data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([AllowAny])
def delete_profile(request):
    profile = request.user.profile
    profile.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
