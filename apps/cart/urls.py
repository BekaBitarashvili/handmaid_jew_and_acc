from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("cart/", views.detail, name="detail"),
    path("cart/drawer/", views.drawer, name="drawer"),
    path("cart/add/", views.add, name="add"),
    path("cart/update/<int:variant_id>/", views.update, name="update"),
    path("cart/remove/<int:variant_id>/", views.remove, name="remove"),
    path("cart/gift-wrap/", views.gift_wrap, name="gift_wrap"),
]
