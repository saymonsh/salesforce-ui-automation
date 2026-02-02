import time

def smart_sleep(duration, check_stop_callback=None, interval=0.5):
    """
    Sleeps for the specified duration in small intervals, checking for a stop signal.

    Args:
        duration (float): Total time to sleep in seconds.
        check_stop_callback (callable, optional): A function that returns True if the sleep should be interrupted.
        interval (float): The interval in seconds to check the stop signal.
    """
    if duration <= 0:
        return

    end_time = time.time() + duration
    while True:
        if check_stop_callback and check_stop_callback():
            return

        remaining = end_time - time.time()
        if remaining <= 0:
            break

        time.sleep(min(remaining, interval))
