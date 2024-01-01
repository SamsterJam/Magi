import datetime
from colorama import Fore, Back, Style, init

# Initialize colorama
init(autoreset=True)

# Verbosity
verbosity=0

def set_verbosity(level):
    global verbosity_level
    verbosity_level = level


def log(message, error=False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = Fore.RED if error else Fore.RESET
    print(f"{color}[{timestamp}] {message}{Style.RESET_ALL}")

def vlog(message):
    if verbosity_level >= 1:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{Fore.LIGHTBLACK_EX}[{timestamp}] {message}{Style.RESET_ALL}")

def vvlog(message):
    if verbosity_level >= 2:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{Back.LIGHTBLACK_EX}[{timestamp}] {message}{Style.RESET_ALL}")