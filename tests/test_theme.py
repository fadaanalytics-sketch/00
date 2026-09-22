from app.ui.theme import FONT_FAMILIES, _pick_available_font


def test_picks_first_preferred_family_that_is_installed():
    # Tahoma comes before Arial in the preference list.
    available = {"Arial", "Tahoma", "Comic Sans MS"}
    assert _pick_available_font(available) == "Tahoma"


def test_falls_through_to_later_entries_when_earlier_ones_are_missing():
    available = {FONT_FAMILIES[-2]}  # second-to-last preferred family only
    assert _pick_available_font(available) == FONT_FAMILIES[-2]


def test_no_match_falls_back_without_raising():
    # None of our preferred families are installed - must not crash, and falls
    # back to whatever Qt's default QFont() reports (which needs a running
    # QApplication to resolve to a real family name; here we only check that
    # the fallback path itself doesn't raise).
    result = _pick_available_font(set())
    assert isinstance(result, str)
