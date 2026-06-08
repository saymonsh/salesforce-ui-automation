import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException
from src.core.exceptions import StopRequestedException

# Bidirectional-text isolates. U+2066 (LEFT-TO-RIGHT ISOLATE) … U+2069 (POP
# DIRECTIONAL ISOLATE) wrap an LTR run (a number, date, or ID) so it renders
# left-to-right *and* is treated as a single neutral object by the surrounding
# Hebrew RTL line — which keeps adjacent neutrals (parentheses, ":", "-") in
# place. NOTE: these are isolates, not the legacy embeddings (LRE/PDF,
# U+202A/U+202C), which do *not* insulate neighbouring neutrals and garble e.g.
# "(1 מתוך 2)" into "1) … 2)".
_LRI = "⁦"  # LEFT-TO-RIGHT ISOLATE
_PDI = "⁩"  # POP DIRECTIONAL ISOLATE


def ltr_isolate(value) -> str:
    """Wrap a number/date/ID in an LTR isolate for correct RTL rendering.

    Use this anywhere a Hebrew (RTL) string interpolates a number, date, count,
    or ID — never f-string a raw number into Hebrew text.
    """
    return f"{_LRI}{value}{_PDI}"


def verify_running(check_stop_callback):
    """
    Checks if the stop signal is set and raises StopRequestedException if it is.
    
    Args:
        check_stop_callback (callable): A function that returns True if stopped.
    
    Raises:
        StopRequestedException: If check_stop_callback returns True.
    """
    if check_stop_callback and check_stop_callback():
        raise StopRequestedException("Execution stopped by user")

def smart_sleep(duration, check_stop_callback=None, interval=0.5):
    """
    Sleeps for the specified duration in small intervals, checking for a stop signal.

    Args:
        duration (float): Total time to sleep in seconds.
        check_stop_callback (callable, optional): A function that returns True if the sleep should be interrupted.
        interval (float): The interval in seconds to check the stop signal.
        
    Raises:
        StopRequestedException: If execution is stopped during sleep.
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

def interruptible_wait(driver, condition, timeout=30, check_stop_func=None, poll_frequency=0.5):
    """
    Waits for a condition to be true while periodically checking for a stop signal.
    This effectively replaces long-running blocking WebDriverWait calls with micro-polling.
    """
    verify_running(check_stop_func)
    
    driver.implicitly_wait(0)
    
    end_time = time.time() + timeout
    
    while True:
        verify_running(check_stop_func)
        
        remaining = end_time - time.time()
        if remaining <= 0:
            raise TimeoutException(f"Timed out after {timeout} seconds")
            
        try:
            return WebDriverWait(driver, poll_frequency).until(condition)
        except TimeoutException:
            pass

def interruptible_find_element(driver, by, value, timeout=30, check_stop_func=None):
    """
    A convenience wrapper to find an element using interruptible micro-polling.
    Replaces blocking `driver.find_element` calls.
    """
    return interruptible_wait(
        driver,
        ec.presence_of_element_located((by, value)),
        timeout=timeout,
        check_stop_func=check_stop_func
    )

