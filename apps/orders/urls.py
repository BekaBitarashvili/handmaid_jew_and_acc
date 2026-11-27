from django.urls import path

from . import checkout_views, views

app_name = "orders"

urlpatterns = [
    path("checkout/", checkout_views.checkout, name="checkout"),
    path("checkout/summary/", checkout_views.checkout_summary, name="checkout_summary"),
    path("order/<uuid:token>/", views.detail, name="detail"),
]
