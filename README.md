# Eco-Travel Advisor: Sustainable Tourism Conversational Agent 🌍✈️

## Project Overview
The Eco-Travel Advisor is a context-aware conversational agent built using the **Rasa Open Source Framework**. It is designed to assist users in planning sustainable travel itineraries by extracting user preferences (destination, budget, dates, and eco-priority) and applying a multi-criteria weighted scoring algorithm to recommend low-carbon transport and eco-certified accommodations.

## Features
* **Adaptive Dialogue Management:** Utilizes Rasa's `DIETClassifier` and `TEDPolicy` for robust intent classification and conversation flow.
* **Environmental Impact Scoring:** Calculates composite utility scores balancing financial cost and $kg CO_2e$ emissions.
* **Human Handover Protocol:** Automatically detects conversation failure or complex routing requests and packages session metadata for human travel specialists.
* **Dynamic UI Generation:** Outputs structured JSON payloads to drive color-coded React/Webchat frontend cards (Green/Amber/Red emission tiers).

## Repository Structure
```text
├── actions/
│   ├── __init__.py
│   └── actions.py         # Custom Python logic, API integrations, and scoring algorithm
├── data/
│   ├── nlu.yml            # Training examples for intent classification
│   ├── rules.yml          # Fallback and handover rule policies
│   └── stories.yml        # Dialogue path training data
├── models/                # Compiled Rasa models (.tar.gz)
├── config.yml             # NLU pipeline and Core policy configuration
├── domain.yml             # System directory (Intents, Entities, Slots, Responses)
├── endpoints.yml          # Webhook configurations for the action server
└── docker-compose.yml     # Multi-container deployment configuration
