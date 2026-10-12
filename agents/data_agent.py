from tools.data_tools import (
    load_state_data,
    get_state_analysis,
    get_india_market_context,
    rank_all_states
)


# ============================================================
# 1. ANALYZE ANY TARGET STATE
# ============================================================

def analyze_target_state(target_state):
    """
    Analyze a user-selected target state/UT.

    The function works for any state available
    in the DecisionRoom dataset.
    """

    state_data = get_state_analysis(target_state)

    if state_data is None:
        return {
            "success": False,
            "error": f"State/UT '{target_state}' was not found."
        }

    india_context = get_india_market_context()

    return {
        "success": True,
        "target_state": target_state,
        "state_evidence": state_data,
        "india_market_context": india_context
    }


# ============================================================
# 2. GET TARGET STATE RANKING
# ============================================================

def get_target_state_ranking(target_state):
    """
    Find the ranking position of a selected state/UT
    across the available startup and funding indicators.
    """

    rankings = rank_all_states()

    state_result = rankings[
        rankings["State/UT"].str.lower()
        == target_state.lower()
    ]

    if state_result.empty:
        return None

    return state_result.iloc[0].to_dict()


# ============================================================
# 3. FIND COMPARABLE STATES
# ============================================================

def get_comparable_states(target_state, n=5):
    """
    Find states with similar startup-base size
    to the selected target state.

    This is a simple quantitative comparison.
    """

    df = load_state_data()

    target = df[
        df["State/UT"].str.lower()
        == target_state.lower()
    ]

    if target.empty:
        return None

    target_startups = target.iloc[0][
        "Total_Startups_2020_2024"
    ]

    # Calculate distance from target state's startup base
    df = df.copy()

    df["Startup_Base_Difference"] = abs(
        df["Total_Startups_2020_2024"]
        - target_startups
    )

    # Exclude target itself
    df = df[
        df["State/UT"].str.lower()
        != target_state.lower()
    ]

    result = (
        df.sort_values("Startup_Base_Difference")
        [
            [
                "State/UT",
                "Total_Startups_2020_2024",
                "Growth_Percentage",
                "Total_Funding_USD",
                "Funding_Data_Available"
            ]
        ]
        .head(n)
    )

    return result


# ============================================================
# 4. COMPLETE DATA AGENT ANALYSIS
# ============================================================

def analyze_market_entry(target_state):
    """
    Generate the quantitative evidence required for
    a market-entry decision for any state/UT.
    """

    target_analysis = analyze_target_state(
        target_state
    )

    if not target_analysis["success"]:
        return target_analysis

    ranking = get_target_state_ranking(
        target_state
    )

    comparable_states = get_comparable_states(
        target_state
    )

    return {
        "success": True,

        "target_state": target_state,

        "state_evidence": target_analysis[
            "state_evidence"
        ],

        "state_ranking": ranking,

        "comparable_states": (
            comparable_states.to_dict(
                orient="records"
            )
            if comparable_states is not None
            else []
        ),

        "india_market_context": target_analysis[
            "india_market_context"
        ]
    }


# ============================================================
# 5. DISPLAY DATA AGENT RESULT
# ============================================================

def print_analysis(analysis):
    """
    Display the Data Agent result in a readable format.
    """

    if not analysis["success"]:

        print("\n========== DATA AGENT ERROR ==========")

        print(
            analysis["error"]
        )

        return

    print(
        "\n========== DATA AGENT ANALYSIS =========="
    )

    print(
        f"\nTarget State: "
        f"{analysis['target_state']}"
    )

    # --------------------------------------------------------
    # State evidence
    # --------------------------------------------------------

    print(
        "\n---------- STATE EVIDENCE ----------"
    )

    evidence = analysis["state_evidence"]

    print(
        f"Total Startups (2020-2024): "
        f"{evidence['Total_Startups_2020_2024']}"
    )

    print(
        f"Startup Growth: "
        f"{evidence['Startup_Growth_2020_2024']}"
    )

    print(
        f"Growth Percentage: "
        f"{evidence['Growth_Percentage']:.2f}%"
    )

    print(
        f"Funding Records: "
        f"{evidence['Funding_Records']}"
    )

    print(
        f"Unique Funded Startups: "
        f"{evidence['Unique_Startups']}"
    )

    print(
        f"Total Recorded Funding: "
        f"${evidence['Total_Funding_USD']:,.2f}"
    )

    print(
        f"Average Funding: "
        f"${evidence['Average_Funding_USD']:,.2f}"
    )

    print(
        f"Median Funding: "
        f"${evidence['Median_Funding_USD']:,.2f}"
    )

    print(
        f"Funding Data Available: "
        f"{evidence['Funding_Data_Available']}"
    )

    # --------------------------------------------------------
    # Rankings
    # --------------------------------------------------------

    print(
        "\n---------- STATE RANKING ----------"
    )

    ranking = analysis["state_ranking"]

    print(
        f"Startup Base Rank: "
        f"{ranking['Startup_Base_Rank']}"
    )

    print(
        f"Startup Growth Rank: "
        f"{ranking['Startup_Growth_Rank']}"
    )

    print(
        f"Funding Rank: "
        f"{ranking['Funding_Rank']}"
    )

    # --------------------------------------------------------
    # Comparable states
    # --------------------------------------------------------

    print(
        "\n---------- COMPARABLE STATES ----------"
    )

    comparable = analysis[
        "comparable_states"
    ]

    if comparable:

        comparable_df = __import__(
            "pandas"
        ).DataFrame(comparable)

        print(
            comparable_df.to_string(
                index=False
            )
        )

    else:

        print(
            "No comparable states found."
        )

    # --------------------------------------------------------
    # India context
    # --------------------------------------------------------

    print(
        "\n---------- INDIA MARKET CONTEXT ----------"
    )

    context = analysis[
        "india_market_context"
    ]

    print(
        f"Year: {context['Year']}"
    )

    print(
        f"GDP Growth: "
        f"{context['GDP_Growth_Percent']:.2f}%"
    )

    print(
        f"GDP: "
        f"${context['GDP_USD']:,.2f}"
    )

    print(
        f"Internet Users: "
        f"{context['Internet_Users_Percent']:.2f}%"
    )

    print(
        f"Population: "
        f"{context['Population']:,.0f}"
    )


# ============================================================
# 6. TESTING
# ============================================================

if __name__ == "__main__":

    # Test with one state.
    # Change this value to ANY state/UT in the dataset.

    target_state = "Tamil Nadu"

    analysis = analyze_market_entry(
        target_state
    )

    print_analysis(
        analysis
    )