from contextvars import ContextVar

delivery_context = ContextVar('delivery_context', default=None)
