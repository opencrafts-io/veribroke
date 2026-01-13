from rest_framework import serializers

import re

class StkPushSerializers(serializers.Serializer):
    """
    Serializer for Messages from Backend
    """
    request_id = serializers.CharField(required=True)
    target_user_id = serializers.CharField(required=True)
    trans_desc = serializers.CharField(max_length=100, required=True)
    service_name = serializers.CharField(required=True)
    reply_to = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    trans_amount = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=1,
        required=True
    )

    def validate_phone_number(self, value):
        """
        Returns True if the phone_number matches valid Kenyan formats,
        otherwise returns False.
        """
        raw_number = value.strip()

        pattern = r"^(?:\+254|254|0)?((?:7|1)\d{8})$"

        if not bool(re.match(pattern, raw_number)):
            raise serializers.ValidationError("Invalid Phone Number")
        return value

class ExtrasSerializer(serializers.Serializer):
    type = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=1,
        required=True
    )
    recipient = serializers.CharField(max_length=50)
    account_reference = serializers.CharField(max_length=100, required=False)
    occassion = serializers.CharField(max_length=100)


class SplitTransactionSerializer(serializers.Serializer):
    originator = serializers.CharField(max_length=50)
    extras = ExtrasSerializer()