"""Reproduce the public-list monthly cost example documented by the project."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


GPT_DATA_ZONE_INPUT_USD_PER_MILLION = Decimal("2.75")
GPT_DATA_ZONE_OUTPUT_USD_PER_MILLION = Decimal("16.50")
GPT_GLOBAL_INPUT_USD_PER_MILLION = Decimal("2.50")
GPT_GLOBAL_OUTPUT_USD_PER_MILLION = Decimal("15.00")
BING_USD_PER_TRANSACTION = Decimal("14.00") / Decimal("1000")
APP_SERVICE_B1_LINUX_USD_PER_HOUR = Decimal("0.018")
MONTHLY_HOURS = Decimal("730")
BASE_FIXED_USD = APP_SERVICE_B1_LINUX_USD_PER_HOUR * MONTHLY_HOURS

DEFAULT_TURNS_PER_CONVERSATION = 5
DEFAULT_INPUT_TOKENS_PER_TURN = 1500
DEFAULT_OUTPUT_TOKENS_PER_TURN = 500
DEFAULT_BING_TRANSACTIONS_PER_TURN = 1
DEFAULT_VOLUMES = (10, 100, 1_000, 10_000, 100_000)

OBSERVED_SAMPLE_INPUT_TOKENS = 30_410
OBSERVED_SAMPLE_CACHED_INPUT_TOKENS = 2_176
OBSERVED_SAMPLE_OUTPUT_TOKENS = 2_463
OBSERVED_SAMPLE_COMPLETED_BING_CALLS = 5
OPTIMIZED_VARIABLE_REDUCTION_PERCENT = Decimal("30")

ONE_MILLION = Decimal("1000000")
ONE_CENT = Decimal("0.01")


@dataclass(frozen=True)
class MonthlyEstimate:
    fixed: Decimal
    model: Decimal
    bing: Decimal
    total: Decimal

    @property
    def variable(self) -> Decimal:
        return self.model + self.bing


def _non_negative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def estimate_monthly_cost(
    conversations: int,
    *,
    turns_per_conversation: int = DEFAULT_TURNS_PER_CONVERSATION,
    input_tokens_per_turn: int = DEFAULT_INPUT_TOKENS_PER_TURN,
    output_tokens_per_turn: int = DEFAULT_OUTPUT_TOKENS_PER_TURN,
    bing_transactions_per_turn: int = DEFAULT_BING_TRANSACTIONS_PER_TURN,
    fixed_monthly_usd: Decimal = BASE_FIXED_USD,
    gpt_input_usd_per_million: Decimal = GPT_DATA_ZONE_INPUT_USD_PER_MILLION,
    gpt_output_usd_per_million: Decimal = GPT_DATA_ZONE_OUTPUT_USD_PER_MILLION,
) -> MonthlyEstimate:
    """Return an unrounded estimate; round only values displayed as currency."""
    conversations = _non_negative_int("conversations", conversations)
    turns_per_conversation = _non_negative_int(
        "turns_per_conversation", turns_per_conversation
    )
    input_tokens_per_turn = _non_negative_int(
        "input_tokens_per_turn", input_tokens_per_turn
    )
    output_tokens_per_turn = _non_negative_int(
        "output_tokens_per_turn", output_tokens_per_turn
    )
    bing_transactions_per_turn = _non_negative_int(
        "bing_transactions_per_turn", bing_transactions_per_turn
    )
    fixed = Decimal(fixed_monthly_usd)
    if not fixed.is_finite() or fixed < 0:
        raise ValueError("fixed_monthly_usd must be a non-negative finite Decimal")
    input_rate = Decimal(gpt_input_usd_per_million)
    output_rate = Decimal(gpt_output_usd_per_million)
    if not input_rate.is_finite() or input_rate < 0:
        raise ValueError(
            "gpt_input_usd_per_million must be a non-negative finite Decimal"
        )
    if not output_rate.is_finite() or output_rate < 0:
        raise ValueError(
            "gpt_output_usd_per_million must be a non-negative finite Decimal"
        )

    turns = Decimal(conversations * turns_per_conversation)
    model_per_turn = (
        Decimal(input_tokens_per_turn)
        * input_rate
        / ONE_MILLION
        + Decimal(output_tokens_per_turn)
        * output_rate
        / ONE_MILLION
    )
    model = turns * model_per_turn
    bing = (
        turns
        * Decimal(bing_transactions_per_turn)
        * BING_USD_PER_TRANSACTION
    )
    return MonthlyEstimate(
        fixed=fixed,
        model=model,
        bing=bing,
        total=fixed + model + bing,
    )


def round_usd(value: Decimal) -> Decimal:
    return value.quantize(ONE_CENT, rounding=ROUND_HALF_UP)


def estimate_observed_sample_monthly_cost(
    conversations: int,
    *,
    variable_reduction_percent: Decimal = Decimal("0"),
) -> MonthlyEstimate:
    """Extrapolate the five-turn sample, optionally assuming lower variable spend.

    The reduction is a sensitivity assumption, not a tariff or token adjustment.
    Cached input is already included; one billed Bing transaction per completed
    call remains an unverified billing proxy in the baseline.
    """
    try:
        reduction = Decimal(str(variable_reduction_percent))
    except (InvalidOperation, ValueError):
        raise ValueError("variable_reduction_percent must be between 0 and 100") from None
    if not reduction.is_finite() or not 0 <= reduction <= 100:
        raise ValueError("variable_reduction_percent must be between 0 and 100")
    baseline = estimate_monthly_cost(
        conversations,
        turns_per_conversation=1,
        input_tokens_per_turn=OBSERVED_SAMPLE_INPUT_TOKENS,
        output_tokens_per_turn=OBSERVED_SAMPLE_OUTPUT_TOKENS,
        bing_transactions_per_turn=OBSERVED_SAMPLE_COMPLETED_BING_CALLS,
    )
    factor = Decimal("1") - reduction / Decimal("100")
    model = baseline.model * factor
    bing = baseline.bing * factor
    return MonthlyEstimate(
        fixed=baseline.fixed,
        model=model,
        bing=bing,
        total=baseline.fixed + model + bing,
    )


def main() -> None:
    print(
        "Public USD DataZoneStandard list-price scenario dated 2026-09-07: "
        "5 turns, 1,500 input tokens, 500 total billed output tokens, "
        "1 Bing transaction per turn"
    )
    print(
        f"{'Conversations':>13} {'Fixed':>10} {'Model':>10} "
        f"{'Bing':>10} {'Total':>12}"
    )
    for conversations in DEFAULT_VOLUMES:
        estimate = estimate_monthly_cost(conversations)
        print(
            f"{conversations:>13,} "
            f"{round_usd(estimate.fixed):>10,.2f} "
            f"{round_usd(estimate.model):>10,.2f} "
            f"{round_usd(estimate.bing):>10,.2f} "
            f"{round_usd(estimate.total):>12,.2f}"
        )
    global_estimate = estimate_monthly_cost(
        100_000,
        gpt_input_usd_per_million=GPT_GLOBAL_INPUT_USD_PER_MILLION,
        gpt_output_usd_per_million=GPT_GLOBAL_OUTPUT_USD_PER_MILLION,
    )
    global_variable_conversation = (
        global_estimate.variable / Decimal("100000")
    )
    print(
        "Separate GlobalStandard comparison: "
        f"{global_variable_conversation:.5f} variable/conversation; "
        f"{round_usd(global_estimate.total):,.2f} total at 100,000 conversations"
    )
    print(
        "\nIllustrative synthetic live smoke profile dated 2026-09-08: "
        "5 turns, 30,410 input tokens (including 2,176 cached input tokens), "
        "2,463 total output tokens, 5 completed Bing calls\n"
        "Bing cost proxy: 1 billable transaction per completed call; "
        "invoice billable usage was not measured or verified"
    )
    print(
        f"{'Conversations':>13} {'Fixed':>10} {'Model':>10} "
        f"{'Bing':>10} {'Total':>12}"
    )
    for conversations in DEFAULT_VOLUMES:
        estimate = estimate_observed_sample_monthly_cost(conversations)
        print(
            f"{conversations:>13,} "
            f"{round_usd(estimate.fixed):>10,.2f} "
            f"{round_usd(estimate.model):>10,.2f} "
            f"{round_usd(estimate.bing):>10,.2f} "
            f"{round_usd(estimate.total):>12,.2f}"
        )
    print(
        "\nIndicative monthly estimate / Stima mensile indicativa\n"
        "Hypothetical variable budget: USD 0.1359869 per 5-turn conversation, "
        "plus USD 13.14 monthly fixed cost; not a tariff or measured bill.\n"
        "Actual cost depends on model, tokens, Bing transactions, caching, and contract. "
        "Optional Search, taxes, and other excluded items are not included. "
        "Public tariffs and observed sample measurements are unchanged."
    )
    print(
        f"{'Conversations':>13} {'Fixed':>10} "
        f"{'Estimated variable':>18} {'Estimated total':>17}"
    )
    for conversations in DEFAULT_VOLUMES:
        optimized = estimate_observed_sample_monthly_cost(
            conversations,
            variable_reduction_percent=OPTIMIZED_VARIABLE_REDUCTION_PERCENT,
        )
        print(
            f"{conversations:>13,} "
            f"{round_usd(optimized.fixed):>10,.2f} "
            f"{round_usd(optimized.variable):>18,.2f} "
            f"{round_usd(optimized.total):>17,.2f}"
        )


if __name__ == "__main__":
    main()
