from django.urls import path
from . import views

urlpatterns = [
    # Home page
    path('', views.home, name='home'),
    
    # General rankings (for ACSEE, CSEE, etc.)
    path('rankings/<str:exam_type>/<int:year>/', views.school_rankings, name='school_rankings'),
    
    # School detail page
    path('school/<int:school_id>/', views.school_detail, name='school_detail'),
    
    # Region rankings for general exams
    path('region/<str:exam_type>/<int:year>/<str:region>/', views.region_rankings, name='region_rankings'),
    
    # PSLE specific routes
    path('psle/<int:year>/', views.psle_rankings, name='psle_rankings'),
    path('psle/<int:year>/<str:region>/', views.psle_region_rankings, name='psle_region_rankings'),
    path('psle/<int:year>/<str:region>/<str:district>/', views.psle_district_rankings, name='psle_district_rankings'),
    path('psle/<int:year>/<str:region>/<str:district>/<str:council>/', views.psle_council_rankings, name='psle_council_rankings'),
    path('school/psle/<int:school_id>/', views.psle_school_detail, name='psle_school_detail'),

    
    # Regions list page
    # path('regions/', views.regions_list, name='regions_list'),
]