"""The pseudonymiser of natural PR-review texts after S9 (src/tracecontract/ingest/pseudonymize_pr.py; D51, §16.4).

Synthetic texts only. Logins are fictional (``fx-...``); e-mail addresses and model identifiers are
built at run time from parts, so that this file holds none.
"""

from __future__ import annotations

from tracecontract.ingest.pseudonymize_pr import (
    MODEL_PLACEHOLDER, OWNER, PROFILE_PLACEHOLDER, PRPseudonymizer, code_spans, in_decorator_position, is_code_at,
    mask_repo_url,
)

MAIL = "fx-rev-1" + "@" + "example.org"
PERSONS = frozenset({"fx-stranger", "fx-owner", "fx-rev-1", "fx-issue"})


def _ps(**kw) -> PRPseudonymizer:
    return PRPseudonymizer({"fx-rev-1": "reviewer", "fx-author": "pr-author", "fx-issue": "issue-author"}, {"fx-x"},
                           bots={"lint-bot[bot]"}, persons=PERSONS, **kw)


def test_repository_urls_follow_the_owner_rule():
    assert mask_repo_url("https://github.com/fx-owner/fx-owner-utils", True) == f"https://github.com/{OWNER}/{OWNER}-utils"
    assert mask_repo_url("https://github.com/fx-owner/tools", True) == f"https://github.com/{OWNER}/tools"
    assert mask_repo_url("https://github.com/fx-org/fx-org-lib", False) == "https://github.com/fx-org/fx-org-lib"
    assert mask_repo_url("https://api.github.com/repos/fx-owner/x", True) == f"https://api.github.com/repos/{OWNER}/x"
    ps = _ps(owner="fx-owner", owner_acts_as_account=True)
    assert ps.repo_url("https://github.com/fx-owner/fx-ownerbot") == f"https://github.com/{OWNER}/fx-ownerbot"
    assert ps.repo_url("https://github.com/fx-stranger/r") == f"https://github.com/{OWNER}/r"  # a person in AIDev
    assert ps.repo_url("https://github.com/fx-org/r") == "https://github.com/fx-org/r"  # an organisation
    # In texts, the owner who acts as an account is a known login.
    assert ps("thanks fx-owner") == "thanks repo-owner"
    assert _ps(owner="fx-org", owner_acts_as_account=False)("fx-org/lib and https://github.com/fx-org/lib") == \
        "fx-org/lib and https://github.com/fx-org/lib"


def test_every_github_link_masks_a_person_account():
    ps = _ps(owner="fx-owner", owner_acts_as_account=True)
    text = ("see https://github.com/fx-stranger/tool/issues/3, github.com/fx-x/r/pull/1, "
            "https://github.com/fx-org/fx-author/pull/2, https://gist.github.com/fx-stranger/abc, "
            "https://raw.githubusercontent.com/fx-stranger/r/main/a.py, git@github.com:fx-stranger/r.git, "
            "https://fx-stranger.github.io/blog, https://api.github.com/repos/fx-stranger/r/pulls, "
            "https://github.com/fx-owner/fx-owner-utils/blob/main/x.py and https://github.com/fx-org/lib.")
    out = ps(text)
    assert "fx-stranger" not in out and "fx-x" not in out and "fx-author" not in out and "fx-owner" not in out
    assert ("see https://github.com/user-1/tool/issues/3, github.com/user-2/r/pull/1, "  # labels by first appearance
            "https://github.com/fx-org/pr-author/pull/2, https://gist.github.com/user-1/abc, "
            "https://raw.githubusercontent.com/user-1/r/main/a.py, git@github.com:user-1/r.git, "
            "https://user-1.github.io/blog, https://api.github.com/repos/user-1/r/pulls, "
            f"https://github.com/{OWNER}/{OWNER}-utils/blob/main/x.py and https://github.com/fx-org/lib.") == out
    # Profile links go entirely, as before.
    assert ps("https://github.com/fx-org and https://github.com/sponsors/fx-stranger") == \
        f"{PROFILE_PLACEHOLDER} and {PROFILE_PLACEHOLDER}"
    assert ps.counts["link_account"] >= 7 and ps.counts["owner"] == 1


def test_git_author_names_with_a_space_are_known_names():
    ps = PRPseudonymizer({"fx-rev-1": "reviewer"}, names={"Fx Person", "Fx Q. Other", "fx-single"})
    out = ps("Fx Person and fx  person\nwrote it; FX Q. Other reviewed; fx-single is a login, not a name")
    assert out == "user-1 and user-1\nwrote it; user-2 reviewed; fx-single is a login, not a name"
    assert ps.counts["name"] == 3


def test_code_tokens_stay_intact():
    ps = _ps()
    hunk = ("@@ -1,3 +1,6 @@\n class A:\n+    @property\n+    @pytest.mark.slow\n+    @dataclass(frozen=True)\n"
            "+    @freeze_time(\"2020-01-01\")\n+    @mydecorator\n+    @fx-rev-1\n     x = a @b\n+@pytest.mark.skip")
    assert ps(hunk, code=True) == hunk  # decorators and decorator positions in a diff hunk are code
    prose = ("@fx-rev-1 use @property or @functools.cache, like @wraps(f); see @NAME@ in the template, "
             "and ask @fx-new and @fx-stranger.\n```python\n@mydecorator\ndef f(): return a @fx-stranger\n```\n"
             "@mydecorator please")
    assert ps(prose) == ("@reviewer use @property or @functools.cache, like @wraps(f); see @NAME@ in the template, "
                         "and ask @user-1 and @user-2.\n```python\n@mydecorator\ndef f(): return a @user-2\n```\n"
                         "@user-3 please")
    assert is_code_at("@freeze_time(", 0, 7) and is_code_at("@x.y", 0, 2) and not is_code_at("@x. y", 0, 2)
    assert in_decorator_position("a\n+    @p", 7) and not in_decorator_position("a @p", 2)
    assert code_spans("x\n```\n@a\n```\ny") == [(2, 12)]


def test_emails_handles_and_bots_as_before_in_one_pass():
    ps = _ps()
    text = f"@FX-REV-1 and @fx-author: ask @lint-bot, @devin-ai-integration[bot] and @fx-new; fx-x agreed ({MAIL})"
    assert ps(text) == "@reviewer and @pr-author: ask @bot-1, @agent and @user-1; user-2 agreed ([email removed])"
    assert ps("+@pytest.mark.slow and x@pytest.mark.parametrize(1)") == "+@pytest.mark.slow and x@pytest.mark.parametrize(1)"
    # One pass: a participant whose login equals a label is not replaced again.
    ps2 = PRPseudonymizer({"fx-rev-1": "reviewer"}, {"reviewer"})
    assert ps2("fx-rev-1 and reviewer") == "reviewer and user-1"
    assert ps(None) is None


def _ids() -> list[str]:
    """Identifiers in the formats of several model families, built from parts; the versions are fictional."""
    g, c, ge, ll, mi = "g" + "pt", "cla" + "ude", "gem" + "ini", "lla" + "ma", "mis" + "tral"
    return [f"{g}-9z", f"{g.upper()}-9.5-turbo", f"{g}9", f"chat{g}-9z-latest", "o" + "9-mini", f"{c}-9-opus-20990101",
            f"{c}-sonnet-9", f"{c.title()} 9.5 Sonnet", f"{ge}-9.5-pro", f"{ge.title()} 9.5 Flash", f"{ll}-9-99b-instruct",
            f"{mi}-large-9", "deep" + "seek-r9", "qw" + "en9.5-coder-99b", "ph" + "i-9-mini", "text-da" + "vinci-009"]


def test_model_identifiers_are_masked():
    ps = _ps()
    for mid in _ids():
        assert ps(f"tried {mid}, it failed") == f"tried {MODEL_PLACEHOLDER}, it failed", mid
    keep = ("Claude Code opened this PR with the cla" + "ude-code CLI; Chat" + "GPT and Copilot are products; "
            "import lla" + "ma_index; o1 = 2; gpt_model = None; the session directory /tmp/cla" + "ude-0/x")
    assert ps(keep) == keep
    assert ps.counts["model_identifier"] == len(_ids())
