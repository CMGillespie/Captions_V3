# app_v3_mvp.py
# Phase 1: Core Functionality (MVP) - Added RAW PACKET LOGGER
# Connects to Wordly WSS API and prints finalized captions to the console.
# Now also logs all raw incoming JSON data for inspection.

import asyncio
import websockets
import json
import logging
import re
import sys

# --- Configuration ---
WSS_ENDPOINT = "wss://endpoint.wordly.ai/attend"
CONNECTION_CODE = "9005"
ATTRIBUTION_LINE = "<Captioning by Wordly.ai>"

# --- Speaker Indication Flags ---
SHOW_SPEAKER_NAMES = False # Set to True to show "Name: " prefix on speaker change
SHOW_SPEAKER_CHANGES = True # Set to True to show ">> " prefix on speaker change

# --- NEW: Debugging Flag ---
# Set this to True to log the full JSON of every packet received.
LOG_RAW_PACKETS = True 

# Setup basic logging
# We'll set the level to DEBUG if raw logging is on, otherwise INFO
log_level = logging.DEBUG if LOG_RAW_PACKETS else logging.INFO
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

def format_presentation_code(code: str) -> str:
    """
    Formats a raw 8-character code (e.g., abcd1234) into the required
    Wordly format (e.g., ABCD-1234).
    """
    code = code.strip().upper()
    if len(code) == 8 and '-' not in code:
        # Insert the dash
        return f"{code[:4]}-{code[4:]}"
    elif len(code) == 9 and code[4] == '-':
        # Already in the correct format
        return code
    else:
        # Invalid format
        logging.warning(f"Invalid Presentation Code format: '{code}'. Proceeding, but connection may fail.")
        return code

async def listen_to_wordly(pres_code: str, access_key: str, target_lang: str):
    """
    Main function to connect to the WSS endpoint and process messages.
    """

    # 1. Build the 'connect' message payload
    connect_payload = {
        "type": "connect",
        "presentationCode": pres_code,
        "languageCode": target_lang,
        "connectionCode": CONNECTION_CODE
    }

    # Add the accessKey only if one was provided
    if access_key:
        connect_payload["accessKey"] = access_key

    # 2. Define our buffering state variables
    current_phrase_id = None
    current_phrase_text = ""
    finalized_phrases = set()

    # 3. Speaker Tracking State
    last_speaker_id = None
    last_speaker_tag = None 

    logging.info(f"Connecting to {WSS_ENDPOINT}...")

    try:
        # Establish the WebSocket connection
        async with websockets.connect(WSS_ENDPOINT) as websocket:
            logging.info("Connection established. Sending 'connect' request...")

            # Send our 'connect' request
            await websocket.send(json.dumps(connect_payload))

            # --- Handshake and Message Loop ---
            connection_successful = False
            async for message in websocket:
                try:
                    data = json.loads(message)

                    # --- NEW: Raw Packet Logger ---
                    if LOG_RAW_PACKETS:
                        # Log the full packet data at DEBUG level
                        logging.debug(f"RAW_PACKET_DATA: {data}")
                    # --- End Logger ---

                    msg_type = data.get("type")

                    # --- Step A: Handle Connection Status ---
                    if msg_type == "status":
                        if data.get("success", False):
                            connection_successful = True
                            logging.info(f"Successfully connected to {pres_code} for language '{target_lang}'.")

                            # Send the one-time attribution line
                            print(ATTRIBUTION_LINE)
                            sys.stdout.flush() # Ensure it prints immediately
                        else:
                            # Connection failed
                            error_msg = data.get("message", "Unknown connection error.")
                            logging.error(f"Connection failed: {error_msg}")
                            break # Exit the loop and end the script

                    # --- Step B: Handle 'end' Message ---
                    elif msg_type == "end":
                        logging.info("Presentation has ended. Closing connection.")
                        break # Exit the loop

                    # --- Step C: Handle 'phrase' Messages (The Core Logic) ---
                    elif msg_type == "phrase" and connection_successful:

                        # Only process phrases for our target language
                        if data.get("translatedLanguageCode") != target_lang:
                            continue

                        phrase_id = data.get("phraseld")
                        text = data.get("translatedText", "")
                        is_final = data.get("isFinal", False)

                        speaker_id = data.get("speakerld")
                        speaker_tag = data.get("speakerTag")
                        speaker_name = data.get("name")

                        # Ignore any messages for phrases we've already finalized
                        if phrase_id in finalized_phrases:
                            continue

                        # 1. If this is a NEW phrase
                        if phrase_id != current_phrase_id:
                            # Finalize the *previous* phrase by printing it with a newline
                            if current_phrase_id is not None:
                                print(current_phrase_text) 
                                sys.stdout.flush()
                                finalized_phrases.add(current_phrase_id)

                            # --- Check for Speaker Change ---
                            speaker_changed = (speaker_id != last_speaker_id or speaker_tag != last_speaker_tag)
                            prefix = ""
                            if speaker_changed:
                                if SHOW_SPEAKER_CHANGES:
                                    prefix += ">> "
                                if SHOW_SPEAKER_NAMES and speaker_name:
                                    prefix += f"{speaker_name}: "

                            # Update speaker memory *after* the check
                            last_speaker_id = speaker_id
                            last_speaker_tag = speaker_tag
                            # --- END Speaker Change Logic ---

                            # Start the new phrase
                            current_phrase_id = phrase_id
                            current_phrase_text = prefix + text # Apply prefix
                            # Print the start of the new line.
                            print(f"\r{current_phrase_text}", end="")
                            sys.stdout.flush()

                        # 2. If this is an UPDATE to the current phrase
                        elif phrase_id == current_phrase_id:
                            # Use the previously determined prefix (don't add >> or Name: mid-phrase)
                            # Find where the actual text starts (after any prefix)
                            existing_prefix_len = len(current_phrase_text) - len(re.sub(r"^(>> )?([^:]+: )?", "", current_phrase_text))
                            existing_prefix = current_phrase_text[:existing_prefix_len]

                            current_phrase_text = existing_prefix + text # Apply prefix + new text
                            # Overwrite the current line with the updated text
                            print(f"\r{current_phrase_text}", end="")
                            sys.stdout.flush()

                        # 3. If the 'isFinal' flag is set
                        if is_final:
                            # Find where the actual text starts (after any prefix) - handle case where isFinal comes before interim
                            existing_prefix_len = len(current_phrase_text) - len(re.sub(r"^(>> )?([^:]+: )?", "", current_phrase_text))
                            existing_prefix = current_phrase_text[:existing_prefix_len]

                            current_phrase_text = existing_prefix + text # Ensure we have the latest text with prefix

                            # Print the final text *with* a newline
                            print(f"\r{current_phrase_text}")
                            sys.stdout.flush()

                            # Add to our "ignore" list
                            finalized_phrases.add(phrase_id)

                            # Reset the buffer, ready for the next new phrase
                            current_phrase_id = None
                            current_phrase_text = ""
                            # Do NOT reset speaker_id/tag here - compare next phrase to this final one

                    elif msg_type == "error":
                        logging.warning(f"Received error from server: {data.get('message')}")

                    elif connection_successful and msg_type not in ["phrase", "status", "end", "users", "speech", "echo"]:
                        if not LOG_RAW_PACKETS: # Avoid double-logging if raw logging is on
                            logging.debug(f"Received unhandled message type: {msg_type}")

                except json.JSONDecodeError:
                    logging.warning(f"Received non-JSON message: {message}")
                except Exception as e:
                    logging.error(f"Error processing message: {e}\nMessage data: {message}")

    except websockets.exceptions.ConnectionClosedError as e:
        logging.error(f"Connection closed unexpectedly: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        logging.info("Script finished.")

# --- Main execution ---
if __name__ == "__main__":
    print("--- Wordly WSS Caption Bridge (MVP v3) ---")

    raw_code = input("Enter Presentation Code (e.g., abcd1234): ")
    access_key = input("Enter Access Key (or press Enter if none): ")
    target_lang = input("Enter Target Language Code (e.g., en, es): ").lower().strip()

    formatted_code = format_presentation_code(raw_code)

    if not formatted_code or not target_lang:
        print("Presentation Code and Target Language are required. Exiting.")
    else:
        try:
            asyncio.run(listen_to_wordly(formatted_code, access_key.strip(), target_lang))
        except KeyboardInterrupt:
            logging.info("\nScript interrupted by user. Exiting.")