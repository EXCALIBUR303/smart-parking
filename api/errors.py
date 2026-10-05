"""Turn PostgreSQL errors into messages an operator can act on.

The database is the real gate: every business rule is a constraint, so the
useful information already exists - it arrives as a SQLSTATE and a constraint
name. This module maps the ones a user can trigger onto plain English.

Users never see raw SQL text. The response carries the friendly message in
`detail` and, when a named rule fired, the rule's name in `rule`, so the UI can
show which constraint did the work. The full database message goes to the
server log.
"""
import logging
import re

import psycopg
from fastapi import HTTPException, status

log = logging.getLogger("smartpark.db")


class DatabaseRuleError(HTTPException):
    """An HTTPException that also names the database rule that refused the request."""

    def __init__(self, status_code: int, detail: str, rule: str | None = None):
        super().__init__(status_code, detail)
        self.rule = rule


# Constraint (or trigger) name -> what the person at the keyboard should read.
CONSTRAINT_MESSAGES = {
    "uq_active_session_slot":
        "That slot already has a vehicle in it. Free it with a gate exit first.",
    # fn_gate_entry raises its own message for this case, naming the bay and
    # facility; this mapping only catches a direct INSERT that bypassed it.
    "uq_active_session_vehicle":
        "This vehicle is already parked and has not exited. Record its exit before a new entry.",
    "fk_session_slot_type_match":
        "That slot is not built for this vehicle type. Choose a slot matching the vehicle.",
    "fk_session_vehicle_type_match":
        "The vehicle type does not match the vehicle on file. Check the registration.",
    "ck_session_exit_after_entry":
        "Exit time must be later than entry time.",
    "ck_reservation_window":
        "The reservation must end after it starts.",
    "ex_reservation_no_overlap":
        "That slot is already reserved for an overlapping period. Pick another slot or time.",
    "fk_reservation_vehicle_owner":
        "That vehicle belongs to a different customer.",
    "fk_reservation_slot_type_match":
        "That bay is not built for this vehicle type. Pick a bay that matches the vehicle.",
    "fk_reservation_vehicle_type_match":
        "The vehicle type does not match the vehicle on file.",
    "trg_reservation_prepare":
        "That bay is out of service and cannot be reserved.",
    "ex_pass_no_overlap":
        "This vehicle already holds a pass covering those dates at this facility.",
    "fk_pass_vehicle_owner":
        "That vehicle belongs to a different customer.",
    "ex_tariff_no_overlap":
        "A tariff is already in force for this facility and vehicle type. Close it before opening a new one.",
    "ck_bill_base_non_negative":
        "A bill amount cannot be negative.",
    "ck_payment_amount_positive":
        "A payment must be greater than zero.",
    "ck_vehicle_plate_shape":
        "That does not look like a valid registration number. Use the format TS09AB1234.",
    "vehicle_plate_number_key":
        "A vehicle with that registration number is already on file.",
    "customer_phone_key":
        "A customer with that phone number already exists.",
    "customer_email_key":
        "A customer with that email address already exists.",
    "ck_customer_phone_shape":
        "Enter a 10 digit phone number with no spaces or country code.",
    "ck_customer_email_shape":
        "That does not look like a valid email address.",
    "ck_customer_name_not_blank":
        "The customer's name cannot be blank.",
    "app_user_email_key":
        "An account with that email address already exists.",
    "ck_app_user_operator_has_facility":
        "An operator must be assigned to exactly one facility.",
    "ck_tariff_cap_sane":
        "The daily cap cannot be lower than the first hour rate.",
    "ck_tariff_rates_non_negative":
        "Tariff rates cannot be negative.",
    "uq_slot_zone_code":
        "A slot with that code already exists in this zone.",
    "ck_slot_note_only_when_out":
        "A service note can only describe a bay that is out of service.",
}

# Rules whose trigger writes a message for a human, including figures a fixed
# string could not know (the balance still owed). Their own wording is shown.
OWN_WORDING = {"trg_payment_within_balance"}

# What a referencing table means to a person, for "cannot delete" messages.
REFERENCED_BY = {
    "vehicle": "vehicles on file",
    "reservation": "reservations on record",
    "parking_pass": "passes on record",
    "parking_session": "parking history",
    "bill": "bills on record",
    "payment": "payments on record",
    "violation": "violations on record",
}

_STILL_REFERENCED = re.compile(r'violates foreign key constraint "[^"]+" on table "(\w+)"')


def _first_line(exc: Exception) -> str:
    """First line of a Postgres error, without the CONTEXT/PL-pgSQL trace."""
    text = str(exc).strip()
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("CONTEXT:", "DETAIL:", "HINT:", "QUERY:")):
            return line
    return "The database rejected that request."


def as_http(exc: Exception) -> HTTPException:
    """Map a database exception onto an HTTPException with a usable message."""
    if isinstance(exc, HTTPException):
        return exc
    if not isinstance(exc, psycopg.Error):
        raise exc

    diag = getattr(exc, "diag", None)
    rule = getattr(diag, "constraint_name", None)
    raw = _first_line(exc)

    # Messages the project's own PL/pgSQL wrote for a human.
    if isinstance(exc, psycopg.errors.RaiseException):
        return DatabaseRuleError(status.HTTP_400_BAD_REQUEST, raw, rule)
    if isinstance(exc, psycopg.errors.ObjectInUse):
        return DatabaseRuleError(status.HTTP_409_CONFLICT, raw, rule)
    if isinstance(exc, psycopg.errors.InsufficientResources):
        return DatabaseRuleError(status.HTTP_409_CONFLICT, raw, rule)
    if isinstance(exc, psycopg.errors.NoDataFound):
        return DatabaseRuleError(status.HTTP_404_NOT_FOUND, raw, rule)

    if isinstance(exc, psycopg.errors.InsufficientPrivilege):
        # A GRANT refusal reads "permission denied for ..."; anything else was
        # raised deliberately by one of our functions with its own wording.
        message = ("You do not have permission to do that."
                   if raw.lower().startswith("permission denied") else raw)
        return DatabaseRuleError(status.HTTP_403_FORBIDDEN, message, rule)

    if isinstance(exc, psycopg.errors.ForeignKeyViolation):
        match = _STILL_REFERENCED.search(raw)
        if match:
            what = REFERENCED_BY.get(match.group(1), "related records")
            return DatabaseRuleError(
                status.HTTP_409_CONFLICT,
                f"This record still has {what}, so it cannot be deleted.", rule)

    if rule in OWN_WORDING:
        return DatabaseRuleError(status.HTTP_409_CONFLICT, raw, rule)

    if rule and rule in CONSTRAINT_MESSAGES:
        return DatabaseRuleError(status.HTTP_409_CONFLICT, CONSTRAINT_MESSAGES[rule], rule)

    if isinstance(exc, psycopg.errors.IntegrityError):
        log.warning("Unmapped integrity error: %s", raw)
        return DatabaseRuleError(status.HTTP_409_CONFLICT,
                                 "That change conflicts with records already on file.", rule)

    if isinstance(exc, psycopg.errors.DataError):
        log.warning("Rejected input: %s", raw)
        return DatabaseRuleError(status.HTTP_400_BAD_REQUEST,
                                 "Some of the values sent are not valid.", rule)

    log.error("Database error: %s", raw)
    return DatabaseRuleError(status.HTTP_500_INTERNAL_SERVER_ERROR,
                             "The database could not complete that request. Please try again.")
