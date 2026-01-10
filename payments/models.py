from django.db import models
from uuid import uuid4


class Transactions(models.Model):
    """
    Holds Transactions Information
    """
    trans_types = (
        ("MPESASTKPUSH", "MPESASTKPUSH"),
    )

    statuses = (
        ("pending", "pending"),
        ("success", "success"),
        ("failure", "failure"),
    )

    request_id = models.CharField(
        max_length=350,
        primary_key=True,
        editable=False,
    )
    target_user_id = models.CharField(
        max_length=350,
        null=False,
    )
    trans_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
    )
    sender = models.CharField(
        max_length=255,
        null=False
    )
    reference_id = models.CharField(
        max_length=350,
        unique=True,
    )
    trans_code = models.CharField(
        max_length=350,
        unique=True,
        null=True
    )
    status = models.CharField(
        max_length=9,
        choices=statuses,
        default="pending",
        null=False,
    )
    message = models.TextField(
        null=True,
    )
    trans_desc = models.TextField(
        null=True,
    )
    trans_type = models.CharField(
        max_length=12,
        choices=trans_types,
        null=False,
    )
    service_name = models.CharField(
        max_length=50,
        null=False,
    )
    reply_to = models.CharField(
        max_length=255,
        null=False,
    )
    split = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True, null=False)
    updated = models.DateTimeField(auto_now=True, null=False)


class SplitTransactions(models.Model):
    """
    Holds Transactions Information
    """
    originator_types = (
        ("MPESASTKPUSH", "MPESASTKPUSH"),
    )

    statuses = (
        ("pending", "pending"),
        ("success", "success"),
        ("failure", "failure"),
    )

    trans_id = models.UUIDField(
        default=uuid4,
        primary_key=True,
        editable=False,
    )
    split_id = models.ForeignKey(
        Transactions,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=False,
    )
    trans_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
    )
    originator = models.CharField(
        max_length=50,
        choices=originator_types,
        null=False,
    )
    trans_type = models.CharField(
        max_length=50,
        null=False,
    )
    recipient = models.CharField(
        max_length=255,
        null=False,
    )
    account_reference = models.CharField(
        max_length=255,
        null=False,
    )
    reference_id = models.CharField(
        max_length=350,
        unique=True,
        null=True,
    )
    trans_code = models.CharField(
        max_length=350,
        unique=True,
        null=True,
    )
    status = models.CharField(
        max_length=9,
        choices=statuses,
        default="pending",
        null=False,
    )
    created = models.DateTimeField(auto_now_add=True, null=False)
    updated = models.DateTimeField(auto_now=True, null=False)