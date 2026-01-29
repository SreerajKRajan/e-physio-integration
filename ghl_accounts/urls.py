from django.urls import path
from ghl_accounts.views import *

urlpatterns = [
    path("auth/connect/", auth_connect, name="oauth_connect"),
    path("auth/tokens/", tokens, name="oauth_tokens"),
    path("auth/callback/", callback, name="oauth_callback"),
    
    path("webhooks/", ghl_webhook),
]