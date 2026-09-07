from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, Scan, Broker, BrokerCategory


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "password1", "password2"]


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["phone", "address", "city", "state", "zip_code", "date_of_birth"]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class ScanForm(forms.Form):
    full_name = forms.CharField(
        max_length=200,
        label="Full Name",
        help_text="Enter your full legal name as it appears on records",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "John Doe"}),
    )
    email = forms.EmailField(
        label="Email Address",
        help_text="Primary email address used on accounts",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "john@example.com"}),
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        label="Phone Number",
        help_text="Phone number linked to your accounts (optional)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "+1 (555) 123-4567"}),
    )
    address = forms.CharField(
        required=False,
        label="Address",
        help_text="Your physical address for matching records (optional)",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "123 Main St, City, State 12345"}),
    )
    categories = forms.MultipleChoiceField(
        choices=BrokerCategory.choices,
        required=False,
        label="Target Categories",
        help_text="Leave empty to scan all categories",
        widget=forms.CheckboxSelectMultiple,
    )
    is_recurring = forms.BooleanField(
        required=False,
        label="Enable Recurring Scans",
        help_text="Automatically re-scan every 90 days",
        initial=False,
    )


class DataStopForm(forms.Form):
    broker_ids = forms.MultipleChoiceField(
        choices=[],
        required=True,
        label="Select Companies",
        help_text="Choose which data brokers to submit stop requests to",
        widget=forms.CheckboxSelectMultiple,
    )
    stop_selling = forms.BooleanField(
        required=False, initial=True, label="Stop selling my data"
    )
    stop_sharing = forms.BooleanField(
        required=False, initial=True, label="Stop sharing with third parties"
    )
    stop_marketing = forms.BooleanField(
        required=False, initial=True, label="Stop marketing communications"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["broker_ids"].choices = [
            (str(b.id), b.name) for b in Broker.objects.filter(is_active=True)
        ]
