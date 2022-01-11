import logging
from logging import LogRecord

import prometheus_client


class PrometheusLoggingHandler(logging.Handler):
    LOG_COUNTER = prometheus_client.Counter(
        "python_logging_messages_total",
        "Count of log entries by logger level",
        ["logger", "level"],
    )

    def emit(self, record: LogRecord):
        self.LOG_COUNTER.labels(record.name, record.levelname).inc()


def export_root_logger_stats():
    logger = logging.getLogger()
    logger.addHandler(PrometheusLoggingHandler())
