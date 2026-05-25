from logging import Logger, getLogger


def get_logger(name: str = "ChatGateway") -> Logger:
    """Return a named logger.

    Logging is configured centrally in ``src/main.py`` via
    ``logging.basicConfig``; this module deliberately attaches no
    handlers so loggers propagate to the root config exactly once. The
    previous setup attached handlers directly to ``ChatGateway`` AND
    let propagation deliver the same record to the root handler, which
    duplicated every ``ChatGateway`` line in the console.
    """
    return getLogger(name)
