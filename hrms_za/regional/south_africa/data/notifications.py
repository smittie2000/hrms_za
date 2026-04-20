"""
Notification record definitions for SA leave-automation.

Three records, all triggered on Leave Application events. Recipients use
`receiver_by_document_field` (Frappe resolves the User at send time from
the named field) — works cleanly for the approver + employee cases.
Role-based recipients via `receiver_by_role` also resolve dynamically at
send time, but we don't need one here: the approver field on the
Leave Application already targets the right person.

Message bodies live in sibling `email_bodies/*.html` files and are inlined
by the seeder at install time (HRMS pattern — see the HRMS install.py
handling for its own Leave Notification templates).

IMPORTANT: each Notification record uses a stable name so the seeder can
check `exists(name)` before inserting. If HR later amends the Notification
in the UI, the seeder must not fight the edit — seed-once semantics.
"""

# Each entry: (record_name, body_filename, payload).
NOTIFICATIONS = [
    (
        "SA Leave — Submitted",
        "leave_submitted.html",
        {
            "document_type": "Leave Application",
            "event": "Submit",
            "channel": "Email",
            "enabled": 1,
            "subject": "Leave request from {{ doc.employee_name }} — {{ doc.name }}",
            "recipients": [
                {"receiver_by_document_field": "leave_approver"},
            ],
        },
    ),
    (
        "SA Leave — Approved",
        "leave_approved.html",
        {
            "document_type": "Leave Application",
            "event": "Value Change",
            "value_changed": "status",
            "condition": 'doc.status == "Approved"',
            "channel": "Email",
            "enabled": 1,
            "subject": "Your leave {{ doc.name }} was approved",
            "recipients": [
                {"receiver_by_document_field": "owner"},
            ],
        },
    ),
    (
        "SA Leave — Rejected",
        "leave_rejected.html",
        {
            "document_type": "Leave Application",
            "event": "Value Change",
            "value_changed": "status",
            "condition": 'doc.status == "Rejected"',
            "channel": "Email",
            "enabled": 1,
            "subject": "Your leave {{ doc.name }} was rejected",
            "recipients": [
                {"receiver_by_document_field": "owner"},
            ],
        },
    ),
]
