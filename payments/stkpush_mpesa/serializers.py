from rest_framework import serializers

import re

class StkPushSerializers(serializers.Serializer):
    """
    Serializer for Messages from Backend
    """
    request_id = serializers.CharField(required=True)
    # Not read anywhere in Veribroke's own processing -- purely a
    # caller-owned reference, historically the Verisafe user id but
    # never enforced to be one. Optional so callers outside that
    # ecosystem aren't forced to fabricate a value. See ADR 0003.
    target_user_id = serializers.CharField(required=False, allow_blank=True)
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
        Accepts +254/254/0/bare-prefixed Kenyan numbers, but always
        returns the canonical 254XXXXXXXXX form Daraja actually accepts
        -- Safaricom rejects other shapes (e.g. a leading '+') outright,
        and Veribroke previously passed whatever shape it received
        straight through unchanged.
        """
        raw_number = value.strip()

        pattern = r"^(?:\+254|254|0)?((?:7|1)\d{8})$"

        match = re.match(pattern, raw_number)
        if not match:
            raise serializers.ValidationError("Invalid Phone Number")
        return f"254{match.group(1)}"

class ExtrasSerializer(serializers.Serializer):
    type = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=1,
        required=True
    )
    recipient = serializers.CharField(max_length=50)
    occassion = serializers.CharField(max_length=100)


class SplitTransactionSerializer(serializers.Serializer):
    originator = serializers.CharField(max_length=50)
    extras = ExtrasSerializer()