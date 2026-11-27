from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("account/", views.account, name="account"),
    path("terms/", views.legal_page, {"key": "terms"}, name="terms"),
    path("privacy/", views.legal_page, {"key": "privacy"}, name="privacy"),
]
