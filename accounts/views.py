"""Views for authentication, profile, and request flows."""

from django.contrib import messages
from django.contrib.auth import logout, login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.conf import settings
from django.utils.crypto import get_random_string
from urllib.parse import urlencode
from django.core.paginator import Paginator
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView
from django.views import View
import requests
from django.http import HttpResponseRedirect

from decimal import Decimal
try:
    from bson.decimal128 import Decimal128
    from bson.objectid import ObjectId
except Exception:
    Decimal128 = None
    ObjectId = None
from common.mixins import ManagementSystemGateMixin
from common.models import ManagementSystem
from common.system_control import is_system_enabled

from .forms import (
    LoginForm,
    ProfileUpdateRequestForm,
    SignupForm,
    FloorLoginForm,
    FloorSignupRequestForm,
)
from .models import ProfileUpdateRequest, User, FloorSignupRequest, GemsAccount, GemTransaction


def ensure_gems_account(user, reason="Welcome bonus"):
    """
    Guarantee a gems account with a clean PK and Decimal balance.
    Older rows coming from Mongo can have ObjectId PKs or Decimal128 balances;
    we rebuild those rows to avoid conversion errors during save().
    """

    def coerce_decimal(val):
        if Decimal128 and isinstance(val, Decimal128):
            val = val.to_decimal()
        try:
            return Decimal(str(val))
        except Exception:
            return Decimal("0")

    # If duplicates exist (possible after schema changes), consolidate to a single row.
    accounts_qs = list(GemsAccount.objects.filter(user=user).order_by("-created_at"))
    if len(accounts_qs) > 1:
        for extra in accounts_qs[1:]:
            extra.delete()
    account = accounts_qs[0] if accounts_qs else None
    created = False

    if account:
        coerced_bal = coerce_decimal(account.balance)
        pk_val = getattr(account, "pk", None)
        pk_bad = pk_val is None
        if pk_bad:
            if pk_val:
                account.delete()
            account = GemsAccount.objects.create(user=user, balance=coerced_bal)
            created = True
        else:
            account.balance = coerced_bal
            try:
                account.save()
            except Exception:
                if getattr(account, "pk", None):
                    account.delete()
                account = GemsAccount.objects.create(user=user, balance=coerced_bal)
                created = True
    else:
        account = GemsAccount.objects.create(user=user, balance=Decimal("0"))
        created = True

    # Apply welcome bonus only once (brand new account with zero balance)
    if account.balance == 0 and created:
        account.balance = Decimal("50")
        account.save()
        GemTransaction.objects.create(
            user=user,
            amount=Decimal("50"),
            reason=reason,
            created_by=None,
        )
    return account


def role_home_url(user):
    if user.role in {User.Role.SUPER_ADMIN, User.Role.CO_SUPER_ADMIN}:
        return reverse("superadmin:welcome")
    if user.role == User.Role.GLOBAL:
        return reverse("marketing:global_home")
    if user.role == User.Role.MARKETING:
        return reverse("marketing:welcome")
    if user.role == User.Role.FLOOR:
        return reverse("common:welcome")
    return reverse("common:welcome")


class SignupView(ManagementSystemGateMixin, FormView):
    template_name = "accounts/signup.html"
    form_class = SignupForm
    success_url = reverse_lazy("accounts:login")
    management_system_key = ManagementSystem.Keys.SIGNUP_LOGIN

    def form_valid(self, form):
        form.save()
        messages.success(
            self.request,
            "Sign up successful. Please wait for Super Admin approval.",
        )
        return super().form_valid(form)


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return HttpResponseRedirect(role_home_url(request.user))
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        user = self.request.user
        if not user.is_account_approved:
            return reverse_lazy("common:welcome")
        return role_home_url(user)

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        ensure_gems_account(user, "Welcome bonus")
        if not user.is_active:
            logout(self.request)
            messages.error(
                self.request,
                "Your account is inactive. Please contact a Super Admin for reactivation.",
            )
            return redirect("accounts:login")
        if (
            user.role == User.Role.MARKETING
            and not is_system_enabled(ManagementSystem.Keys.SIGNUP_LOGIN, user)
        ):
            logout(self.request)
            messages.error(
                self.request,
                "Login is currently disabled by the Super Admin.",
            )
            return redirect("accounts:login")
        return response


class GlobalSSOStartView(View):
    """Begin OAuth2/OIDC login for Global users."""

    def get(self, request):
        client_id = getattr(settings, "GLOBAL_OIDC_CLIENT_ID", "")
        redirect_uri = getattr(settings, "GLOBAL_OIDC_REDIRECT_URI", "")
        if not all([client_id, redirect_uri]):
            messages.error(request, "Global SSO is not configured.")
            return redirect("accounts:login")
        state = get_random_string(24)
        request.session["global_oidc_state"] = state
        authorize = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        return redirect(f"{authorize}?{urlencode(params)}")


class GlobalSSOCallbackView(View):
    """Handle OAuth2/OIDC callback. Token exchange not completed without provider settings."""

    def get(self, request):
        state = request.GET.get("state")
        code = request.GET.get("code")
        expected_state = request.session.get("global_oidc_state")
        if not state or state != expected_state:
            messages.error(request, "Invalid SSO state.")
            return redirect("accounts:login")
        if not code:
            messages.error(request, "No authorization code returned from provider.")
            return redirect("accounts:login")
        client_id = getattr(settings, "GLOBAL_OIDC_CLIENT_ID", "")
        client_secret = getattr(settings, "GLOBAL_OIDC_CLIENT_SECRET", "")
        redirect_uri = getattr(settings, "GLOBAL_OIDC_REDIRECT_URI", "")
        if not all([client_id, client_secret, redirect_uri]):
            messages.error(request, "Global SSO is not fully configured.")
            return redirect("accounts:login")
        token_url = "https://oauth2.googleapis.com/token"
        userinfo_url = "https://openidconnect.googleapis.com/v1/userinfo"
        try:
            resp = requests.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            if resp.status_code != 200:
                messages.error(request, f"Token exchange failed ({resp.status_code}).")
                try:
                    print("Token error:", resp.text)
                except Exception:
                    pass
                return redirect("accounts:login")
            data = resp.json()
            access_token = data.get("access_token")
            if not access_token:
                messages.error(request, "Token exchange failed: no access token.")
                return redirect("accounts:login")
            # Fetch userinfo
            uresp = requests.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if uresp.status_code != 200:
                messages.error(request, f"Userinfo fetch failed ({uresp.status_code}).")
                try:
                    print("Userinfo error:", uresp.text)
                except Exception:
                    pass
                return redirect("accounts:login")
            uinfo = uresp.json()
            email = uinfo.get("email")
            if not email:
                messages.error(request, "No email returned from provider.")
                return redirect("accounts:login")
            first_name = uinfo.get("given_name", "")
            last_name = uinfo.get("family_name", "")
            user = User.objects.filter(email__iexact=email).first()
            created_user = False
            if not user:
                user = User(
                    email=email,
                    first_name=first_name or email.split("@")[0],
                    last_name=last_name,
                    role=User.Role.GLOBAL,
                    is_account_approved=True,
                    is_active=True,
                )
                user.set_unusable_password()
                user.save()
                created_user = True
            else:
                # if existing user, update names if blank
                updated = False
                if not user.first_name and first_name:
                    user.first_name = first_name
                    updated = True
                if not user.last_name and last_name:
                    user.last_name = last_name
                    updated = True
                if user.role != User.Role.GLOBAL:
                    user.role = User.Role.GLOBAL
                    updated = True
                if updated:
                    user.save(update_fields=["first_name", "last_name", "role"])
            # ensure gems account
            ensure_gems_account(user, "Welcome bonus")
            # capture basic login meta
            user.last_login_ip = request.META.get("REMOTE_ADDR") or ""
            user.last_login_timezone = request.META.get("TZ") or ""
            user.save(update_fields=["last_login_ip", "last_login_timezone"])
            auth_login(request, user)
            messages.success(request, "Logged in via Global SSO.")
            return redirect(role_home_url(user))
        except Exception:
            messages.error(request, "Global SSO login failed. Please try again.")
            import traceback
            traceback.print_exc()
            return redirect("accounts:login")


class FloorSignupView(FormView):
    template_name = "accounts/floor_signup.html"
    form_class = FloorSignupRequestForm
    success_url = reverse_lazy("accounts:floor_signup_status")

    def form_valid(self, form):
        req = form.save()
        messages.success(self.request, "Signup request submitted. Wait for approval.")
        return redirect("accounts:floor_signup_status", token=req.request_token)


class FloorLoginView(FormView):
    template_name = "accounts/floor_login.html"
    form_class = FloorLoginForm
    success_url = reverse_lazy("marketing:welcome")

    def form_valid(self, form):
        from .models import User
        username = form.cleaned_data["username"].strip()
        password = form.cleaned_data["password"]
        # Allow login by floor username even if the role was later updated (e.g., to Marketing)
        user = User.objects.filter(floor_username=username).first()

        if user and user.check_password(password):
            from django.contrib.auth import login as auth_login

            auth_login(self.request, user)
            ensure_gems_account(user, "Welcome bonus")
            return HttpResponseRedirect(role_home_url(user))

        messages.error(
            self.request,
            "Invalid username or password, or account not yet approved. Please contact admin if already approved.",
        )
        return self.form_invalid(form)


class FloorSignupStatusView(View):
    template_name = "accounts/floor_signup_status.html"

    def get(self, request, token=None):
        token = token or request.GET.get("token")
        req = FloorSignupRequest.objects.filter(request_token=token).first()
        if not req:
            messages.error(request, "Invalid or missing request token.")
            return redirect("accounts:floor_signup")
        show_creds = False
        if req.status == FloorSignupRequest.Status.APPROVED and not req.creds_viewed:
            show_creds = True
            req.creds_viewed = True
            req.save(update_fields=["creds_viewed"])
        return render(request, self.template_name, {"req": req, "show_creds": show_creds})


class FloorStatusLookupView(View):
    template_name = "accounts/floor_status_lookup.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip().lower()
        result = (
            FloorSignupRequest.objects.filter(email__iexact=email)
            .order_by("-created_at")
            .first()
        )
        if not result:
            messages.error(request, "No signup request found for that email.")
            return render(request, self.template_name)
        show_creds = False
        if result.status == FloorSignupRequest.Status.APPROVED and not result.creds_viewed:
            show_creds = True
            result.creds_viewed = True
            result.save(update_fields=["creds_viewed"])
        return render(request, self.template_name, {"result": result, "show_creds": show_creds})


@method_decorator(login_required, name="dispatch")
class ProfileView(ManagementSystemGateMixin, TemplateView):
    template_name = "accounts/profile.html"
    management_system_key = ManagementSystem.Keys.PROFILE

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        requests_qs = ProfileUpdateRequest.objects.filter(user=user).order_by(
            "-created_at"
        )
        paginator = Paginator(requests_qs, 5)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["profile_requests"] = page_obj
        context["requests_paginator"] = paginator
        context["requests_page_obj"] = page_obj
        return context


@method_decorator(login_required, name="dispatch")
class ProfileUpdateRequestView(ManagementSystemGateMixin, FormView):
    template_name = "accounts/profile_update_request.html"
    form_class = ProfileUpdateRequestForm
    success_url = reverse_lazy("accounts:profile")
    management_system_key = ManagementSystem.Keys.PROFILE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Request submitted to Super Admin.")
        return super().form_valid(form)


@login_required
def email_verification_pending(request):
    """Simple view to show the pending approval screen."""

    if not is_system_enabled(ManagementSystem.Keys.PROFILE, request.user):
        messages.error(
            request,
            "Profile pages are currently disabled by the Super Admin.",
        )
        return redirect("common:welcome")
    return render(request, "accounts/email_verification_pending.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("accounts:login")
