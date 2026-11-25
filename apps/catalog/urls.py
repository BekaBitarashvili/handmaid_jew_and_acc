from django.urls import path

from . import views

app_name = "catalog"

# English path words in both languages; only the slugs are translated (SPEC §3).
urlpatterns = [
    path("shop/", views.shop, name="shop"),
    path("shop/<slug:slug>/", views.shop, name="category"),
    path("product/<slug:slug>/", views.product_detail, name="product"),
]
