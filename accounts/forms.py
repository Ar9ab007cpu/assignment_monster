"""Forms used in the accounts app."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import ProfileUpdateRequest, User
from .models import FloorSignupRequest
from formbuilder.utils import apply_schema_to_form


class SignupForm(forms.ModelForm):
    """Marketing sign-up form with password confirmation."""

    password1 = forms.CharField(
        label="Create Password",
        widget=forms.PasswordInput,
        help_text="Minimum 8 characters with a letter, number & symbol.",
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
    )

    whatsapp_country_code = forms.ChoiceField(
        choices=[
            ("+91", "+91 India"),
            ("+44", "+44 UK"),
            ("+1", "+1 USA"),
        ],
        label="Country Code",
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "whatsapp_country_code",
            "whatsapp_number",
            "last_qualification",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-control"
            if isinstance(field.widget, forms.Select):
                css_class = "form-select"
            field.widget.attrs.setdefault("class", css_class)
        apply_schema_to_form(self, "signup", None)

    def clean(self):
        data = super().clean()
        password1 = data.get("password1")
        password2 = data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        if password1:
            if len(password1) < 8:
                self.add_error("password1", "Password must be at least 8 characters.")
            has_letter = any(ch.isalpha() for ch in password1)
            has_number = any(ch.isdigit() for ch in password1)
            has_symbol = any(not ch.isalnum() for ch in password1)
            if not (has_letter and has_number and has_symbol):
                self.add_error(
                    "password1",
                    "Password must include letters, numbers, and symbols.",
                )
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.MARKETING
        user.set_password(self.cleaned_data["password1"])
        user.is_active = True
        user.is_account_approved = False
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Login form using email + password."""

    username = forms.EmailField(label="Email ID")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class GlobalProfileEditForm(forms.ModelForm):
    """Allow global users to tweak name + avatar only."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "profile_picture"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "profile_picture": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": "image/*"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].label = "Preferred first name"
        self.fields["last_name"].label = "Preferred last name"
        self.fields["profile_picture"].label = "Profile picture"

    def clean_first_name(self):
        value = (self.cleaned_data.get("first_name") or "").strip()
        if not value:
            raise forms.ValidationError("First name is required.")
        return value

    def clean_last_name(self):
        value = (self.cleaned_data.get("last_name") or "").strip()
        if not value:
            raise forms.ValidationError("Last name is required.")
        return value


class ProfileUpdateRequestForm(forms.ModelForm):
    """Form to send profile update requests."""

    class Meta:
        model = ProfileUpdateRequest
        fields = ["request_type", "updated_value", "file_upload", "notes"]
        widgets = {
            "request_type": forms.Select(attrs={"class": "form-select"}),
            "updated_value": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["file_upload"].widget.attrs.setdefault("class", "form-control")
        self.fields["notes"].widget.attrs.setdefault("placeholder", "Optional notes")
        apply_schema_to_form(self, "profile_request", getattr(self.user, "role", None))

    def clean(self):
        data = super().clean()
        request_type = data.get("request_type")
        updated_value = data.get("updated_value")
        file_upload = data.get("file_upload")

        if request_type == ProfileUpdateRequest.RequestType.PROFILE_PICTURE:
            if not file_upload:
                self.add_error("file_upload", "Please upload a profile picture.")
        else:
            if not updated_value:
                self.add_error("updated_value", "Please provide the new value.")
        return data

    def save(self, commit=True):
        request_obj = super().save(commit=False)
        request_obj.user = self.user
        target_field = request_obj.get_target_field()
        if target_field:
            value = getattr(self.user, target_field, "")
            if target_field == "profile_picture" and value:
                request_obj.current_value = value.name
            else:
                request_obj.current_value = value if value is not None else ""
        if commit:
            request_obj.save()
        return request_obj


class FloorSignupForm(forms.Form):
    """Floor signup with invite code; generates username automatically."""

    invite_code = forms.CharField(label="Invite Code", max_length=16)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    password1 = forms.CharField(
        label="Create Password",
        widget=forms.PasswordInput,
        help_text="Minimum 8 characters with a letter, number & symbol.",
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_invite_code(self):
        code = self.cleaned_data["invite_code"].strip()
        from .models import InviteCode

        invite = InviteCode.objects.filter(code=code).first()
        if not invite or not invite.is_valid():
            raise forms.ValidationError("Invalid or expired invite code.")
        self.invite = invite
        return code

    def clean(self):
        data = super().clean()
        p1 = data.get("password1")
        p2 = data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1:
            if len(p1) < 8:
                self.add_error("password1", "Password must be at least 8 characters.")
            has_letter = any(ch.isalpha() for ch in p1)
            has_number = any(ch.isdigit() for ch in p1)
            has_symbol = any(not ch.isalnum() for ch in p1)
            if not (has_letter and has_number and has_symbol):
                self.add_error(
                    "password1",
                    "Password must include letters, numbers, and symbols.",
                )
        return data

    def save(self):
        from .models import User
        user = User(
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            role=User.Role.FLOOR,
        )
        username = user.generate_floor_username()
        user.floor_username = username
        # generate placeholder email to satisfy unique constraint, not used for login
        user.email = f"{username.lower()}@floor.local"
        user.set_password(self.cleaned_data["password1"])
        user.is_active = True
        user.is_account_approved = True
        user.save()
        # mark invite used
        self.invite.mark_used()
        return user


class FloorLoginForm(forms.Form):
    """Floor login by username."""

    username = forms.CharField(label="Username")
    password = forms.CharField(label="Password", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class FloorSignupRequestForm(forms.ModelForm):
    """Request-based floor signup using legacy signup fields."""

    class Meta:
        model = FloorSignupRequest
        fields = [
            "first_name",
            "last_name",
            "email",
            "whatsapp_country_code",
            "whatsapp_number",
            "last_qualification",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-control"
            if isinstance(field.widget, forms.Select):
                css_class = "form-select"
            field.widget.attrs.setdefault("class", css_class)
