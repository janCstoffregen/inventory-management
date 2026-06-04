import random
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders, restock_orders

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

class RestockRecommendation(BaseModel):
    sku: str
    item_name: str
    category: str
    current_demand: int
    forecasted_demand: int
    demand_gap: int
    recommended_quantity: int
    unit_cost: float
    line_total: float
    trend: str

class RestockRecommendationsResponse(BaseModel):
    budget: float
    total_cost: float
    budget_remaining: float
    item_count: int
    recommendations: List[RestockRecommendation]

class RestockOrderItem(BaseModel):
    sku: str
    item_name: str
    quantity: int
    unit_cost: float
    line_total: float
    lead_time_days: int
    expected_delivery: str

class RestockOrder(BaseModel):
    id: str
    order_number: str
    created_date: str
    budget: float
    total_cost: float
    item_count: int
    max_lead_time_days: int
    latest_expected_delivery: str
    status: str
    items: List[RestockOrderItem]

class CreateRestockOrderItemRequest(BaseModel):
    sku: str
    quantity: int

class CreateRestockOrderRequest(BaseModel):
    budget: float
    items: List[CreateRestockOrderItemRequest]

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

def _fallback_unit_cost(sku: str) -> float:
    """Deterministic per-SKU price in the $20-$200 range for demand items that
    aren't in inventory.json. Most forecast SKUs don't have an inventory match
    in the demo data, so this keeps recommendations meaningful without mutating
    shared JSON files."""
    return round(20 + (abs(hash(sku)) % 18000) / 100, 2)

@app.get("/api/restock-recommendations", response_model=RestockRecommendationsResponse)
def get_restock_recommendations(budget: float = 0):
    """Recommend items to restock within a given budget.

    Algorithm: join demand forecasts with inventory unit_cost by SKU, compute
    demand_gap = forecasted_demand - current_demand, sort by trend (increasing
    first) then by gap descending, then greedy-pack items into the budget.
    """
    # Build SKU -> unit_cost lookup once so we don't repeatedly scan inventory
    unit_cost_by_sku = {item["sku"]: item["unit_cost"] for item in inventory_items}
    inventory_by_sku = {item["sku"]: item for item in inventory_items}

    candidates = []
    for forecast in demand_forecasts:
        sku = forecast["item_sku"]
        gap = max(0, forecast["forecasted_demand"] - forecast["current_demand"])
        if gap == 0:
            continue
        unit_cost = unit_cost_by_sku.get(sku) or _fallback_unit_cost(sku)
        category = inventory_by_sku[sku]["category"] if sku in inventory_by_sku else "Forecasted"
        candidates.append({
            "sku": sku,
            "item_name": forecast["item_name"],
            "category": category,
            "current_demand": forecast["current_demand"],
            "forecasted_demand": forecast["forecasted_demand"],
            "demand_gap": gap,
            "recommended_quantity": gap,
            "unit_cost": unit_cost,
            "line_total": round(gap * unit_cost, 2),
            "trend": forecast.get("trend", "stable"),
        })

    # Increasing trend first, then biggest gaps first
    trend_priority = {"increasing": 0, "stable": 1, "decreasing": 2}
    candidates.sort(key=lambda c: (trend_priority.get(c["trend"], 3), -c["demand_gap"]))

    # Greedy pack — keep evaluating after a skip so smaller items can still fit
    selected = []
    running_total = 0.0
    for candidate in candidates:
        if running_total + candidate["line_total"] <= budget:
            selected.append(candidate)
            running_total += candidate["line_total"]

    return {
        "budget": budget,
        "total_cost": round(running_total, 2),
        "budget_remaining": round(budget - running_total, 2),
        "item_count": len(selected),
        "recommendations": selected,
    }

@app.post("/api/restock-orders", response_model=RestockOrder)
def create_restock_order(request: CreateRestockOrderRequest):
    """Submit a restocking order. Each item gets a random 7-21 day lead time."""
    if not request.items:
        raise HTTPException(status_code=400, detail="Order must include at least one item")

    inventory_by_sku = {item["sku"]: item for item in inventory_items}
    forecast_by_sku = {f["item_sku"]: f for f in demand_forecasts}
    now = datetime.now()

    order_items: List[dict] = []
    total_cost = 0.0
    max_lead_time = 0
    latest_delivery = now

    for item in request.items:
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Quantity for {item.sku} must be positive")

        inv = inventory_by_sku.get(item.sku)
        forecast = forecast_by_sku.get(item.sku)
        if not inv and not forecast:
            raise HTTPException(status_code=400, detail=f"Unknown SKU: {item.sku}")

        # Same fallback as the recommendation endpoint so prices stay consistent
        unit_cost = inv["unit_cost"] if inv else _fallback_unit_cost(item.sku)
        item_name = inv["name"] if inv else forecast["item_name"]

        lead_time = random.randint(7, 21)
        expected_delivery = now + timedelta(days=lead_time)
        line_total = round(item.quantity * unit_cost, 2)

        order_items.append({
            "sku": item.sku,
            "item_name": item_name,
            "quantity": item.quantity,
            "unit_cost": unit_cost,
            "line_total": line_total,
            "lead_time_days": lead_time,
            "expected_delivery": expected_delivery.isoformat(timespec="seconds"),
        })
        total_cost += line_total
        if lead_time > max_lead_time:
            max_lead_time = lead_time
            latest_delivery = expected_delivery

    next_seq = len(restock_orders) + 1
    order = {
        "id": f"RST-{next_seq:04d}",
        "order_number": f"RST-{now.year}-{next_seq:04d}",
        "created_date": now.isoformat(timespec="seconds"),
        "budget": request.budget,
        "total_cost": round(total_cost, 2),
        "item_count": len(order_items),
        "max_lead_time_days": max_lead_time,
        "latest_expected_delivery": latest_delivery.isoformat(timespec="seconds"),
        "status": "Submitted",
        "items": order_items,
    }
    restock_orders.append(order)
    return order

@app.get("/api/restock-orders", response_model=List[RestockOrder])
def get_restock_orders():
    """Return submitted restocking orders, most recent first."""
    return sorted(restock_orders, key=lambda o: o["created_date"], reverse=True)

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
