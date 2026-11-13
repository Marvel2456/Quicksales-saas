from rest_framework import serializers

from account.models import Branch, CustomUser, Notification, Organization, OrganizationMembership


class BranchSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "address", "created_at"]


class OrganizationSummarySerializer(serializers.ModelSerializer):
    currency_code = serializers.CharField(read_only=True)
    currency_symbol = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "business_type",
            "country",
            "currency_code",
            "currency_symbol",
            "brand_color",
            "is_active",
        ]


class MembershipSummarySerializer(serializers.ModelSerializer):
    organization = OrganizationSummarySerializer(read_only=True)
    branch = BranchSummarySerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationMembership
        fields = ["id", "organization", "branch", "role", "permissions", "is_active"]

    def get_permissions(self, obj):
        return obj.user.get_permissions_in_organization(
            organization=obj.organization,
            branch=obj.branch,
        )


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "must_change_password",
            "is_active",
        ]
        read_only_fields = ["id", "email", "role", "must_change_password", "is_active"]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    organization_id = serializers.UUIDField(required=False, allow_null=True)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    password1 = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    password2 = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    organization_name = serializers.CharField(max_length=200)
    business_type = serializers.CharField(max_length=100)
    organization_country = serializers.CharField(max_length=100)
    branch_name = serializers.CharField(max_length=200, default="Main Branch")
    branch_address = serializers.CharField(max_length=250, required=False, allow_blank=True, default="")
    brand_color = serializers.CharField(max_length=20, required=False, default="#007bff")


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "message", "notification_type", "is_read", "created_at", "organization"]
        read_only_fields = fields

