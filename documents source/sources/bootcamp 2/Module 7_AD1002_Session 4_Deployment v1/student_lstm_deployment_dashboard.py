import requests
import pandas as pd
import streamlit as st


API_URL = "http://127.0.0.1:8001"

st.set_page_config(page_title="LSTM-RSRP Deployment", page_icon="📡", layout="wide")
st.title("LSTM-RSRP GeoAI Deployment Dashboard")
st.caption("10 time-ordered observations × 8 features → predicted next RSRP")


def api_get(path):
    response = requests.get(f"{API_URL}{path}", timeout=15)
    response.raise_for_status()
    return response.json()


def api_post(path, payload):
    response = requests.post(f"{API_URL}{path}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


try:
    health = api_get("/health")
    version = api_get("/version")
    st.success(f"API online | Model: {version['model_version']}")
except requests.RequestException as error:
    st.error("API is not available. Run the API cell in the Session 4 notebook first.")
    st.code(str(error))
    st.stop()

with st.expander("Model information", expanded=True):
    col1, col2, col3 = st.columns(3)
    col1.metric("API status", health["status"])
    col2.metric("Lookback", version["lookback"])
    col3.metric("Input features", len(version["features"]))
    st.write("Feature order:", version["features"])

try:
    payload = api_get("/sample-request")
except requests.RequestException as error:
    st.error(f"Could not load sample data: {error}")
    st.stop()

observations = pd.DataFrame(payload["observations"])
st.subheader("Latest 10 network observations")
st.dataframe(observations, use_container_width=True, hide_index=True)

with st.expander("JSON request sent to the API"):
    st.json(payload)

if st.button("Run prediction", type="primary", use_container_width=True):
    try:
        result = api_post("/predict-rsrp", payload)
    except requests.RequestException as error:
        st.error(f"Prediction failed: {error}")
        st.stop()

    st.subheader("Prediction result")
    col1, col2, col3 = st.columns(3)
    col1.metric("Predicted next RSRP", f"{result['predicted_rsrp_dbm']:.2f} dBm")
    col2.metric("Signal class", result["signal_class"])
    col3.metric("Response time", f"{result['response_time_ms']:.2f} ms")

    st.map(
        pd.DataFrame(
            {"lat": [result["latitude"]], "lon": [result["longitude"]]}
        ),
        latitude="lat",
        longitude="lon",
        zoom=15,
    )

    latest_level = float(observations.iloc[-1]["Level"])
    comparison = pd.DataFrame(
        {
            "RSRP": [latest_level, result["predicted_rsrp_dbm"]]
        },
        index=["Latest input Level", "Predicted next Level"],
    )
    st.subheader("Latest input versus next prediction")
    st.bar_chart(comparison)

    with st.expander("Complete API response"):
        st.json(result)
