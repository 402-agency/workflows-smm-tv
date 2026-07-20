from app.services.ai.base import AnalysisResult, ScriptResult


def test_analysis_coerces_string_to_list():
    a = AnalysisResult.model_validate(
        {"summary": "Great", "strengths": "Acting", "extra": "ignored"}
    )
    assert a.strengths == ["Acting"]
    assert a.weaknesses == []
    assert a.summary == "Great"


def test_analysis_defaults_on_missing():
    a = AnalysisResult.model_validate({})
    assert a.summary == ""
    assert a.notable_topics == []


def test_script_parses_ranked_list_and_hashtags():
    s = ScriptResult.model_validate(
        {
            "hook": "Top 3!",
            "ranked_list": [{"position": 1, "title": "Dune", "blurb": "epic"}],
            "hashtags": "#film",
        }
    )
    assert s.ranked_list[0].title == "Dune"
    assert s.ranked_list[0].position == 1
    assert s.hashtags == ["#film"]


def test_script_handles_list_hashtags():
    s = ScriptResult.model_validate({"hashtags": ["#a", "#b", ""]})
    assert s.hashtags == ["#a", "#b"]
