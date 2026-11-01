import os

from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(__file__), "..", "app", "streamlit_app.py")


def test_app_runs_with_fictional_sample():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(m.value for m in at.markdown)
    assert "Decision support, not proof of field savings" in " ".join(i.value for i in at.info)
    assert "FICTIONAL" in " ".join(w.value for w in at.warning)
    assert "OPTIMAL" in " ".join(s.value for s in at.success)
    assert "SYNTHETIC" in text


def test_app_reports_infeasible_budget():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.number_input[0].set_value(20_000).run()
    assert not at.exception
    assert "INFEASIBLE" in " ".join(e.value for e in at.error)
