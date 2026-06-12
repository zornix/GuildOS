"""Attendance — check-ins, excuses, check-in links/pages, and sessions.

Domain package boundary: legacy handlers (attendance/excuses/checkin_links/
checkin_page flat modules) are delegated to unchanged; attendance_sessions is
the new surface layered over the existing tables. See CONFORM_TODO.md.
"""
