from django.urls import path

from . import views
from .queries import COLLECTION_NEW, COLLECTION_SALE

app_name = "catalog"

# English path words in both languages; only the slugs are translated (SPEC §3).
# "new" and "sale" come before the category pattern and are reserved category slugs.
urlpatterns = [
    path("shop/", views.listing, name="shop"),
    path("shop/new/", views.listing, {"collection": COLLECTION_NEW}, name="new"),
    path("shop/sale/", views.listing, {"collection": COLLECTION_SALE}, name="sale"),
    path("shop/<slug:slug>/", views.listing, name="category"),
    path("product/<slug:slug>/", views.product_detail, name="product"),
]
