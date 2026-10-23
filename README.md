# Code Seller API

## Razorpay test-mode setup

Payment processing is disabled by default. The integration deliberately accepts only Razorpay test keys (`rzp_test_…`) and `RAZORPAY_MODE=test`; live keys and live mode are rejected.

Set these environment variables in the backend host's secret settings. Do not commit secrets or put them in the customer frontend:

```text
PAYMENTS_ENABLED=true
RAZORPAY_MODE=test
RAZORPAY_KEY_ID=rzp_test_…
RAZORPAY_KEY_SECRET=…
RAZORPAY_WEBHOOK_SECRET=…
```

Create a Razorpay webhook pointing to `https://<backend-host>/api/orders/webhook/razorpay` and subscribe to `payment.captured` (and optionally `order.paid`). Use the same webhook secret in the environment. The backend creates Razorpay orders from its own database totals, validates checkout signatures, retrieves the payment from Razorpay and requires a captured status, and independently validates signed webhook amount, currency, and order linkage. Duplicate captures are idempotent. Downloads are served only for paid, processing, or completed orders.

When test configuration is absent, order records can still be created and remain pending, but payment cannot start and no download access is granted. For launch, a separate security review and explicit code change are needed before any live-mode integration; this version does not support it.

## Identifier and history behavior

New customer IDs use `CS-` plus eight unambiguous uppercase letters/digits. New product IDs are six uppercase letters/digits. Existing product IDs, order rows, and historical references are retained. New order items snapshot the server-calculated unit price and quantity.
