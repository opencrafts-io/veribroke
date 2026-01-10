from django.urls import path
from .views import StkPushCallBack, TestAPIView

urlpatterns = [
    path("stk-push/", StkPushCallBack.as_view(), name="stk-callback"),
    path("testview/", TestAPIView.as_view(), name="test_api"),
]