from logging import getLogger, StreamHandler, Formatter, INFO, DEBUG, FileHandler
import os

def setup_logging() -> None:
    """Configure and return the chat gateway logger"""
    logger = getLogger("ChatGateway")
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return
    
    logger.setLevel(INFO)

    # Create console handler
    console_handler = StreamHandler()
    console_handler.setLevel(DEBUG)

    # Create file handler
    log_file = os.path.join(os.path.dirname(__file__), 'chat_gateway.log')
    file_handler = FileHandler(log_file)
    file_handler.setLevel(INFO)

    # Create formatter and add it to the handlers
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Add the handlers to the logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

def get_logger(name: str = "ChatGateway"):
    """Get a logger instance"""
    return getLogger(name)

# Initialize on module import
setup_logging()