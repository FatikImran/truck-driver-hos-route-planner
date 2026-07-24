from django.urls import path
from . import views

urlpatterns = [
    path('', views.api_root, name='api-root'),  # Optional: response for /api/
    path('route', views.route_planner, name='route_planner'),
    path('geocode-suggest', views.geocode_suggest, name='geocode_suggest'),
]
