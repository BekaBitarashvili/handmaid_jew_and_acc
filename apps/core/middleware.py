from django.http import HttpRequest
from django.middleware.locale import LocaleMiddleware as DjangoLocaleMiddleware


class LocaleMiddleware(DjangoLocaleMiddleware):
    """Language = URL prefix, else the language cookie, else Georgian (SPEC §3).

    Django's version also consults the browser's Accept-Language header; the shop
    deliberately ignores it so every first visit lands on /ka/.
    """

    def process_request(self, request: HttpRequest) -> None:
        request.META.pop("HTTP_ACCEPT_LANGUAGE", None)
        super().process_request(request)
