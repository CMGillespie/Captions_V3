# PROJECT BRIEF: Caption Encoder Bridge (v3.0 - WSS Pivot)

## 1. Project Goal ("What it does")

To build a robust, low-latency, and multi-channel application that connects directly to Wordly's **WSS (WebSocket) API**. The application will ingest real-time `phrase` data, buffer it correctly, and transmit the finalized text to professional broadcast hardware encoders via a standard TCP socket.

This v3 application is a replacement for the v2 (Captions API) app, with a primary performance target of **sub-5-second** end-to-end latency.

## 2. Background & Rationale ("Why we're doing it")

The v2 application, which relies on the Captions API (webhook) and Firestore, successfully proved the "bridge" concept. However, our joint testing definitively concluded:

* **Non-Viable Latency:** The v2 architecture has an unavoidable, stacked latency of **$\approx$17 seconds** ($\approx$11s from the Captions API + $\approx$6s from our required buffer).
* **Broadcast Unacceptable:** This level of delay is not viable for a real-time broadcast environment.
* **A Clear Solution:** Identical tests against the **Wordly WSS API** showed it delivers the same data with a total latency of **$\approx$2-3 seconds**.

**The Decision:** To meet the project's performance goals, we are pivoting the architecture. This v3 project will build a new application *natively* on the low-latency WSS API. The v2 application will be archived.

## 3. Core Architecture ("How it does it")

This architecture removes the Cloud Run webhook and Firestore *listener* from the real-time path. The application will be a single, persistent Python script that manages all connections directly.

### New Data Flow:

1.  **Primary (Real-Time):**
    `Wordly (WSS API)` $\rightarrow$ `v3 App (app_wss.py)` $\rightarrow$ `Broadcast Encoder (TCP)`
2.  **Secondary (Logging):**
    `v3 App (app_wss.py)` $\rightarrow$ `Google Firestore (Async Write)`

### Key Components:

* **Main Application (`app_wss.py`):** A single, stateful Python application. It will run:
    1.  A **Flask/Socket.IO Server** (in the main thread) to serve the web UI for management.
    2.  A **WSS Client Manager** (in a background thread) to handle all WSS connections.
* **WSS Client (New):** A persistent client that connects to `wss://endpoint.wordly.ai/attend` using the `presentationCode` and `accessKey`. It will use `asyncio` and the `websockets` library to listen for `phrase` messages.
* **Buffering Logic (New):** The v2 "Buffer and Release" logic will be replaced. The new logic will use the `phraseId` and `isFinal` flags from the WSS payload. It will buffer interim text and only release the *final* text for a given `phraseId`.
* **Firestore Logger (New):** A new, asynchronous module. When the WSS Client receives a `phrase` message with `isFinal: true`, it will pass this final, complete caption to the logger, which will write it to Firestore. This achieves the v2 goal of logging a transcript for summaries *without* adding any latency to the real-time encoder stream.

## 4. Feature Roadmap (Phased Plan)

We will build v3 in distinct, testable phases, following our "no premature refactoring" protocol.

* **Phase 1: Core Functionality (MVP)**
    * Goal: Create a simple, command-line script that proves the core WSS connection and new buffering logic.
    * Tasks:
        1.  Build a WSS client that connects to a *single* hard-coded Wordly session.
        2.  Listen for `phrase` messages for a *single* hard-coded language.
        3.  Implement the new "Buffer and Release" logic based on `phraseId` and `isFinal`.
        4.  Print the finalized text to the console.
    * *Deliverable: A script that gives us a 2-3s latency text stream in the terminal.*

* **Phase 2: Encoder Integration**
    * Goal: Send the finalized text from Phase 1 to a real encoder.
    * Tasks:
        1.  Integrate the TCP `EncoderProfile` classes from v2.
        2.  Pipe the finalized text from the WSS buffer to a single hard-coded encoder instance.
    * *Deliverable: Captions appearing on the broadcast encoder with < 5s latency.*

* **Phase 3: UI & Multi-Channel Management**
    * Goal: Re-introduce the v2 web UI to manage multiple, dynamic channels.
    * Tasks:
        1.  Integrate the Flask/Socket.IO server and HTML/JS frontend from v2.
        2.  Modify the UI to create/manage "WSS Instances" (which will replace the v2 "Firestore Instances").
        3.  The "Add Channel" button will now spawn a new WSS client listener (in a thread) for that specific language.
    * *Deliverable: The full v2 UI experience, but now driving the low-latency WSS app.*

* **Phase 4: Asynchronous Logging & v2 Parity**
    * Goal: Achieve all secondary goals from v2.
    * Tasks:
        1.  Build the `FirestoreLogger` module.
        2.  In the WSS client, when `isFinal: true` is received, send the data to the logger (which writes to Firestore asynchronously).
        3.  Re-implement the one-time `<Live Captions by Wordly.AI>` attribution line.
        4.  Build robust error handling and auto-reconnect logic for the WSS client.
    * *Deliverable: A production-ready, low-latency, multi-channel bridge app with full transcript logging.*

## 5. Key Dependencies

* **Python 3.10+**
* **Libraries:** `websockets`, `asyncio`, `Flask`, `Flask-SocketIO`, `google-cloud-firestore`
* **Services:** Wordly WSS API, Google Firestore (for logging only).