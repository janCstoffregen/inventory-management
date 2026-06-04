"""
Tests for the restocking API endpoints.
"""
import pytest

# The in-memory restock_orders list persists across tests within a session,
# so we autouse a fixture to reset it between tests for isolation.
import mock_data


@pytest.fixture(autouse=True)
def reset_restock_orders():
    mock_data.restock_orders.clear()
    yield
    mock_data.restock_orders.clear()


class TestRestockRecommendations:
    """Test suite for the /api/restock-recommendations endpoint."""

    def test_recommendations_basic_structure(self, client):
        """Recommendations endpoint returns the expected envelope."""
        response = client.get("/api/restock-recommendations?budget=100000")
        assert response.status_code == 200

        data = response.json()
        assert "budget" in data
        assert "total_cost" in data
        assert "budget_remaining" in data
        assert "item_count" in data
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)

    def test_recommendations_respect_budget(self, client):
        """Total cost of recommendations must not exceed the budget."""
        budgets = [5000, 50000, 100000, 500000]
        for budget in budgets:
            response = client.get(f"/api/restock-recommendations?budget={budget}")
            assert response.status_code == 200
            data = response.json()
            assert data["total_cost"] <= budget
            assert data["budget_remaining"] == pytest.approx(
                budget - data["total_cost"], abs=0.01
            )

    def test_recommendations_zero_budget(self, client):
        """A zero budget produces zero recommendations."""
        response = client.get("/api/restock-recommendations?budget=0")
        assert response.status_code == 200
        data = response.json()
        assert data["item_count"] == 0
        assert data["recommendations"] == []
        assert data["total_cost"] == 0

    def test_recommendation_item_structure(self, client):
        """Each recommendation has the required fields with sensible types."""
        response = client.get("/api/restock-recommendations?budget=500000")
        data = response.json()
        assert data["item_count"] > 0, "Demo data should produce at least one recommendation"

        for rec in data["recommendations"]:
            assert "sku" in rec
            assert "item_name" in rec
            assert "category" in rec
            assert "current_demand" in rec
            assert "forecasted_demand" in rec
            assert "demand_gap" in rec
            assert "recommended_quantity" in rec
            assert "unit_cost" in rec
            assert "line_total" in rec
            assert "trend" in rec
            assert rec["demand_gap"] > 0
            assert rec["unit_cost"] > 0
            # line_total should match qty * unit_cost within rounding tolerance
            assert abs(rec["line_total"] - rec["recommended_quantity"] * rec["unit_cost"]) < 0.01

    def test_recommendations_prioritize_increasing_trend(self, client):
        """Increasing-trend items should come before stable/decreasing ones."""
        response = client.get("/api/restock-recommendations?budget=500000")
        recs = response.json()["recommendations"]
        trend_order = {"increasing": 0, "stable": 1, "decreasing": 2}
        seen_max = -1
        for rec in recs:
            rank = trend_order.get(rec["trend"], 3)
            assert rank >= seen_max
            seen_max = rank


class TestRestockOrders:
    """Test suite for the /api/restock-orders endpoints."""

    def test_submit_and_retrieve_order(self, client):
        """POST creates an order and GET returns it."""
        payload = {
            "budget": 50000,
            "items": [
                {"sku": "WDG-001", "quantity": 100},
                {"sku": "PSU-501", "quantity": 5},
            ],
        }
        post_response = client.post("/api/restock-orders", json=payload)
        assert post_response.status_code == 200
        order = post_response.json()

        assert order["id"].startswith("RST-")
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert order["item_count"] == 2
        assert len(order["items"]) == 2

        get_response = client.get("/api/restock-orders")
        assert get_response.status_code == 200
        all_orders = get_response.json()
        assert any(o["id"] == order["id"] for o in all_orders)

    def test_order_items_have_lead_time(self, client):
        """Each line item must include a lead_time_days in the 7-21 range."""
        payload = {
            "budget": 100000,
            "items": [{"sku": "WDG-001", "quantity": 50}],
        }
        order = client.post("/api/restock-orders", json=payload).json()
        for item in order["items"]:
            assert 7 <= item["lead_time_days"] <= 21
            assert "expected_delivery" in item
            assert "T" in item["expected_delivery"]

        assert 7 <= order["max_lead_time_days"] <= 21
        assert order["max_lead_time_days"] == max(i["lead_time_days"] for i in order["items"])

    def test_total_cost_matches_line_totals(self, client):
        """Order total_cost equals the sum of line totals."""
        payload = {
            "budget": 200000,
            "items": [
                {"sku": "WDG-001", "quantity": 100},
                {"sku": "FLT-405", "quantity": 50},
            ],
        }
        order = client.post("/api/restock-orders", json=payload).json()
        line_sum = sum(item["line_total"] for item in order["items"])
        assert abs(order["total_cost"] - line_sum) < 0.01

    def test_submit_rejects_unknown_sku(self, client):
        """Unknown SKUs return 400."""
        payload = {
            "budget": 10000,
            "items": [{"sku": "DOES-NOT-EXIST-999", "quantity": 10}],
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400
        assert "Unknown SKU" in response.json()["detail"]

    def test_submit_rejects_empty_items(self, client):
        """An empty items list returns 400."""
        response = client.post("/api/restock-orders", json={"budget": 10000, "items": []})
        assert response.status_code == 400

    def test_submit_rejects_zero_quantity(self, client):
        """Zero or negative quantity returns 400."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": [{"sku": "WDG-001", "quantity": 0}]},
        )
        assert response.status_code == 400

    def test_orders_returned_most_recent_first(self, client):
        """GET orders are sorted by created_date descending."""
        payload = {"budget": 50000, "items": [{"sku": "WDG-001", "quantity": 10}]}
        client.post("/api/restock-orders", json=payload)
        client.post("/api/restock-orders", json=payload)

        orders = client.get("/api/restock-orders").json()
        assert len(orders) == 2
        assert orders[0]["created_date"] >= orders[1]["created_date"]

    def test_get_orders_empty_initially(self, client):
        """With no submissions, the list is empty (autouse fixture resets state)."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []
