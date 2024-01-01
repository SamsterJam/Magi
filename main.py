import argparse
from utils import set_verbosity
from voice_assistant import VoiceAssistant

def parse_arguments():
    parser = argparse.ArgumentParser(description="Voice Assistant")
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('-vv', '--very-verbose', action='store_true', help='Enable very verbose logging')
    return parser.parse_args()

def main():

    # Manage Verbosity
    args = parse_arguments()
    verbosity = 0
    if args.very_verbose:
        verbosity = 1
    elif args.verbose:
        verbosity = 2

    set_verbosity(verbosity)

    assistant = VoiceAssistant()
    assistant.run()

if __name__ == "__main__":
    main()