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

## Product discount calculation

Basic, Plus, and Premium membership product discounts are 0%, 5%, and 10%. A membership discount applies only while the customer's membership is approved and unexpired. Free products are not discounted. During an eligible active festival campaign, paid products receive the festival discount first (currently 30%); the applicable membership percentage is then applied to that reduced price. Each step rounds to the nearest whole price unit using `(amount * (100 - percent) + 50) // 100`. For example, a 999 price becomes 699 after the festival discount, then 664 for an active Plus member. Quotes and order creation use the backend calculation; order creation stores the final unit price and both discount amounts for later order summaries.
