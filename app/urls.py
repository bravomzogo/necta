# app/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("rankings/<str:exam_type>/<int:year>/", views.school_rankings, name="school_rankings"),
    path('', views.home, name='home'),

]

