"""Turn PostgreSQL integrity errors into messages an operator can act on.

The database is the real gate: every business rule is a constraint, so the
useful error text already exists - it just arrives as a SQLSTATE and a
constraint name. This module maps the ones a user can actually trigger onto
plain English, and passes anything unrecognised through as a 400 with the
database's own message rather than swallowing it into a generic 500.
"""
import psycopg
from fastapi import HTTPException, status

# Constraint name -> what the person at the keyboard should read.
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
    "ex_pass_no_overlap":
        "This vehicle already holds a pass covering those dates at this facility.",
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
    "ck_customer_phone_shape":
        "Enter a 10 digit phone number with no spaces or country code.",
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
}


def as_http(exc: Exception) -> HTTPException:
    """Map a database exception onto an HTTPException with a usable message."""
    if isinstance(exc, psycopg.errors.RaiseException):
        # RAISE EXCEPTION from one of the fn_gate_* functions. Its message is
        # already written for a human.
        return HTTPException(status.HTTP_400_BAD_REQUEST, _clean(exc))

    if isinstance(exc, psycopg.errors.InsufficientResources):
        return HTTPException(status.HTTP_409_CONFLICT, _clean(exc))

    if isinstance(exc, psycopg.errors.NoDataFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, _clean(exc))

    if isinstance(exc, psycopg.errors.InsufficientPrivilege):
        return HTTPException(status.HTTP_403_FORBIDDEN,
                             "You do not have permission to do that.")

    if isinstance(exc, psycopg.Error):
        name = getattr(getattr(exc, "diag", None), "constraint_name", None)
        if name and name in CONSTRAINT_MESSAGES:
            return HTTPException(status.HTTP_409_CONFLICT, CONSTRAINT_MESSAGES[name])
        if isinstance(exc, psycopg.errors.IntegrityError):
            # Unmapped but genuinely a data problem - show the database's own
            # message rather than pretending the server broke.
            return HTTPException(status.HTTP_409_CONFLICT, _clean(exc))
        return HTTPException(status.HTTP_400_BAD_REQUEST, _clean(exc))

    raise exc


def _clean(exc: Exception) -> str:
    """First line of a Postgres error, without the CONTEXT/PL-pgSQL trace."""
    text = str(exc).strip()
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("CONTEXT:", "DETAIL:", "HINT:", "QUERY:")):
            return line
    return text.splitlines()[0] if text else "The database rejected that request."
