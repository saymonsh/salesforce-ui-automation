import time
from src.core.exceptions import StopException

def verify_running(check_stop_callback):
    """
    Checks if the stop signal is set and raises StopException if it is.
    
    Args:
        check_stop_callback (callable): A function that returns True if stopped.
    
    Raises:
        StopException: If check_stop_callback returns True.
    """
    if check_stop_callback and check_stop_callback():
        raise StopException("Execution stopped by user")

def smart_sleep(duration, check_stop_callback=None, interval=0.5):
    """
    Sleeps for the specified duration in small intervals, checking for a stop signal.

    Args:
        duration (float): Total time to sleep in seconds.
        check_stop_callback (callable, optional): A function that returns True if the sleep should be interrupted.
        interval (float): The interval in seconds to check the stop signal.
        
    Raises:
        StopException: If execution is stopped during sleep.
    """
    # Initial check before sleeping
    verify_running(check_stop_callback)
    
    if duration <= 0:
        return

    end_time = time.time() + duration
    while True:
        verify_running(check_stop_callback)

        remaining = end_time - time.time()
        if remaining <= 0:
            break

        time.sleep(min(remaining, interval))

