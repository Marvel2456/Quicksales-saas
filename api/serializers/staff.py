from rest_framework import serializers

from account.models import (
    OrganizationMembership,
    VALID_STAFF_PERMISSION_KEYS,
)


class StaffMembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = OrganizationMembership
        fields = [
            "id",
            "user_id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "branch_id",
            "branch_name",
            "permissions",
            "is_active",
            "date_joined",
        ]


class StaffCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=["manager", "sales"], default="sales")
    branch_id = serializers.UUIDField()
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    def validate_permissions(self, value):
        invalid = [p for p in value if p not in VALID_STAFF_PERMISSION_KEYS]
        if invalid:
            raise serializers.ValidationError(
                f"Invalid permission key(s): {', '.join(invalid)}."
            )
        return sorted(set(value))


class StaffUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["manager", "sales"], required=False)
    branch_id = serializers.UUIDField(required=False)
    is_active = serializers.BooleanField(required=False)
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )

    def validate_permissions(self, value):
        invalid = [p for p in value if p not in VALID_STAFF_PERMISSION_KEYS]
        if invalid:
            raise serializers.ValidationError(
                f"Invalid permission key(s): {', '.join(invalid)}."
            )
        return sorted(set(value))

