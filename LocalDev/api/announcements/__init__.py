"""Announcements — chapter-wide messaging through the shared message outbox.

Delivery providers stay behind the outbox (0070 pattern); nothing leaves the
process in V1 (MESSAGE_DELIVERY_MODE=dry_run).
"""
