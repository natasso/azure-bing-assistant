from decimal import Decimal

import pytest

from scripts.estimate_monthly_cost import (
    BASE_FIXED_USD,
    GPT_GLOBAL_INPUT_USD_PER_MILLION,
    GPT_GLOBAL_OUTPUT_USD_PER_MILLION,
    OBSERVED_SAMPLE_CACHED_INPUT_TOKENS,
    OBSERVED_SAMPLE_INPUT_TOKENS,
    OBSERVED_SAMPLE_OUTPUT_TOKENS,
    OPTIMIZED_VARIABLE_REDUCTION_PERCENT,
    estimate_monthly_cost,
    estimate_observed_sample_monthly_cost,
    main,
    round_usd,
)


@pytest.mark.parametrize(
    ("conversations", "expected_total"),
    [
        (10, "14.46"),
        (100, "26.33"),
        (1_000, "145.02"),
        (10_000, "1331.89"),
        (100_000, "13200.64"),
    ],
)
def test_documented_totals(conversations, expected_total):
    estimate = estimate_monthly_cost(conversations)
    assert round_usd(estimate.total) == Decimal(expected_total)


def test_zero_conversations_has_only_fixed_cost():
    estimate = estimate_monthly_cost(0)
    assert estimate.fixed == BASE_FIXED_USD == Decimal("13.140")
    assert estimate.variable == Decimal("0")
    assert estimate.total == BASE_FIXED_USD


def test_turn_count_rescales_only_variable_cost():
    one_turn = estimate_monthly_cost(1, turns_per_conversation=1)
    five_turns = estimate_monthly_cost(1, turns_per_conversation=5)
    assert one_turn.variable == Decimal("0.026375")
    assert five_turns.variable == one_turn.variable * 5
    assert five_turns.fixed == one_turn.fixed


def test_bing_transaction_sensitivity():
    estimates = [
        estimate_monthly_cost(
            1, turns_per_conversation=1, bing_transactions_per_turn=count
        )
        for count in (0, 1, 2)
    ]
    assert [estimate.bing for estimate in estimates] == [
        Decimal("0"),
        Decimal("0.014"),
        Decimal("0.028"),
    ]
    assert all(estimate.model == Decimal("0.012375") for estimate in estimates)


def test_global_standard_is_a_separate_comparison():
    estimate = estimate_monthly_cost(
        100_000,
        gpt_input_usd_per_million=GPT_GLOBAL_INPUT_USD_PER_MILLION,
        gpt_output_usd_per_million=GPT_GLOBAL_OUTPUT_USD_PER_MILLION,
    )
    assert estimate.variable / Decimal("100000") == Decimal("0.12625")
    assert round_usd(estimate.total) == Decimal("12638.14")


def test_data_zone_high_output_sensitivity():
    baseline = estimate_monthly_cost(1)
    high_output = estimate_monthly_cost(1, output_tokens_per_turn=1_500)
    assert high_output.variable - baseline.variable == Decimal("0.08250")
    baseline_100k = estimate_monthly_cost(100_000)
    high_output_100k = estimate_monthly_cost(
        100_000, output_tokens_per_turn=1_500
    )
    assert high_output_100k.total - baseline_100k.total == Decimal("8250.00000")


def test_observed_sample_uses_aggregate_tokens_without_adding_cached_tokens():
    estimate = estimate_observed_sample_monthly_cost(1)
    assert OBSERVED_SAMPLE_CACHED_INPUT_TOKENS == 2_176
    assert OBSERVED_SAMPLE_CACHED_INPUT_TOKENS < OBSERVED_SAMPLE_INPUT_TOKENS
    assert OBSERVED_SAMPLE_OUTPUT_TOKENS == 2_463
    assert estimate.model == Decimal("0.124267")
    assert estimate.bing == Decimal("0.070")
    assert estimate.variable == Decimal("0.194267")
    assert estimate.total == Decimal("13.334267")


@pytest.mark.parametrize(
    ("conversations", "expected_total"),
    [
        (10, "15.08"),
        (100, "32.57"),
        (1_000, "207.41"),
        (10_000, "1955.81"),
        (100_000, "19439.84"),
    ],
)
def test_observed_sample_documented_totals(conversations, expected_total):
    estimate = estimate_observed_sample_monthly_cost(conversations)
    assert round_usd(estimate.total) == Decimal(expected_total)


@pytest.mark.parametrize(
    ("conversations", "expected_total"),
    [(10, "14.50"), (100, "26.74"), (1_000, "149.13"),
     (10_000, "1373.01"), (100_000, "13611.83")],
)
def test_optimized_observed_sample_documented_totals(conversations, expected_total):
    estimate = estimate_observed_sample_monthly_cost(
        conversations, variable_reduction_percent=OPTIMIZED_VARIABLE_REDUCTION_PERCENT
    )
    assert round_usd(estimate.total) == Decimal(expected_total)
    assert estimate.fixed == BASE_FIXED_USD
    assert estimate.variable == Decimal(conversations) * Decimal("0.1359869")


def test_optimization_scales_spend_not_cached_measurements_or_fixed_cost():
    baseline = estimate_observed_sample_monthly_cost(1)
    optimized = estimate_observed_sample_monthly_cost(
        1, variable_reduction_percent=Decimal("30")
    )
    assert optimized.model == baseline.model * Decimal("0.70")
    assert optimized.bing == baseline.bing * Decimal("0.70")
    assert OBSERVED_SAMPLE_INPUT_TOKENS == 30_410
    assert OBSERVED_SAMPLE_CACHED_INPUT_TOKENS == 2_176
    assert estimate_observed_sample_monthly_cost(
        1, variable_reduction_percent=Decimal("0")
    ) == baseline
    for conversations, reduction in [(0, Decimal("30")), (100_000, Decimal("100"))]:
        estimate = estimate_observed_sample_monthly_cost(
            conversations, variable_reduction_percent=reduction
        )
        assert estimate.variable == 0
        assert estimate.total == estimate.fixed == BASE_FIXED_USD


@pytest.mark.parametrize(
    "reduction",
    [Decimal("-0.01"), Decimal("100.01"), Decimal("NaN"), Decimal("Infinity"),
     Decimal("-Infinity"), "invalid", None, True],
)
def test_invalid_variable_reduction_is_rejected(reduction):
    with pytest.raises(ValueError, match="variable_reduction_percent"):
        estimate_observed_sample_monthly_cost(1, variable_reduction_percent=reduction)


def test_calculator_labels_indicative_estimate_as_hypothetical_budget(capsys):
    main()
    output = capsys.readouterr().out
    assert "Stima mensile indicativa" in output
    assert "Indicative monthly estimate" in output
    assert "Hypothetical variable budget: USD 0.1359869 per 5-turn conversation" in output
    assert "not a tariff or measured bill" in output
    assert "Public tariffs and observed sample measurements are unchanged" in output
    assert "Estimated variable" in output
    assert "Estimated total" in output
    for removed in ("30%", "optimized", "ottimizzato", "Baseline total", "user-reported"):
        assert removed not in output
    assert "13,611.83" in output
    assert "19,439.84" in output
    assert "13,200.64" in output


@pytest.mark.parametrize(
    "kwargs",
    [
        {"conversations": -1},
        {"conversations": 1, "turns_per_conversation": -1},
        {"conversations": 1, "input_tokens_per_turn": -1},
        {"conversations": 1, "output_tokens_per_turn": -1},
        {"conversations": 1, "bing_transactions_per_turn": -1},
        {"conversations": 1, "fixed_monthly_usd": Decimal("-0.01")},
        {
            "conversations": 1,
            "gpt_input_usd_per_million": Decimal("-0.01"),
        },
        {
            "conversations": 1,
            "gpt_output_usd_per_million": Decimal("-0.01"),
        },
    ],
)
def test_negative_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        estimate_monthly_cost(**kwargs)
