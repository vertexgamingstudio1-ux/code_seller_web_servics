import unittest
from datetime import datetime, timedelta, timezone

from services.festival_service import apply_campaign
from services.product_service import _catalog_sections, _classify_new_arrivals, _is_new_arrival


class NewArrivalCatalogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)

    def test_inclusive_first_ten_days_boundary(self):
        self.assertTrue(_is_new_arrival(self.now.isoformat(), self.now))
        self.assertTrue(_is_new_arrival((self.now - timedelta(days=9, hours=23)).isoformat(), self.now))
        self.assertFalse(_is_new_arrival((self.now - timedelta(days=10)).isoformat(), self.now))
        self.assertFalse(_is_new_arrival((self.now - timedelta(days=10, seconds=1)).isoformat(), self.now))

    def test_future_or_invalid_publication_dates_are_not_arrivals(self):
        self.assertFalse(_is_new_arrival((self.now + timedelta(seconds=1)).isoformat(), self.now))
        self.assertFalse(_is_new_arrival("not-a-date", self.now))

    def test_catalog_sections_exclude_arrivals_without_losing_products(self):
        source = [
            {"id": "fresh", "created_at": "2026-10-30T12:00:00Z", "published_at": "2026-10-30T12:00:00Z"},
            {"id": "aged", "created_at": "2026-10-19T12:00:00Z", "published_at": "2026-10-19T12:00:00Z"},
        ]
        classified = _classify_new_arrivals(source, self.now, timestamp_field="published_at")
        payload = _catalog_sections(classified)
        self.assertEqual([p["id"] for p in payload["new_arrivals"]], ["fresh"])
        self.assertEqual([p["id"] for p in payload["products"]], ["aged"])
        self.assertEqual({p["id"] for p in payload["new_arrivals"] + payload["products"]}, {"fresh", "aged"})
        self.assertEqual(payload["count"], 2)

    def test_one_canonical_price_breakdown_for_catalog_and_arrivals(self):
        source = {"id": "item", "price": 999, "is_free": False}
        cases = [
            (None, 0, (999, 0, 0, 0)),
            ({"name": "Diwali"}, 0, (699, 30, 0, 300)),
            (None, 5, (949, 0, 5, 50)),
            ({"name": "Diwali"}, 5, (664, 30, 5, 335)),
            (None, 10, (899, 0, 10, 100)),
            ({"name": "Diwali"}, 10, (629, 30, 10, 370)),
        ]
        for campaign, membership, expected in cases:
            with self.subTest(campaign=campaign, membership=membership):
                priced = apply_campaign(source, campaign, membership)
                sections = _catalog_sections([{"id": "item", "is_new_arrival": True, **priced}])
                arrival = sections["new_arrivals"][0]
                # The shared object means both homepage and normal catalog consumers see the same fields.
                self.assertEqual((arrival["price"], arrival["festival_discount_percent"],
                                  arrival["membership_discount_percent"], arrival["discount_amount"]), expected)

    def test_free_or_ineligible_products_keep_existing_no_discount_rules(self):
        free = apply_campaign({"price": 0, "is_free": True}, {"name": "Sale"}, 10)
        self.assertEqual((free["price"], free["festival_discount_percent"], free["membership_discount_percent"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
