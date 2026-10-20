from django.urls import path
from . import views


urlpatterns = [

    # =========================================================
    # PUBLIC
    # =========================================================

    path('', views.home, name='home'),
    path('about/', views.about, name='about'),


    # =========================================================
    # AUTH
    # =========================================================

    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path(
        'forgot-password/',
        views.forgot_password_view,
        name='forgot_password'
    ),
    path(
        'verify-email/',
        views.verify_email_view,
        name='verify_email'
    ),


    # =========================================================
    # USER
    # =========================================================

    path(
        'dashboard/',
        views.dashboard,
        name='dashboard'
    ),

    path(
        'profile/',
        views.my_profile,
        name='my_profile'
    ),

    path(
        'notifications/',
        views.notifications,
        name='notifications'
    ),

    path(
        'notifications/<int:pk>/read/',
        views.mark_notif_read,
        name='mark_notif_read'
    ),

    path(
        'become-seller/',
        views.become_seller,
        name='become_seller'
    ),

    path(
        'verify-identity/',
        views.verify_identity,
        name='verify_identity'
    ),


    # =========================================================
    # VEHICLE LISTINGS
    # =========================================================

    path(
        'vehicles/<int:pk>/',
        views.vehicle_detail,
        name='vehicle_detail'
    ),

    # NEW CHAT URL
    path(
        'vehicles/<int:pk>/chat/',
        views.send_chat_message,
        name='send_chat_message'
    ),

    path(
        'vehicles/<int:pk>/chat/poll/',
        views.chat_poll,
        name='chat_poll'
    ),

    # Global chat widget
    path('chat/inbox/', views.chat_inbox, name='chat_inbox'),
    path('chat/<int:conv_id>/thread/', views.chat_thread, name='chat_thread'),
    path('chat/<int:conv_id>/send/', views.chat_send, name='chat_send'),

    path(
        'vehicles/post/',
        views.post_vehicle,
        name='post_vehicle'
    ),

    # =========================================================
    # RATINGS
    # =========================================================

    path(
        'sellers/<int:user_id>/rate/',
        views.rate_seller,
        name='rate_seller'
    ),

    path(
        'vehicles/<int:pk>/rate/',
        views.rate_vehicle,
        name='rate_vehicle'
    ),

    path(
        'vehicles/<int:pk>/status/',
        views.update_listing_status,
        name='update_listing_status'
    ),

    path(
        'vehicles/<int:pk>/edit/',
        views.edit_vehicle,
        name='edit_vehicle'
    ),

    path(
        'vehicles/<int:pk>/delete/',
        views.delete_vehicle,
        name='delete_vehicle'
    ),

    path(
        'photos/<int:photo_id>/delete/',
        views.delete_photo,
        name='delete_photo'
    ),


    # =========================================================
    # ADMIN
    # =========================================================

    path(
        'admin-panel/',
        views.admin_dashboard,
        name='admin_dashboard'
    ),

    path(
        'admin-panel/users/',
        views.admin_users,
        name='admin_users'
    ),

    path(
        'admin-panel/users/<int:user_id>/view-id/',
        views.admin_view_seller_id,
        name='admin_view_seller_id'
    ),

    path(
        'admin-panel/users/<int:user_id>/approve-id/',
        views.admin_approve_seller_id,
        name='admin_approve_seller_id'
    ),

    path(
        'admin-panel/users/<int:user_id>/reject-id/',
        views.admin_reject_seller_id,
        name='admin_reject_seller_id'
    ),

    path(
        'admin-panel/listings/<int:pk>/review/',
        views.admin_listing_review,
        name='admin_listing_review'
    ),

    path(
        'admin-panel/listings/<int:pk>/approve/',
        views.admin_approve_listing,
        name='admin_approve_listing'
    ),

    path(
        'admin-panel/listings/<int:pk>/remove/',
        views.admin_remove_listing,
        name='admin_remove_listing'
    ),
]