import uuid


def new_thread_id() -> str:
    # UUID4 is fine for thread IDs
    return str(uuid.uuid4())
