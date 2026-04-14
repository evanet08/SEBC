from django.urls import path
from . import views

app_name = 'sebc_app'

urlpatterns = [
    # Pages publiques
    path('', views.accueil, name='accueil'),
    path('login/', views.page_login, name='login'),
    path('candidature/', views.page_candidature, name='candidature'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # API Auth
    path('api/auth/check-email/', views.api_check_email, name='api_check_email'),
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/auth/request-otp/', views.api_request_otp, name='api_request_otp'),
    path('api/auth/verify-otp/', views.api_verify_otp, name='api_verify_otp'),
    path('api/auth/set-password/', views.api_set_password, name='api_set_password'),
    path('api/auth/logout/', views.api_logout, name='api_logout'),

    # API Candidature
    path('api/candidature/submit/', views.api_submit_candidature, name='api_submit_candidature'),
]
