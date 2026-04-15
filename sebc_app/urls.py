from django.urls import path
from . import views
from . import mobile_views

app_name = 'sebc_app'

urlpatterns = [
    # Pages publiques
    path('', views.accueil, name='accueil'),
    path('login/', views.page_login, name='login'),
    path('candidature/', views.page_candidature, name='candidature'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('administration/', views.administration, name='administration'),
    path('membres/', views.page_membres, name='membres'),

    # API Auth
    path('api/auth/check-email/', views.api_check_email, name='api_check_email'),
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/auth/request-otp/', views.api_request_otp, name='api_request_otp'),
    path('api/auth/verify-otp/', views.api_verify_otp, name='api_verify_otp'),
    path('api/auth/set-password/', views.api_set_password, name='api_set_password'),
    path('api/auth/logout/', views.api_logout, name='api_logout'),

    # API Candidature
    path('api/candidature/submit/', views.api_submit_candidature, name='api_submit_candidature'),
    path('api/candidature/check-parrain/', views.api_check_parrain, name='api_check_parrain'),

    # API Membre (self-service)
    path('api/membre/update-profile/', views.api_membre_update_profile, name='api_membre_update_profile'),
    path('api/membre/ayants-droits/', views.api_membre_ayants_droits, name='api_membre_ayants_droits'),
    path('api/membre/documents/', views.api_membre_documents, name='api_membre_documents'),
    path('api/membre/valider-filleul/', views.api_valider_filleul, name='api_valider_filleul'),
    path('api/membre/relancer-parrain/', views.api_relancer_parrain, name='api_relancer_parrain'),

    # API Administration CRUD
    path('api/admin/pays/', views.api_admin_pays, name='api_admin_pays'),
    path('api/admin/cellules/', views.api_admin_cellules, name='api_admin_cellules'),
    path('api/admin/provinces/', views.api_admin_provinces, name='api_admin_provinces'),
    path('api/admin/types-ayants-droits/', views.api_admin_types_ad, name='api_admin_types_ad'),
    path('api/admin/types-soutien/', views.api_admin_types_soutien, name='api_admin_types_soutien'),
    path('api/admin/parametres/', views.api_admin_parametres, name='api_admin_parametres'),
    path('api/admin/roles/', views.api_admin_roles, name='api_admin_roles'),
    path('api/admin/modules/', views.api_admin_modules, name='api_admin_modules'),

    # Page Communication
    path('communication/', views.page_communication, name='communication'),

    # API Communication
    path('api/communication/contacts/', views.api_communication_contacts, name='api_communication_contacts'),
    path('api/communication/threads/', views.api_communication_threads, name='api_communication_threads'),
    path('api/communication/', views.api_communication_messages, name='api_communication_messages'),
    path('api/communication/send/', views.api_communication_send, name='api_communication_send'),
    path('api/communication/groups/create/', views.api_communication_group_create, name='api_communication_group_create'),
    path('api/communication/groups/delete/', views.api_communication_group_delete, name='api_communication_group_delete'),
    path('api/communication/send-file/', views.api_communication_send_file, name='api_communication_send_file'),
    path('api/communication/unread/', views.api_communication_unread, name='api_communication_unread'),
    path('api/communication/visio/', views.api_communication_visio, name='api_communication_visio'),

    # API Meetings
    path('api/communication/meetings/', views.api_meeting_list, name='api_meeting_list'),
    path('api/communication/meetings/create/', views.api_meeting_create, name='api_meeting_create'),
    path('api/communication/meetings/cancel/', views.api_meeting_cancel, name='api_meeting_cancel'),
    path('api/communication/meetings/join/', views.api_meeting_join, name='api_meeting_join'),

    # ═══════════════════════════════════════════════════════
    # API MOBILE (Flutter)
    # ═══════════════════════════════════════════════════════
    # Auth
    path('api/mobile/auth/check-email/', mobile_views.mobile_check_email, name='m_check_email'),
    path('api/mobile/auth/login/', mobile_views.mobile_login, name='m_login'),
    path('api/mobile/auth/request-otp/', mobile_views.mobile_request_otp, name='m_request_otp'),
    path('api/mobile/auth/verify-otp/', mobile_views.mobile_verify_otp, name='m_verify_otp'),
    path('api/mobile/auth/set-password/', mobile_views.mobile_set_password, name='m_set_password'),
    path('api/mobile/auth/logout/', mobile_views.mobile_logout, name='m_logout'),

    # Candidature
    path('api/mobile/candidature/check-parrain/', mobile_views.mobile_check_parrain, name='m_check_parrain'),
    path('api/mobile/candidature/submit/', mobile_views.mobile_submit_candidature, name='m_submit_candidature'),

    # Membre
    path('api/mobile/membre/profile/', mobile_views.mobile_profile, name='m_profile'),
    path('api/mobile/membre/update-profile/', mobile_views.mobile_update_profile, name='m_update_profile'),
    path('api/mobile/membre/ayants-droits/', mobile_views.mobile_ayants_droits, name='m_ayants_droits'),
    path('api/mobile/membre/valider-filleul/', mobile_views.mobile_valider_filleul, name='m_valider_filleul'),
    path('api/mobile/membre/relancer-parrain/', mobile_views.mobile_relancer_parrain, name='m_relancer_parrain'),

    # Communication
    path('api/mobile/communication/contacts/', mobile_views.mobile_comm_contacts, name='m_comm_contacts'),
    path('api/mobile/communication/threads/', mobile_views.mobile_comm_threads, name='m_comm_threads'),
    path('api/mobile/communication/messages/', mobile_views.mobile_comm_messages, name='m_comm_messages'),
    path('api/mobile/communication/send/', mobile_views.mobile_comm_send, name='m_comm_send'),
    path('api/mobile/communication/send-file/', mobile_views.mobile_comm_send_file, name='m_comm_send_file'),
    path('api/mobile/communication/unread/', mobile_views.mobile_comm_unread, name='m_comm_unread'),
    path('api/mobile/communication/visio/', mobile_views.mobile_comm_visio, name='m_comm_visio'),
    path('api/mobile/communication/groups/create/', mobile_views.mobile_comm_group_create, name='m_comm_group_create'),
    path('api/mobile/communication/groups/delete/', mobile_views.mobile_comm_group_delete, name='m_comm_group_delete'),

    # Meetings
    path('api/mobile/communication/meetings/', mobile_views.mobile_meeting_list, name='m_meeting_list'),
    path('api/mobile/communication/meetings/create/', mobile_views.mobile_meeting_create, name='m_meeting_create'),
    path('api/mobile/communication/meetings/cancel/', mobile_views.mobile_meeting_cancel, name='m_meeting_cancel'),
    path('api/mobile/communication/meetings/join/', mobile_views.mobile_meeting_join, name='m_meeting_join'),

    # Ref Data
    path('api/mobile/ref-data/', mobile_views.mobile_ref_data, name='m_ref_data'),
]

