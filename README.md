# 🌿 Eco-Travel Advisor

An AI-powered chatbot that helps users plan carbon-conscious trips by comparing transport options, accommodation, activities, and carbon offset programmes.

Built with **Rasa 3.1.0**, **Python 3.8**, and **Streamlit** as part of an MSc AI assignment at BSBI / UCA.

---

## 🚀 Live Demo

> Deployed on HuggingFace Spaces:  
> **[https://huggingface.co/spaces/YOUR_USERNAME/eco-travel-advisor](https://huggingface.co/spaces/YOUR_USERNAME/eco-travel-advisor)**

---

## 💬 What the Bot Can Do

- Compare transport options by carbon footprint (train vs. flight vs. bus)
- Suggest eco-certified accommodation
- Recommend low-impact activities at the destination
- Calculate and suggest carbon offset programmes
- Generate a full personalised eco-itinerary
- Hand over to a human agent when it cannot help

---

## 🗂️ Project Structure

```
eco-travel-advisor/
├── actions/
│   └── actions.py          # 6 custom Rasa action classes
├── data/
│   ├── nlu.yml             # Intent + entity training examples
│   ├── stories.yml         # Conversation flow stories
│   └── rules.yml           # Deterministic conversation rules
├── models/                 # Trained Rasa model (generated)
├── app.py                  # Streamlit frontend
├── config.yml              # Rasa NLU pipeline + policies
├── domain.yml              # Intents, entities, slots, responses
├── endpoints.yml           # Action server endpoint config
├── credentials.yml         # Channel credentials
├── Dockerfile              # HuggingFace Spaces deployment
├── docker-compose.yml      # Local multi-service deployment
├── requirements.txt        # Python dependencies
├── start.sh                # Container startup script
├── .env                    # API keys (NOT committed — see .gitignore)
└── .gitignore
```

---

## ⚙️ Local Setup (Docker)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/eco-travel-advisor.git
cd eco-travel-advisor

# 2. Copy the env template and fill in your keys
cp .env .env.local
# Edit .env with your Climatiq and Amadeus keys

# 3. Build and run with Docker Compose
docker compose up --build

# 4. Open the frontend
# http://localhost:3000
```

---

## ⚙️ Local Setup (without Docker — Colab / venv)

```bash
# Create venv
python3.8 -m venv rasa_venv
source rasa_venv/bin/activate

# Install dependencies
pip install rasa==3.1.0 streamlit==1.28.0 requests==2.28.0

# Train the model
rasa train

# Terminal 1 — action server
rasa run actions --port 5055

# Terminal 2 — Rasa server
rasa run --enable-api --cors "*" --port 5005 --endpoints endpoints.yml

# Terminal 3 — Streamlit frontend
streamlit run app.py --server.port 3000
```

---

## 🔑 API Keys Required

| API | Purpose | Free Tier |
|-----|---------|-----------|
| [Climatiq](https://www.climatiq.io/) | Carbon footprint calculations | 500 calls/month |
| [Amadeus Sandbox](https://developers.amadeus.com/) | Flights and hotels | Free sandbox |
| [OpenRouteService](https://openrouteservice.org/) | Low-carbon routing | 2,000 req/day |
| [OpenCage](https://opencagedata.com/) | Geocoding / GPS | 2,500 req/day |

Add all keys to your `.env` file. **Never commit `.env` to GitHub.**

---

## 🧪 Testing

```bash
# NLU tests (80/20 split, target F1 ≥ 0.85 per intent)
rasa test nlu --nlu data/nlu.yml --cross-validation

# Core / dialogue tests
rasa test core --stories tests/test_stories.yml

# Unit tests for actions
pytest tests/test_actions.py -v
```

---

## 🏗️ Architecture

```
User (Browser)
    │
    ▼
Streamlit Frontend (port 7860 on HF Spaces / 3000 locally)
    │
    ▼
Rasa Core + NLU (port 5005)
    │  DIETClassifier pipeline
    │  EntitySynonymMapper
    │  RulePolicy + TEDPolicy
    │
    ▼
Python Action Server (port 5055)
    │
    ├── ActionCompareTransport    → Climatiq + OpenRouteService
    ├── ActionCompareAccommodation → Mock eco-hotel database
    ├── ActionCompareActivities   → Mock activities database
    ├── ActionCarbonOffset        → Mock offset programmes
    ├── ActionFinalItinerary      → Assembles full trip plan
    └── ActionHumanHandover       → Escalation packaging
```

---

## 📝 Assignment Notes

- **DistilBERT / HFTransformersNLP** was investigated as an optional NLU enhancement but found incompatible with Rasa 3.1.0's pinned `transformers==4.12.5`. DIETClassifier was retained as the primary pipeline.
- **SpaCy `en_core_web_md`** was also attempted but conflicted with the Rasa 3.1.0 venv on Python 3.8. A `KNOWN_CITIES` dictionary (100+ cities) was implemented as the documented workaround for city name entity extraction.
- **FallbackPolicy and TwoStageFallbackPolicy** are deprecated in Rasa 3.x — fallback handling is implemented via `RulePolicy` and `NLUFallbackClassifier`.

---

## 👩‍💻 Author

Shokoofeh — MSc Artificial Intelligence, BSBI / UCA  
Assignment submission — June 2026
