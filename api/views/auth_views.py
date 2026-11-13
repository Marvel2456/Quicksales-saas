from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from account.forms import OwnerRegisterForm
from account.models import (
    ActivityLog,
    Branch,
    CustomUser,
    Notification,
    Organization,
    OrganizationMembership,
)
from account.tasks import (
    deactivate_subscription,
    task_send_password_reset_email,
    task_send_verification_email,
)
from account.views import _get_verification_organization, get_protocol
from api.context import resolve_mobile_context
from api.pagination import paginate_queryset
from api.permissions import MOBILE_DEFAULT_PERMISSIONS, PasswordChangedPermission
from api.serializers.auth import (
    BranchSummarySerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    MembershipSummarySerializer,
    NotificationSerializer,
    OrganizationSummarySerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    UserProfileSerializer,
)
from subscriptions.models import Plan, Subscription


def _build_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def _get_user_memberships(user):
    return (
        OrganizationMembership.objects.filter(user=user, is_active=True)
        .select_related("organization", "branch")
        .order_by("date_joined")
    )


class MobileLoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, tags=["Auth"])
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]
        requested_org_id = serializer.validated_data.get("organization_id")

        existing_user = CustomUser.objects.filter(email__iexact=email).first()
        if existing_user and not existing_user.is_active and existing_user.check_password(password):
            return Response(
                {
                    "detail": "Account email is not verified yet.",
                    "code": "account_inactive",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = authenticate(request=request, username=email, password=password)
        if user is None:
            return Response(
                {"detail": "Invalid email or password.", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        memberships = list(_get_user_memberships(user))
        active_membership = None
        if requested_org_id:
            active_membership = next(
                (m for m in memberships if str(m.organization_id) == str(requested_org_id)),
                None,
            )
            if not active_membership:
                return Response(
                    {"detail": "You do not belong to the requested organization."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif memberships:
            active_membership = next(
                (m for m in memberships if m.organization_id == user.organization_id),
                memberships[0],
            )

        active_org = active_membership.organization if active_membership else user.organization
        active_branch = active_membership.branch if active_membership else user.branch
        active_role = active_membership.role if active_membership else user.role
        permissions = (
            user.get_permissions_in_organization(organization=active_org, branch=active_branch)
            if active_org
            else []
        )

        tokens = _build_tokens_for_user(user)
        return Response(
            {
                **tokens,
                "must_change_password": bool(user.must_change_password),
                "user": UserProfileSerializer(user).data,
                "active_organization": OrganizationSummarySerializer(active_org).data if active_org else None,
                "active_branch": BranchSummarySerializer(active_branch).data if active_branch else None,
                "active_role": active_role,
                "permissions": permissions,
                "organizations": MembershipSummarySerializer(memberships, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class MobileLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LogoutSerializer, tags=["Auth"])
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)


class MobileRegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=RegisterSerializer, tags=["Auth"])
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        pw1 = data.get("password1") or data.get("password") or ""
        pw2 = data.get("password2") or pw1
        form_data = {
            "email": data["email"].strip().lower(),
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "phone_number": data.get("phone_number", ""),
            "password1": pw1,
            "password2": pw2,
            "organization_name": data["organization_name"],
            "business_type": data["business_type"],
            "organization_country": data["organization_country"],
            "branch_name": data.get("branch_name", "Main Branch"),
            "branch_address": data.get("branch_address", ""),
            "brand_color": data.get("brand_color", "#007bff"),
        }
        form = OwnerRegisterForm(form_data)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

        email = form.cleaned_data["email"].strip().lower()
        organization_name = form.cleaned_data["organization_name"]
        existing_user = CustomUser.objects.filter(email__iexact=email).first()

        if existing_user and Organization.objects.filter(
            owned_by=existing_user, name__iexact=organization_name
        ).exists():
            return Response(
                {"organization_name": [f'You already own an organization called "{organization_name}".']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            trial_start = timezone.now()
            trial_end = trial_start + timedelta(days=7)

            organization = Organization.objects.create(
                name=organization_name,
                business_type=form.cleaned_data["business_type"],
                country=form.cleaned_data["organization_country"],
                brand_color=form.cleaned_data.get("brand_color") or "#007bff",
                trial_start=trial_start,
                trial_end=trial_end,
                is_active=True,
            )
            branch = Branch.objects.create(
                organization=organization,
                name=form.cleaned_data["branch_name"],
                address=form.cleaned_data.get("branch_address", ""),
            )

            free_plan = Plan.objects.filter(price=0).first() or Plan.objects.filter(tier="free").first()
            if not free_plan:
                free_plan, _ = Plan.objects.get_or_create(
                    tier="free",
                    size="starter",
                    billing_frequency="monthly",
                    defaults={
                        "name": "Free Trial",
                        "price": 0,
                        "price_usd": 0,
                        "duration_in_days": 14,
                    },
                )
            subscription = Subscription.objects.create(
                organization=organization,
                plan=free_plan,
                currency=organization.currency_code,
                start_date=trial_start,
                end_date=trial_end,
                is_active=True,
            )
            try:
                deactivate_subscription.apply_async(args=[str(subscription.id)], eta=trial_end)
            except Exception:
                pass

            if existing_user:
                user = existing_user
                if not user.organization:
                    user.organization = organization
                    user.branch = branch
                    user.save(update_fields=["organization", "branch"])
                organization.owned_by = user
                organization.save(update_fields=["owned_by"])
                OrganizationMembership.objects.create(
                    user=user,
                    organization=organization,
                    branch=branch,
                    role="owner",
                    is_active=True,
                )
                ActivityLog.objects.create(
                    staff=user,
                    organization=organization,
                    branch=branch,
                    activity=f"Registered new organization '{organization.name}' via mobile API",
                )
                requires_verification = not user.is_active
            else:
                user = CustomUser.objects.create_user(
                    email=email,
                    password=form.cleaned_data["password1"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    phone_number=form.cleaned_data.get("phone_number", ""),
                    organization=organization,
                    branch=branch,
                    role="owner",
                    is_active=False,
                )
                organization.owned_by = user
                organization.save(update_fields=["owned_by"])
                OrganizationMembership.objects.create(
                    user=user,
                    organization=organization,
                    branch=branch,
                    role="owner",
                    is_active=True,
                )
                try:
                    task_send_verification_email.delay(user.id, organization.id)
                except Exception:
                    pass
                requires_verification = True

        return Response(
            {
                "detail": "Registration successful. Please verify your email to activate your account."
                if requires_verification
                else "New organization created successfully.",
                "requires_verification": requires_verification,
                "user": UserProfileSerializer(user).data,
                "organization": OrganizationSummarySerializer(organization).data,
                "branch": BranchSummarySerializer(branch).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MobileResendVerificationView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=ResendVerificationSerializer, tags=["Auth"])
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()

        user = CustomUser.objects.filter(email__iexact=email).first()
        if user and not user.is_active:
            organization = _get_verification_organization(user)
            if organization:
                try:
                    task_send_verification_email.delay(user.id, organization.id)
                except Exception:
                    pass

        return Response(
            {"detail": "If an unverified account exists for that email, a verification email has been sent."},
            status=status.HTTP_200_OK,
        )


class MobileForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=ForgotPasswordSerializer, tags=["Auth"])
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()

        user = CustomUser.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            protocol = get_protocol()
            domain = request.get_host()
            if settings.ENV == "production" and user.organization and settings.DOMAIN:
                domain = f"{user.organization.slug}.{settings.DOMAIN}"
            reset_link = f"{protocol}://{domain}/account/reset-password/{uid}/{token}/"
            try:
                task_send_password_reset_email.delay(user.id, reset_link)
            except Exception:
                pass

        return Response(
            {"detail": "If an account with that email exists, a password reset link has been sent."},
            status=status.HTTP_200_OK,
        )


class MobileChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, tags=["Auth"])
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        old_password = serializer.validated_data.get("old_password", "")
        new_password = serializer.validated_data["new_password"]

        if not user.must_change_password:
            if not old_password or not user.check_password(old_password):
                return Response(
                    {"old_password": ["Current password is incorrect."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            password_validation.validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])

        tokens = _build_tokens_for_user(user)
        return Response(
            {
                "detail": "Password updated successfully.",
                **tokens,
                "must_change_password": False,
            },
            status=status.HTTP_200_OK,
        )


class MobileMeView(APIView):
    permission_classes = [IsAuthenticated, PasswordChangedPermission]

    @extend_schema(tags=["Account"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        memberships = _get_user_memberships(request.user)
        return Response(
            {
                "user": UserProfileSerializer(request.user).data,
                "active_organization": OrganizationSummarySerializer(ctx.organization).data
                if ctx.organization
                else None,
                "active_branch": BranchSummarySerializer(ctx.branch).data if ctx.branch else None,
                "active_role": ctx.role,
                "permissions": ctx.permissions,
                "organizations": MembershipSummarySerializer(memberships, many=True).data,
            }
        )

    @extend_schema(request=UserProfileSerializer, tags=["Account"])
    def patch(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MobileOrganizationsView(APIView):
    permission_classes = [IsAuthenticated, PasswordChangedPermission]

    @extend_schema(tags=["Account"])
    def get(self, request):
        memberships = _get_user_memberships(request.user)
        return Response(MembershipSummarySerializer(memberships, many=True).data)


class MobileNotificationListView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["Notifications"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = Notification.objects.filter(user=request.user)
        if ctx.organization:
            qs = qs.filter(organization=ctx.organization)
        unread_count = qs.filter(is_read=False).count()
        return paginate_queryset(
            request,
            qs,
            NotificationSerializer,
            extra_data={"unread_count": unread_count},
        )


class MobileNotificationReadView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["Notifications"])
    def post(self, request, pk):
        notification = Notification.objects.filter(id=pk, user=request.user).first()
        if not notification:
            return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)


class MobileNotificationMarkAllReadView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["Notifications"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        qs = Notification.objects.filter(user=request.user, is_read=False)
        if ctx.organization:
            qs = qs.filter(organization=ctx.organization)
        updated = qs.update(is_read=True)
        return Response({"marked_read": updated})
