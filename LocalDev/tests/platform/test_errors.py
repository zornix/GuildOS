from api.platform.errors import public_message


def test_known_fragment_maps_to_its_fixed_text():
    known = {"already checked in": "Already checked in", "not found": "Not found"}
    assert public_message(Exception("event 123 not found in chapter 9"), known, "Not allowed") == "Not found"


def test_unknown_error_gets_the_default_and_no_internal_text():
    out = public_message(Exception('duplicate key value violates unique constraint "x_pkey"'), {}, "Could not save")
    assert out == "Could not save"


def test_every_mapped_error_is_logged_with_its_original_text(caplog):
    known = {"already checked in": "Already checked in"}
    with caplog.at_level("WARNING", logger="api.platform.errors"):
        public_message(Exception("already checked in"), known, "Not allowed")
    assert "already checked in" in caplog.text


def test_reallocate_map_does_not_turn_constraint_text_into_not_found():
    from api.treasury.api.payments import REALLOCATE_KNOWN_ERRORS

    raw = 'insert or update on table "payment_allocations" violates foreign key constraint "payment_allocations_invoice_id_fkey"'
    out = public_message(Exception(raw), REALLOCATE_KNOWN_ERRORS, "Reallocation could not be applied")
    assert out == "Reallocation could not be applied"
    assert public_message(
        Exception("invoice 1f2e not found in chapter 9a"), REALLOCATE_KNOWN_ERRORS, "x"
    ) == "Invoice not found"
