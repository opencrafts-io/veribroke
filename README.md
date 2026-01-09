# 💸 Veribroke Payment Service

The **Veribroke Payment Service** is responsible for managing all **payment operations** within the OpenCrafts ecosystem.  
It acts as a **central payment hub**, processing and coordinating various payment methods through **RabbitMQ** for reliable, asynchronous communication between microservices.

---

## 🧩 System Overview

Veribroke is designed around a **queue-based architecture** using **RabbitMQ**.  
Each payment method (e.g., M-Pesa STK, Card Payments, Airtel Money) is mapped to a specific **routing key** and **queue** under a common exchange.

Other microservices publish payment requests to these queues, and Veribroke processes them asynchronously, then sends payment status updates or notifications to the respective services.

---

## 🕸️ Messaging Overview

| Component | Description |
|------------|-------------|
| **Exchange Name** | `io.opencrafts.veribroke` |
| **Exchange Type** | `direct` |
| **Content Type** | `application/json` |
| **Purpose** | Serves as the message router for all payment-related requests across the OpenCrafts ecosystem. |

---

## 📦 Queues and Routing Keys

| Payment Method | Queue Name | Routing Key | Description |
|----------------|-------------|--------------|-------------|
| **M-Pesa STK Push** | `veribroke.mpesa-stk` | `veribroke.mpesa-stk` | Handles M-Pesa STK push requests — triggers user payment prompts. |
| **Card Payments** *(future)* | `veribroke.card-payment` | `veribroke.card-payment` | Handles card-based transactions via supported card APIs. |
| **Airtel Money** *(future)* | `veribroke.airtel-money` | `veribroke.airtel-money` | Handles Airtel Money transactions and confirmations. |
| **Bank Transfers** *(future)* | `veribroke.bank-transfer` | `veribroke.bank-transfer` | Handles direct bank payment integrations. |

> 💡 **Note:**  
> Each queue listens to messages published to the exchange `io.opencrafts.veribroke` using its respective routing key.

---

## ⚙️ Message Structure

All messages must be published as **JSON objects** with the content type `application/json`.

### Common Fields

| Field | Type | Required | Description |
|--------|------|-----------|-------------|
| `request_id` | `string` | ✅ | Unique identifier for the request. |
| `trans_amount` | `number` | ✅ | Amount to be charged. |
| `trans_desc` | `string` | ✅ | Payment purpose or reference. |
| `reply_to` | `string` | ✅ | routing key to receive payment result notifications. |
| `target_user_id` | `string` | ✅ | Verisafe User Responsible For This Intiation |
| `service_name` | `string` | ✅ | The Service Sending The Request |
| `metadata` | `object` | ❌ | Optional custom fields for internal use. (Shall be stated) |

---

## 📲 Triggering an M-Pesa STK Push

To initiate an M-Pesa STK Push, publish a message to the exchange `io.opencrafts.veribroke` using the routing key `veribroke.mpesa-stk`.

### Exchange & Queue

| Property | Value |
|-----------|--------|
| **Exchange Name** | `io.opencrafts.veribroke` |
| **Routing Key** | `veribroke.mpesa-stk` |
| **Content Type** | `application/json` |

### Example Request Message

```json
{
  "request_id": "OR648724567",
  "target_user_id": "f71a-2b57-4678-8776-9708c92d8dd1",
  "phone_number": "2547xxxxx",
  "trans_amount": 800,
  "service_name": "SHEREHE",
  "trans_desc": "Sherehe Payment - Order #24567",
  "reply_to": "sherehe.opencrafts",
}
```

# Notification Messaging (Topic Exchange)

## Overview

This service uses a **topic exchange** to publish notifications to other services.

Any service that wants to receive notifications must:
- Create its own queue
- Bind the queue to the topic exchange using a routing key

This allows services to subscribe only to the notifications they care about while remaining loosely coupled.

---

## Exchange Configuration

- **Exchange Type:** topic
- **Purpose:** Publish notifications to subscribing services
- **Exchange Management:** The exchange is created and managed by this service

> Consumers should **not** create the exchange. They are only responsible for creating and managing their own queues.

---

## Subscribing to Notifications

To receive notifications from this service:

1. Create a queue in your service
2. Bind the queue to the topic exchange
3. Use a routing key of your choice

### Example Binding
Exchange: notifications.topic
Queue: my-service.notifications
Routing Key: my-service.events.#

Once bound, your queue will receive all messages whose routing keys match your binding pattern.

---

## Sending Requests & Receiving Notifications

When sending a request to this service to queues with notifications enabled and expecting notifications or responses, you **must include a `reply_to` field** in the request body.

### `reply_to`

- The value of `reply_to` **must be the routing key** used to bind your queue to the topic exchange
- This value tells the service where to publish notifications or responses

If `reply_to` is not provided, the service will not know where to route notifications. and the request will be ignored and not be processed

## Notification Publishing Behavior

Notifications are published to the topic exchange

The routing key used is the value provided in reply_to

All queues with matching bindings will receive the notification

## Routing Key Best Practices

- Use a unique routing key namespace per service

- Avoid sharing queues across multiple services

- Look at rabbit's documentation on topic exchange for more info

## Notes

Ensure your queue is bound to the exchange before sending requests

Always provide a valid reply_to routing key when expecting notifications

# Split Transactions

## Overview

Split Transactions allow a single transaction to be **split and partially routed to a third party**.

This feature is **optional** and is enabled by including a `split_data` JSON object inside the request `metadata`.

- If `split_data` **is present**, the service processes the transaction as a split transaction
- If `split_data` **is absent**, the service assumes a normal (non-split) transaction

> The meaning of split transactions is internal and assumed to be understood by the team.

---

## Enabling Split Transactions

To enable split transactions, include a `split_data` object in the request metadata.

### High-Level Structure

```json
{
  "split_data": {
    "originator": "MPESA",
    "extras": {
      ...
    }
  }
}
```

### Supported Originators
MPESA

Currently, MPESA is the only supported originator.

##### Additional originators may be supported in the future.

### extras Object (MPESA)

The structure of extras depends on the selected originator.

For MPESA, the following format is required:

```json
{
  "type": "pochi",
  "amount": 500,
  "recipient": "254712345678",
  "account-reference": null,
  "occassion": "Commission payout"
}
```

| Field | Type | Required | Description |
|--------|------|-----------|-------------|
| `type` | `string` | ✅ | Type of MPESA transaction. |
| `amount` | `number` | ✅ | Amount to split and send to the third party. |
| `recipient` | `string` | ✅ | Destination of the split amount |
| `account_reference` | `string` | ❌ | Required when type is paybill, otherwise can be null. |
| `occassion` | `string` | ✅ | Description of the split transaction |

### Supported MPESA Types

| Field | Recipient Value |
|--------|------------------------------|
| `pochi` | `Phone Number` |
| `personal` | `Phone Number` | 
| `paybill` | `Short code` |
| `till` | `Short code` |

### Recipient Rules

- If type is pochi or personal:

  - recipient must be a phone number

- If type is paybill or till:

  - recipient must be a short code

- If type is paybill:

  - account-reference must be provided (cannot be omitted, but may be null if applicable)

### Example Metadata with Split Transaction
```json
{
  "metadata": {
    "split_data": {
      "originator": "MPESA",
      "extras": {
        "type": "paybill",
        "amount": 1000,
        "recipient": "123456",
        "account-reference": "INV-2026-001",
        "occassion": "Service fee split"
      }
    }
  }
}
```

### Notes

- If split_data is missing, the transaction will be processed normally

- Invalid or incomplete split_data may result in request rejection

- Ensure all required fields are provided based on the selected type