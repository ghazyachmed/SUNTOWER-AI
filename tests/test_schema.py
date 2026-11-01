import os

import pandas as pd
import pytest

from site_schema import EVIDENCE_TYPES, evidence_matrix, load_portfolio_csv, validate_portfolio

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE = os.path.join(ROOT, "data", "sample_portfolio_fictional.csv")


@pytest.fixture
def records():
    return load_portfolio_csv(SAMPLE)


def _set(df, site, field, **kw):
    df = df.copy()
    m = (df.site_id == site) & (df.field == field)
    for k, v in kw.items():
        df.loc[m, k] = v
    return df


def _errors(issues, site=None, field=None):
    return [i for i in issues if i.severity == "error"
            and (site is None or i.site_id == site) and (field is None or i.field == field)]


def test_sample_validates_except_deliberate_error(records):
    sites, issues = validate_portfolio(records)
    assert len(sites) == 10
    assert {i.site_id for i in _errors(issues)} == {"FICT-11"}
    assert records["site_id"].nunique() == 11


def test_every_evidence_type_is_allowed_and_labelled(records):
    assert set(records["evidence_type"]) <= set(EVIDENCE_TYPES)
    sites, _ = validate_portfolio(records)
    m = evidence_matrix(sites)
    assert {"SYNTHETIC", "PROXY", "ASSUMPTION", "MISSING"} <= set(m.drop(columns="site_id").values.ravel())


@pytest.mark.parametrize("field,value", [("latitude", "95"), ("longitude", "-181"),
                                         ("ghi_kwh_m2_day", "0.2"), ("diesel_ef_kg_per_l", "9.5"),
                                         ("grid_ef_kg_per_kwh", "-0.1"), ("pv_capex_per_kwp", "-900"),
                                         ("grid_tariff_per_kwh", "4.0"), ("load_kw_avg", "abc")])
def test_out_of_range_values_rejected(records, field, value):
    _, issues = validate_portfolio(_set(records, "FICT-01", field, value=value))
    assert _errors(issues, "FICT-01", field)


def test_unit_mismatch_rejected(records):
    _, issues = validate_portfolio(_set(records, "FICT-02", "load_kw_avg", unit="W"))
    assert _errors(issues, "FICT-02", "load_kw_avg")


def test_mixed_currency_blocks_portfolio(records):
    df = _set(records, "FICT-03", "currency", value="IDR")
    sites, issues = validate_portfolio(df)
    assert sites == [] and _errors(issues, "*", "currency")


def test_zero_tariff_on_grid_site_rejected(records):
    _, issues = validate_portfolio(_set(records, "FICT-02", "grid_tariff_per_kwh", value="0"))
    assert _errors(issues, "FICT-02", "grid_tariff_per_kwh")


def test_measured_needs_source_and_date(records):
    df = _set(records, "FICT-01", "load_kw_avg", evidence_type="measured", source="", as_of_date="")
    _, issues = validate_portfolio(df)
    assert _errors(issues, "FICT-01", "load_kw_avg")


def test_blank_value_must_be_labelled_missing(records):
    df = _set(records, "FICT-04", "diesel_l_per_day", evidence_type="synthetic")
    _, issues = validate_portfolio(df)
    assert _errors(issues, "FICT-04", "diesel_l_per_day")


def test_duplicate_tower_coordinates_flagged(records):
    df = _set(records, "FICT-02", "latitude", value="-7.0")
    df = _set(df, "FICT-02", "longitude", value="107.00001")
    sites, issues = validate_portfolio(df)
    flagged = {i.site_id for i in _errors(issues) if "duplicate" in i.message.lower()}
    assert flagged == {"FICT-01", "FICT-02"}
    assert "FICT-01" not in {s.site_id for s in sites}


def test_duplicate_rows_flagged(records):
    df = pd.concat([records, records[(records.site_id == "FICT-05") & (records.field == "load_kw_avg")]])
    _, issues = validate_portfolio(df)
    assert _errors(issues, "FICT-05", "load_kw_avg")


def test_proxy_label_is_preserved(records):
    sites, _ = validate_portfolio(records)
    s3 = next(s for s in sites if s.site_id == "FICT-03")
    assert s3.evidence("ghi_kwh_m2_day") == "modeled_proxy"
