import pandas as pd


# ============================================================
# 1. LOAD STATE-LEVEL DATA
# ============================================================

def load_state_data():
    """
    Load the combined state-level DecisionRoom dataset.

    The 'Total' row is removed because it represents
    the national total, not an individual state/UT.
    """

    file_path = "data/processed/state_decision_dataset.csv"

    df = pd.read_csv(file_path)

    # Remove national Total row
    df = df[
        df["State/UT"].str.lower() != "total"
    ].copy()

    return df


# ============================================================
# 2. LOAD WORLD BANK DATA
# ============================================================

def load_worldbank_data():
    """
    Load India-level World Bank market context.
    """

    file_path = "data/processed/worldbank_india_market.csv"

    df = pd.read_csv(file_path)

    return df


# ============================================================
# 3. GET INFORMATION FOR ONE STATE
# ============================================================

def get_state_analysis(state_name):
    """
    Return quantitative evidence for any state/UT.

    The function is generic and does not depend on
    Tamil Nadu or Karnataka.
    """

    df = load_state_data()

    state_data = df[
        df["State/UT"].str.lower() == state_name.lower()
    ]

    if state_data.empty:
        return None

    return state_data.iloc[0].to_dict()


# ============================================================
# 4. TOP STATES BY STARTUP BASE
# ============================================================

def get_top_states_by_startups(n=10):
    """
    Find states with the highest total number of
    DPIIT-recognized startups from 2020-2024.
    """

    df = load_state_data()

    result = (
        df.sort_values(
            "Total_Startups_2020_2024",
            ascending=False
        )
        [
            [
                "State/UT",
                "Total_Startups_2020_2024"
            ]
        ]
        .head(n)
    )

    return result


# ============================================================
# 5. TOP STATES BY FUNDING
# ============================================================

def get_top_states_by_funding(n=10):
    """
    Find states with the highest recorded startup funding.

    Only states with actual funding data are included.
    """

    df = load_state_data()

    # Missing funding data is NOT treated as zero.
    df = df[
        df["Funding_Data_Available"] == True
    ].copy()

    result = (
        df.sort_values(
            "Total_Funding_USD",
            ascending=False
        )
        [
            [
                "State/UT",
                "Total_Funding_USD"
            ]
        ]
        .head(n)
    )

    return result


# ============================================================
# 6. INDIA MARKET CONTEXT
# ============================================================

def get_india_market_context():
    """
    Return the latest available India-level
    World Bank market indicators.
    """

    df = load_worldbank_data()

    latest = (
        df.sort_values("Year")
        .iloc[-1]
    )

    return latest.to_dict()


# ============================================================
# 7. COMPARE TWO STATES
# ============================================================

def compare_states(state_a, state_b):
    """
    Compare any two states/UTs.

    This function is completely generic.
    """

    df = load_state_data()

    states = df[
        df["State/UT"].str.lower().isin(
            [
                state_a.lower(),
                state_b.lower()
            ]
        )
    ].copy()

    if len(states) != 2:
        return None

    comparison_columns = [
        "State/UT",
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "Total_Startups_2020_2024",
        "Startup_Growth_2020_2024",
        "Growth_Percentage",
        "Funding_Records",
        "Unique_Startups",
        "Total_Funding_USD",
        "Average_Funding_USD",
        "Median_Funding_USD",
        "Funding_Data_Available"
    ]

    return states[comparison_columns]


# ============================================================
# 8. RANK ALL STATES
# ============================================================

def rank_all_states():
    """
    Rank all states/UTs using available startup
    ecosystem and funding indicators.

    This function does NOT depend on any particular state.
    """

    df = load_state_data()

    # --------------------------------------------------------
    # Startup base ranking
    # --------------------------------------------------------

    df["Startup_Base_Rank"] = (
        df["Total_Startups_2020_2024"]
        .rank(
            ascending=False,
            method="min"
        )
        .astype(int)
    )

    # --------------------------------------------------------
    # Startup growth ranking
    # --------------------------------------------------------

    df["Startup_Growth_Rank"] = (
        df["Growth_Percentage"]
        .rank(
            ascending=False,
            method="min"
        )
        .astype(int)
    )

    # --------------------------------------------------------
    # Funding ranking
    # --------------------------------------------------------

    df["Funding_Rank"] = pd.NA

    funding_mask = (
        df["Funding_Data_Available"] == True
    )

    df.loc[funding_mask, "Funding_Rank"] = (
        df.loc[funding_mask, "Total_Funding_USD"]
        .rank(
            ascending=False,
            method="min"
        )
        .astype(int)
    )

    # --------------------------------------------------------
    # Select useful columns
    # --------------------------------------------------------

    result = df[
        [
            "State/UT",
            "Total_Startups_2020_2024",
            "Growth_Percentage",
            "Total_Funding_USD",
            "Funding_Data_Available",
            "Startup_Base_Rank",
            "Startup_Growth_Rank",
            "Funding_Rank"
        ]
    ].sort_values(
        "Startup_Base_Rank"
    )

    return result


# ============================================================
# 9. MAIN TESTING SECTION
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # TOP STATES BY STARTUP BASE
    # --------------------------------------------------------

    print(
        "\n========== TOP STATES BY STARTUPS =========="
    )

    print(
        get_top_states_by_startups(10)
        .to_string(index=False)
    )


    # --------------------------------------------------------
    # TOP STATES BY FUNDING
    # --------------------------------------------------------

    print(
        "\n========== TOP STATES BY FUNDING =========="
    )

    print(
        get_top_states_by_funding(10)
        .to_string(index=False)
    )


    # --------------------------------------------------------
    # INDIA MARKET CONTEXT
    # --------------------------------------------------------

    print(
        "\n========== INDIA MARKET CONTEXT =========="
    )

    print(
        get_india_market_context()
    )


    # --------------------------------------------------------
    # EXAMPLE STATE COMPARISON
    # --------------------------------------------------------

    print(
        "\n========== STATE COMPARISON =========="
    )

    comparison = compare_states(
        "Tamil Nadu",
        "Karnataka"
    )

    if comparison is not None:
        print(
            comparison.to_string(index=False)
        )
    else:
        print(
            "One or both states were not found."
        )


    # --------------------------------------------------------
    # ALL STATE RANKING
    # --------------------------------------------------------

    print(
        "\n========== ALL STATE RANKING =========="
    )

    rankings = rank_all_states()

    print(
        rankings.to_string(index=False)
    )