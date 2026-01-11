from django.urls import path
from .views import SplitTransCallBack
from .views import StkPushCallBack, TestAPIView

urlpatterns = [
    path("split-callback/", SplitTransCallBack.as_view(), name="split_callback"),
    path("stk-push/", StkPushCallBack.as_view(), name="stk_callback"),
    path("testview/", TestAPIView.as_view(), name="test_api"),
]