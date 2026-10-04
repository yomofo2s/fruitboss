import re

from django import forms
from django.conf import settings

from .models import ContactMessage, Order

NIGERIAN_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno", "Cross River",
    "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT Abuja", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano",
    "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo",
    "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
]


class StyledFormMixin:
    """Bootstrap classes, and placeholders for text inputs."""

    def _style(self, placeholders=False):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, (forms.CheckboxInput, forms.RadioSelect)):
                continue
            w.attrs["class"] = (w.attrs.get("class", "") + " form-control").strip()
            if placeholders and not w.attrs.get("placeholder"):
                w.attrs["placeholder"] = f.label


class CheckoutForm(StyledFormMixin, forms.ModelForm):
    state = forms.ChoiceField(choices=[("", "Select state")] + [(s, s) for s in NIGERIAN_STATES])
    payment_method = forms.ChoiceField(choices=Order.Payment.choices, widget=forms.RadioSelect)
    accept_terms = forms.BooleanField(error_messages={"required": "Please accept the terms to continue."})

    class Meta:
        model = Order
        fields = ["full_name", "email", "phone", "address", "city", "state", "notes", "payment_method"]
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
            "address": forms.TextInput(attrs={"placeholder": "House number and street name",
                                              "autocomplete": "street-address"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Delivery notes (optional)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
        online = settings.SHOP["PAYSTACK_ENABLED"]
        field = self.fields["payment_method"]
        field.choices = [c for c in Order.Payment.choices if online or c[0] != Order.Payment.CARD]
        field.initial = Order.Payment.CARD if online else Order.Payment.COD

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if len(re.sub(r"\D", "", phone)) < 10 or not re.fullmatch(r"[+\d\s()-]+", phone):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone


class ContactForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "subject", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 7})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style(placeholders=True)


class SubscribeForm(forms.Form):
    email = forms.EmailField()
