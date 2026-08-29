"""Tests for per-chart Analysis PDF pages with conclusions."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import AnalysisResult, Platform, Site, Vehicle
from modules.m5_reports.analysis_chart_pages import build_analysis_chart_pages
from modules.m5_reports.pdf_report import generate_analysis_report


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    import core.database as db_mod

    db = tmp_path / "pdf_charts.db"
    monkeypatch.setattr("config.DB_PATH", str(db))
    monkeypatch.setattr(db_mod, "DB_PATH", str(db))
    db_mod.init_db()
    return db


def _sample_result(month: int = 6, overall: float = 0.72) -> AnalysisResult:
    site = Site(lat=28.5, lon=-80.5, name="Test Site", bbox_nm=25.0)
    vehicle = Vehicle(
        name="Test Veh",
        vehicle_class="slv_orb",
        max_wind_kts=20,
        max_gust_kts=25,
        max_hs_m=1.83,
        max_swell_ht_m=2.44,
        max_swell_period_s=18,
        recovery_mode="expendable",
    )
    platform = Platform(
        name="Gateway X",
        hull_type="semisub",
        hull_motion_factor=1.0,
    )
    return AnalysisResult(
        site=site,
        vehicle=vehicle,
        platform=platform,
        mode="historical",
        overall_prob=overall,
        param_probs={
            "ws": 0.8, "wg": 0.75, "sh": 0.7, "swh": 0.65, "swp": 0.9,
            "wdV": 0.5, "sdV": 0.5, "swdV": 0.5,
        },
        limiting_param="sh",
        data_sources={p: "era5_reanalysis" for p in
                      ("ws", "wg", "sh", "swh", "swp", "wdV", "sdV", "swdV")},
        effective_means={
            "ws": 10.0 + month * 0.3,
            "wg": 14.0 + month * 0.2,
            "sh": 0.8 + month * 0.05,
            "swh": 0.5 + month * 0.03,
            "swp": 7.0 + month * 0.2,
            "wdV": 40.0,
            "sdV": 50.0,
            "swdV": 55.0,
        },
        thresholds=vehicle.thresholds(),
        weights={"ws": 0.3, "wg": 0.26, "sh": 0.22, "swh": 0.14, "swp": 0.08},
        active_params={"ws", "wg", "sh", "swh", "swp"},
        year_start=2020,
        year_end=2024,
        month_filter=month,
    )


def _sample_profile() -> dict:
    # Summer higher, winter lower — exercises conclusions.
    overalls = [0.55, 0.58, 0.52, 0.60, 0.68, 0.78, 0.85, 0.88, 0.80, 0.70, 0.62, 0.57]
    return {m: _sample_result(m, overalls[m - 1]) for m in range(1, 13)}


class TestAnalysisChartPages:
    def test_builds_twelve_individual_charts_with_conclusions(self, tmp_path):
        pages = build_analysis_chart_pages(tmp_path, _sample_profile())
        assert len(pages) == 12
        for p in pages:
            assert Path(p.path).is_file()
            assert Path(p.path).stat().st_size > 1000
            assert p.title
            assert len(p.conclusion.split()) >= 20  # ~2–3 sentences

    def test_pdf_embeds_per_chart_pages(self, isolated_db, tmp_path):
        profile = _sample_profile()
        chart_dir = tmp_path / "charts"
        pages = build_analysis_chart_pages(chart_dir, profile)
        out = tmp_path / "report.pdf"
        saved = generate_analysis_report(
            profile[6],
            str(out),
            annual_profile=profile,
            chart_pages=pages,
        )
        assert Path(saved).is_file()
        assert Path(saved).stat().st_size > 20_000
