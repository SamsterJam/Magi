import openai
import json
import time
from utils import log, vlog, vvlog
from assistant_functions import get_weather

class OpenAIClient:
    def __init__(self, config):
        self.api_key = config.openai_api_key
        self.openai_client = openai.OpenAI(api_key=self.api_key)
        self.active_threads_file = "active.treg"
        self.active_assistants_file = "active.areg"

    def create_thread(self):
        try:
            thread_response = self.openai_client.beta.threads.create()
            thread_id = thread_response.id
            vlog(f"Thread created with ID: {thread_id}")
            self._record_active_thread(thread_id)
            return thread_id
        except Exception as e:
            log(f"Failed to create thread: {e}", error=True)

    def delete_thread(self, thread_id):
        try:
            self.openai_client.beta.threads.delete(thread_id)
            log(f"Thread with ID: {thread_id} deleted successfully.")
            self._remove_active_thread(thread_id)
        except Exception as e:
            log(f"Failed to delete thread: {e}", error=True)

    def create_assistant(self, prompt):
        try:
            assistant_response = self.openai_client.beta.assistants.create(
                name="Magi",
                instructions=prompt,
                tools=[{"type": "code_interpreter"}],  # Add other tools/functions as needed
                model="gpt-3.5-turbo-1106"  # Replace with the desired model
            )
            assistant_id = assistant_response.id
            vlog(f"Assistant created with ID: {assistant_id}")
            self._record_active_assistant(assistant_id)
            return assistant_id
        except Exception as e:
            log(f"Failed to create assistant: {e}", error=True)

    def delete_assistant(self, assistant_id):
        try:
            self.openai_client.beta.assistants.delete(assistant_id)
            log(f"Assistant with ID: {assistant_id} deleted successfully.")
            self._remove_active_assistant(assistant_id)
        except Exception as e:
            log(f"Failed to delete assistant: {e}", error=True)

    def process_command_with_assistant(self, thread_id, command, assistant_id):
        try:
            # Add the user's message to the thread
            message = self.openai_client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=command
            )
            vlog(f"Message created with ID: {message.id}")

            # Run the assistant on the thread
            run_response = self.openai_client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )
            vlog(f"Run created with ID: {run_response.id}")

            # Wait for the run to complete and get the assistant's response
            while True:
                run_status = self.openai_client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run_response.id
                )
                if run_status.status == 'completed':
                    break
                elif run_status.status == 'requires_action':
                    # Handle required actions, such as calling external functions
                    self._handle_required_actions(run_status, thread_id, run_response.id)
                # Polling interval
                time.sleep(1)

            # Retrieve the assistant's messages
            messages = self.openai_client.beta.threads.messages.list(
                thread_id=thread_id
            )
            assistant_messages = [msg for msg in messages.data if msg.role == 'assistant']
            assistant_messages.sort(key=lambda msg: msg.created_at)
            if assistant_messages:
                assistant_reply = assistant_messages[-1].content
            else:
                assistant_reply = "I'm sorry, I can't process your request right now."

            log(f"Assistant Response: {assistant_reply}")
            return assistant_reply
        except Exception as e:
            log(f"Error during command processing: {e}", error=True)

    def _record_active_thread(self, thread_id):
        # Append the new thread ID to the active_threads_file
        with open(self.active_threads_file, "a") as file:
            file.write(thread_id + "\n")

    def _remove_active_thread(self, thread_id):
        # Remove the deleted thread ID from the active_threads_file
        with open(self.active_threads_file, "r") as file:
            thread_ids = file.read().splitlines()
        thread_ids.remove(thread_id)
        with open(self.active_threads_file, "w") as file:
            file.write("\n".join(thread_ids) + "\n")

    def _record_active_assistant(self, assistant_id):
        # Append the new assistant ID to the active_assistants_file
        with open(self.active_assistants_file, "a") as file:
            file.write(assistant_id + "\n")

    def _remove_active_assistant(self, assistant_id):
        # Remove the deleted assistant ID from the active_assistants_file
        with open(self.active_assistants_file, "r") as file:
            assistant_ids = file.read().splitlines()
        assistant_ids.remove(assistant_id)
        with open(self.active_assistants_file, "w") as file:
            file.write("\n".join(assistant_ids) + "\n")

    def _handle_required_actions(self, run_status, thread_id, run_id):
        # Handle required actions from the assistant, such as calling external functions
        for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
            if tool_call.function.name == "get_weather":
                arguments = json.loads(tool_call.function.arguments)
                weather_info = get_weather(self.config.openweathermap_api_key, arguments["location"])
                self.openai_client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run_id,
                    tool_outputs=[
                        {
                            "tool_call_id": tool_call.id,
                            "output": weather_info
                        }
                    ]
                )