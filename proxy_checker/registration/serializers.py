from rest_framework import serializers
from .models import User, UserProfile
from rest_framework_simplejwt.tokens import RefreshToken


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'phone_number', 'password')  # registration fields
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': True},
            'phone_number': {'required': True},
            'password': {'required': True},
        }

    def create(self, validated_data):
        user = User.objects.create(
            email=validated_data['email'],
            username=validated_data['username'],
            phone_number=validated_data['phone_number']
        )

        user.set_password(validated_data['password'])
        user.save()

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        # Include tokens in the response data
        validated_data['access_token'] = access_token
        validated_data['refresh_token'] = str(refresh)

        return user


class UserProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.FileField(max_length=None, use_url=True, required=False)

    class Meta:
        model = UserProfile
        fields = ('avatar', 'description')


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Проверяем, существует ли пользователь с указанным email
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь с данной почтой не найден")

        return value


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    # def validate_password(self, value):
    #     # Проверяем, существует ли пользователь с указанным email
    #     try:
    #         user = User.objects.get(email=value)
    #     except User.DoesNotExist:
    #         raise serializers.ValidationError("Пользователь с данной почтой не найден")
    #
    #     return value