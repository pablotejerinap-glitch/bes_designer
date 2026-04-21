# BES Designer

Automated design tool for Electric Submersible Pump (ESP/BES) systems, following
the methodology of Kermit Brown's *The Technology of Artificial Lift Methods*,
Volume 2b, Chapter 4.5.

Given well, reservoir, fluid, and completion data, the tool produces a complete
ESP design: pump selection and stage count, motor sizing, cable selection,
surface voltage, and transformer rating — for equipment from Reda, Centrilift,
ODI, and Kobe catalogs.

## Project structure

```
bes_designer/
├── app.py               # Application entry point (Streamlit)
├── requirements.txt
├── core/
│   └── models.py        # All data models and validation
├── catalogs/            # Manufacturer pump/motor/cable catalog data
├── recommender/         # IPR, TDH, and equipment selection logic
├── reports/             # PDF and Excel report generation
├── ui/                  # Streamlit UI components
├── tests/               # pytest test suite
└── data/                # Static reference data files
```

## Installation

```bash
# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

## Running the app

```bash
streamlit run app.py
```

## Running the tests

```bash
pytest tests/ -v
```
