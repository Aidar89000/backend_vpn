from app.crud.spa import _serialize_transaction_status


def test_serialize_transaction_status_maps_success_and_pending():
    assert _serialize_transaction_status("CONFIRMED") == "confirmed"
    assert _serialize_transaction_status("PENDING") == "pending"
    assert _serialize_transaction_status("PROCESSING") == "pending"


def test_serialize_transaction_status_maps_failed_and_cancelled():
    assert _serialize_transaction_status("CANCELED") == "cancelled"
    assert _serialize_transaction_status("CANCELLED") == "cancelled"
    assert _serialize_transaction_status("FAILED") == "failed"
    assert _serialize_transaction_status("EXPIRED") == "failed"
