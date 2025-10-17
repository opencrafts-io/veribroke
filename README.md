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
| `amount` | `number` | ✅ | Amount to be charged. |
| `description` | `string` | ✅ | Payment purpose or reference. |
| `callback_url` | `string` | ✅ | URL to receive payment result notifications. |
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
  "amount": 800,
  "service_name": "SHEREHE",
  "description": "Sherehe Payment - Order #24567",
  "callback_url": "https://api.opencrafts.io/payments/callback",
}
