"""Deterministic lab-value flagging tests."""
from app.safety.lab_ranges import extract_lab_values, worst_flag


def test_extract_normal_value():
    values = extract_lab_values("Hemoglobin: 14.0 g/dL")
    assert len(values) == 1
    assert values[0].name == "hemoglobin"
    assert values[0].flag == "normal"


def test_extract_high_value():
    values = extract_lab_values("Fasting Glucose 145 mg/dL")
    glucose = next(v for v in values if v.name == "fasting glucose")
    assert glucose.flag == "high"


def test_extract_low_value():
    values = extract_lab_values("TSH 0.1 mIU/L")
    tsh = next(v for v in values if v.name == "tsh")
    assert tsh.flag == "low"


def test_extract_multiple_values():
    text = "Hemoglobin 10.5 g/dL\nCreatinine 2.1 mg/dL\nTotal Cholesterol 180 mg/dL"
    values = extract_lab_values(text)
    names = {v.name for v in values}
    assert {"hemoglobin", "creatinine", "total cholesterol"} <= names
    flags = {v.name: v.flag for v in values}
    assert flags["hemoglobin"] == "low"
    assert flags["creatinine"] == "high"
    assert flags["total cholesterol"] == "normal"


def test_no_recognized_values():
    assert extract_lab_values("Patient reports feeling generally well.") == []


def test_worst_flag():
    values = extract_lab_values("Creatinine 2.1 mg/dL\nHemoglobin 14.0 g/dL")
    assert worst_flag(values) == "high"
    normal_only = extract_lab_values("Hemoglobin 14.0 g/dL")
    assert worst_flag(normal_only) is None
