"""
Structured JSON logging so CloudWatch Logs Insights can query/filter by
orderId (the correlation ID) across every Lambda in the event chain.
"""
import json
import logging
import sys

_logger = logging.getLogger("order-processing")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    _logger.addHandler(handler)


def log_event(message: str, **fields):
    record = {"message": message, **fields}
    _logger.info(json.dumps(record))
