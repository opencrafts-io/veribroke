# Incident Report: Microservice Data Discrepancy (Sherehe vs. Verisafe)

## 1. Incident Overview
| Attribute | Details |
| :--- | :--- |
| **Date** | 2026-03-04 |
| **Time of Incident** | 00:17:22 |
| **Microservices Involved** | Sherehe (Transactions), Verisafe (Payments) |
| **Primary Actors** | Rodney (Developer), Baraka (DevOps) |
| **Issue** | Mismatch in successful ticket counts and total amounts due to incomplete test data cleanup. |

---

## 2. Context
On **2026-03-04 00:17:22**, a developer (**Rodney**) performed production testing using a specific set of UUIDs. Following the test, the DevOps engineer (**Baraka**) was instructed to purge the test data from the production environment. 

The cleanup was successfully executed on the **Verisafe** (referenced as *Veribroke* in logs) microservice. However, the records were **not deleted** from the **Sherehe** microservice, leading to a discrepancy where Sherehe reported higher transaction totals than Verisafe.

---

## 3. Investigation & Step-by-Step SQL Analysis

To identify the cause of the mismatch, the following steps were taken across both databases:

### Step 1: Identifying the Discrepancy (Sherehe)
We first analyzed the transaction distribution in the Sherehe service to find where the numbers were inflated.

```sql
-- Checking the volume of successful tickets vs total amounts
SELECT 
    count(ticket_quantity) AS total_tickets, 
    sum(amount) AS total_amount, 
    amount 
FROM transactions 
WHERE status = 'SUCCESS' 
GROUP BY amount 
ORDER BY total_tickets DESC;
```

### Step 2: Extracting ID Aggregates for Cross-Service Check
To perform a comparison, we used an aggregate function to generate a copyable array of all successful IDs associated with the problematic amount (350).

```sql
-- Aggregating IDs into a copyable list
SELECT '(' || string_agg(id::text, ', ') || ')' AS copy_me
FROM transactions 
WHERE amount = 350 AND status = 'SUCCESS';
```

### Step 3: Verification on Veribroke

Using the list generated in Step 2, we queried the Verisafe database to find which IDs from Sherehe were missing in the payment logs.

```sql
-- Finding "ghost" records that exist in Sherehe but not in Verisafe
SELECT * FROM payments_transactions 
WHERE request_id NOT IN (
    '1c6c...715d', 
    '3897...529f', 
    '[...REDACTED_LIST...]'
) AND trans_amount = 350;
```

### Step 4: Isolation of the Specific Test ID

We specifically targeted the ID used during Rodney's test (1e61...3860) to confirm its existence across services.

```sql
-- Running this on Sherehe (Returned 1 row)
SELECT * FROM transactions WHERE id = '1e61...3860';

-- Running this on Verisafe (Returned 0 rows)
SELECT * FROM payments_transactions WHERE request_id = '1e61...3860';
```

*Finding*: The record existed in Sherehe but was missing from Verisafe, confirming an incomplete manual purge.

## 4. Root Cause

The root cause was Incomplete Distributed Data Deletion. In a microservice architecture where data is replicated or shared across services, manual deletions must be coordinated. The DevOps cleanup script targeted the payment gateway service but neglected the primary transaction ledger.


## 5. Recommendations & Preventative Measures

1. Unified Purge Scripts: Develop an internal tool or script that triggers a "Delete User/Test Data" event via a Message Bus (like RabbitMQ or Kafka) so that all microservices can listen and delete relevant records simultaneously.

2. Test Data Tagging: Implement a is_test or metadata flag on the transactions table. This allows financial reports to exclude test data automatically, even if the record is not immediately deleted.

3. Cross-Service Reconciliation (Recon) Jobs: Run a daily automated reconciliation job that compares transaction counts between Sherehe and Verisafe and flags any discrepancies for manual review.

4. Strict Production Testing Protocols: Discourage manual testing on Production. If necessary, use dedicated "Test User" accounts whose data is automatically ignored by analytics and financial logic.


Report Submitted by by: Erick Muuo
