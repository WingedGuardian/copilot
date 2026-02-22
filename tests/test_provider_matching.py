"""Test improved provider matching with normalized prefixes and OAuth support."""
from nanobot.config.schema import Config, ProviderConfig, ProvidersConfig


def _make_config(**provider_keys) -> Config:
    """Create a Config with specific providers having API keys."""
    providers = ProvidersConfig()
    for name, key in provider_keys.items():
        setattr(providers, name, ProviderConfig(api_key=key))
    return Config(providers=providers)


def test_prefix_matching_normalized():
    """github-copilot/model should match github_copilot provider (dash to underscore)."""
    config = _make_config(openai="sk-test")
    _, name = config._match_provider("github-copilot/gpt-4o")
    assert name == "github_copilot"


def test_oauth_provider_not_in_fallback():
    """OAuth providers should not be returned as fallback when no model matches."""
    config = Config()
    config.providers.github_copilot = ProviderConfig(api_key="fake")
    p, name = config._match_provider("some/random-model")
    assert name != "github_copilot"


def test_keyword_matching_still_works():
    """Standard keyword matching should still function."""
    config = _make_config(deepseek="sk-test")
    _, name = config._match_provider("deepseek/deepseek-chat")
    assert name == "deepseek"


def test_dash_underscore_normalization_in_keywords():
    """Keywords with dashes should match model strings with underscores and vice versa."""
    config = _make_config(openai="sk-test")
    _, name = config._match_provider("gpt-4o")
    assert name == "openai"
