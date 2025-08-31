# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('rankings/<str:exam_type>/<int:year>/', views.school_rankings, name='school_rankings'),
    path('school/<int:school_id>/', views.school_detail, name='school_detail'),
    path('region/<str:exam_type>/<int:year>/<str:region>/', views.region_rankings, name='region_rankings'),
]