from django.urls import path

from . import views

# Language-neutral: providers call this URL server-to-server.
api_urlpatterns = [
    path("payments/callback/<str:provider>/", views.callback, name="callback"),
]

# Customer-facing (under /ka/ and /en/).
app_name = "payments"
urlpatterns = [
    path("payments/fake/<str:reference>/", views.fake_bank, name="fake_bank"),
]
