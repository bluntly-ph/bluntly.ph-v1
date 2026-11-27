"""Aggregate v1 router. Feature modules register their routers here."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    admin_analytics,
    admin_console,
    admin_earnings,
    admin_integrity,
    admin_investigation,
    admin_people,
    admin_prices,
    admin_priority,
    admin_qa_sandbox,
    admin_referral,
    admin_reports,
    admin_sellers,
    admin_users,
    ai,
    auth,
    case_chat,
    comments,
    conversations,
    email,
    global_search,
    internal_cron,
    membership,
    notifications,
    pages,
    payouts,
    postback,
    products,
    qa,
    reading_telemetry,
    reporting,
    requests,
    review_drafts,
    reviews,
    sellers,
    store_changes,
    store_console,
    store_products,
    super_admin,
    support,
    tokens,
    traffic_ingest,
    users,
)

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(products.router)
api_v1_router.include_router(reviews.router)
api_v1_router.include_router(review_drafts.router)
# After reviews: its paths are literal ("/reviews/{id}/comments") rather than a
# prefix, so registration order decides nothing, but reading order should follow
# the resource they hang off.
api_v1_router.include_router(comments.router)
# Page-shaped reads (one call per page; app/api/v1/routes/pages.py).
api_v1_router.include_router(pages.router)
api_v1_router.include_router(pages.search_router)
api_v1_router.include_router(admin_investigation.router)
api_v1_router.include_router(admin_referral.router)
api_v1_router.include_router(admin_earnings.router)
api_v1_router.include_router(admin_analytics.router)
api_v1_router.include_router(admin_people.router)
api_v1_router.include_router(case_chat.router)
api_v1_router.include_router(conversations.router)
api_v1_router.include_router(global_search.router)
api_v1_router.include_router(admin_console.router)
api_v1_router.include_router(admin_users.router)
api_v1_router.include_router(internal_cron.router)
api_v1_router.include_router(traffic_ingest.router)
api_v1_router.include_router(reading_telemetry.router)
api_v1_router.include_router(admin_reports.router)
api_v1_router.include_router(admin_priority.router)
api_v1_router.include_router(admin_qa_sandbox.router)
api_v1_router.include_router(membership.router)
api_v1_router.include_router(ai.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(qa.router)
api_v1_router.include_router(tokens.router)
api_v1_router.include_router(requests.router)
api_v1_router.include_router(payouts.router)
api_v1_router.include_router(postback.router)
api_v1_router.include_router(store_products.router)
api_v1_router.include_router(store_console.router)
api_v1_router.include_router(store_changes.router)
api_v1_router.include_router(sellers.router)
api_v1_router.include_router(admin_sellers.router)
api_v1_router.include_router(admin_prices.router)
api_v1_router.include_router(admin_integrity.router)
api_v1_router.include_router(notifications.router)
api_v1_router.include_router(email.router)
api_v1_router.include_router(reporting.router)
api_v1_router.include_router(support.router)
api_v1_router.include_router(super_admin.router)
