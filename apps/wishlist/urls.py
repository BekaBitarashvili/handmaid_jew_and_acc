from django.urls import path

from . import views

app_name = "wishlist"

urlpatterns = [
    path("wishlist/", views.wishlist, name="list"),
    path("wishlist/toggle/<int:product_id>/", views.toggle, name="toggle"),
    path("wishlist/s/<str:token>/", views.shared, name="shared"),
]
