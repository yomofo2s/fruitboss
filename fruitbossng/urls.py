from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Fruitboss admin"
admin.site.site_title = "Fruitboss"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("store.urls")),
]

# Uploaded media is served by Django only in development; use a web server / object storage in production.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
